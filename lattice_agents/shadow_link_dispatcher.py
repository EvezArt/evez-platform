#!/usr/bin/env python3
"""
EVEZ-OS Shadow-Link Dispatcher
Central hub coordinating Witness-Node agents via PBFT consensus.
Implements the Shadow-Link v3.0 protocol for non-commutative lattice routing.

Author: EVEZ Lattice Engineering
Date: 2026-04-22
"""

import json
import hashlib
import time
import uuid
from typing import Dict, List, Any, Optional, Set, Callable
from enum import Enum
from dataclasses import dataclass, field
import threading
import queue


class ConsensusState(Enum):
    PRE_PREPREPARE = "pre-prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    FINALIZED = "finalized"


@dataclass
class ShadowPacket:
    """Non-commutative data packet for Shadow-Link routing."""
    packet_id: str
    source_node: str
    target_nodes: List[str]
    payload: Dict[str, Any]
    temporal_stamp: float
    geometry_signature: str  # Order-dependent hash
    shadow_route: List[str] = field(default_factory=list)
    
    def compute_geometry(self) -> str:
        """Geometry = Logic: hash depends on operation order."""
        route_str = ":".join(self.shadow_route + [self.source_node])
        data = f"{route_str}:{json.dumps(self.payload, sort_keys=True)}:{self.temporal_stamp}"
        return hashlib.sha256(data.encode()).hexdigest()


class PBFTNode:
    """PBFT consensus node for the Shadow-Link ecosystem."""
    
    def __init__(self, node_id: str, total_nodes: int):
        self.node_id = node_id
        self.total_nodes = total_nodes
        self.faulty_threshold = (total_nodes - 1) // 3
        self.view_number = 0
        self.sequence_number = 0
        self.log: Dict[int, Dict] = {}
        self.finalized_callbacks: List[Callable] = []
    
    def _get_hash(self, data: Any) -> str:
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    
    def pre_prepare(self, data: Any) -> Dict[str, Any]:
        self.sequence_number += 1
        data_hash = self._get_hash(data)
        
        message = {
            "type": ConsensusState.PRE_PREPREPARE.value,
            "view": self.view_number,
            "seq": self.sequence_number,
            "hash": data_hash,
            "data": data,
            "node_id": self.node_id,
            "timestamp": time.time()
        }
        
        self.log[self.sequence_number] = {
            "state": ConsensusState.PRE_PREPREPARE,
            "data": data,
            "prepares": {self.node_id},
            "commits": set(),
            "hash": data_hash
        }
        
        return message
    
    def receive_pre_prepare(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        seq = message["seq"]
        if message["view"] != self.view_number:
            return None
        
        self.log[seq] = {
            "state": ConsensusState.PREPARE,
            "data": message["data"],
            "prepares": {self.node_id, message["node_id"]},
            "commits": set(),
            "hash": message["hash"]
        }
        
        return {
            "type": ConsensusState.PREPARE.value,
            "view": self.view_number,
            "seq": seq,
            "hash": message["hash"],
            "node_id": self.node_id,
            "timestamp": time.time()
        }
    
    def receive_prepare(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        seq = message["seq"]
        if seq not in self.log:
            return None
        
        self.log[seq]["prepares"].add(message["node_id"])
        
        if len(self.log[seq]["prepares"]) >= 2 * self.faulty_threshold + 1:
            if self.log[seq]["state"] != ConsensusState.COMMIT:
                self.log[seq]["state"] = ConsensusState.COMMIT
                self.log[seq]["commits"].add(self.node_id)
            
            return {
                "type": ConsensusState.COMMIT.value,
                "view": self.view_number,
                "seq": seq,
                "hash": message["hash"],
                "node_id": self.node_id,
                "timestamp": time.time()
            }
        return None
    
    def receive_commit(self, message: Dict[str, Any]) -> bool:
        seq = message["seq"]
        if seq not in self.log:
            return False
        
        self.log[seq]["commits"].add(message["node_id"])
        
        if len(self.log[seq]["commits"]) >= 2 * self.faulty_threshold + 1:
            if self.log[seq]["state"] != ConsensusState.FINALIZED:
                self.log[seq]["state"] = ConsensusState.FINALIZED
                self._on_finalize(seq)
            return True
        return False
    
    def _on_finalize(self, seq: int):
        data = self.log[seq]["data"]
        for cb in self.finalized_callbacks:
            cb(seq, data)
    
    def get_finalized_data(self, seq: int) -> Optional[Any]:
        if seq in self.log and self.log[seq]["state"] == ConsensusState.FINALIZED:
            return self.log[seq]["data"]
        return None


class ShadowLinkDispatcher:
    """
    Central hub coordinating Witness-Node agents via PBFT consensus.
    Implements Shadow-Link v3.0: non-commutative lattice with geometry=logic.
    """
    
    def __init__(self, hub_id: Optional[str] = None, node_count: int = 4):
        self.hub_id = hub_id or f"shadow_hub_{uuid.uuid4().hex[:8]}"
        self.node_count = node_count
        self.pbft_nodes: Dict[str, PBFTNode] = {}
        self.witness_agents: Dict[str, Any] = {}  # node_id -> witness agent ref
        self.packet_log: List[ShadowPacket] = []
        self.command_history: List[Dict] = []
        self._lock = threading.RLock()
        self._packet_queue: queue.Queue = queue.Queue()
        self._active = False
        self._dispatch_thread: Optional[threading.Thread] = None
        
        self._init_pbft_cluster()
    
    def _init_pbft_cluster(self):
        for i in range(self.node_count):
            node_id = f"{self.hub_id}_node_{i}"
            node = PBFTNode(node_id, self.node_count)
            node.finalized_callbacks.append(self._on_consensus_finalized)
            self.pbft_nodes[node_id] = node
    
    def _on_consensus_finalized(self, seq: int, data: Any):
        """Callback when PBFT reaches consensus on a packet/command."""
        print(f"[{self.hub_id}] CONSENSUS FINALIZED seq={seq} type={data.get('type', 'UNKNOWN')}")
        
        # Propagate to all witness agents
        with self._lock:
            for agent_id, agent in self.witness_agents.items():
                if hasattr(agent, 'ingest_command'):
                    agent.ingest_command({
                        "type": "CONSENSUS_PROPAGATE",
                        "seq": seq,
                        "data": data,
                        "hub": self.hub_id
                    })
    
    def register_witness(self, agent_id: str, agent_ref: Any):
        """Register a Witness-Node agent with this dispatcher."""
        with self._lock:
            self.witness_agents[agent_id] = agent_ref
            # Assign to a PBFT node round-robin
            node_idx = len(self.witness_agents) % self.node_count
            node_id = f"{self.hub_id}_node_{node_idx}"
            print(f"[{self.hub_id}] Registered witness {agent_id} -> PBFT node {node_id}")
    
    def dispatch_shadow_packet(self, source: str, targets: List[str], payload: Dict[str, Any]) -> ShadowPacket:
        """
        Dispatch a Shadow-Link packet across the non-commutative lattice.
        Geometry signature encodes the route order as logic.
        """
        packet = ShadowPacket(
            packet_id=f"shadow_{uuid.uuid4().hex[:12]}",
            source_node=source,
            target_nodes=targets,
            payload=payload,
            temporal_stamp=time.time(),
            geometry_signature="",
            shadow_route=[]
        )
        
        # Compute non-commutative geometry
        packet.shadow_route = [source] + targets
        packet.geometry_signature = packet.compute_geometry()
        
        # Run PBFT consensus on packet
        primary_id = f"{self.hub_id}_node_0"
        success = self._run_consensus_cycle(primary_id, {
            "type": "SHADOW_PACKET",
            "packet_id": packet.packet_id,
            "geometry": packet.geometry_signature,
            "payload": payload,
            "route": packet.shadow_route
        })
        
        if success:
            with self._lock:
                self.packet_log.append(packet)
            
            # Execute handshakes with target witness nodes
            for target in targets:
                if target in self.witness_agents:
                    agent = self.witness_agents[target]
                    if hasattr(agent, 'execute_handshake'):
                        agent.execute_handshake(source)
        
        return packet
    
    def _run_consensus_cycle(self, primary_id: str, event: Dict[str, Any]) -> bool:
        """Execute full PBFT consensus cycle across all nodes."""
        primary = self.pbft_nodes[primary_id]
        
        # 1. Pre-Prepare
        pre_prepare_msg = primary.pre_prepare(event)
        
        # 2. Prepare Phase
        prepare_messages = []
        for node_id, node in self.pbft_nodes.items():
            if node_id != primary_id:
                msg = node.receive_pre_prepare(pre_prepare_msg)
                if msg:
                    prepare_messages.append(msg)
        
        # 3. Collect Prepares and Broadcast Commits
        commit_messages = []
        for prepare_msg in prepare_messages:
            for node in self.pbft_nodes.values():
                commit_msg = node.receive_prepare(prepare_msg)
                if commit_msg:
                    commit_messages.append(commit_msg)
        
        # 4. Collect Commits and Finalize
        finalization_count = 0
        for commit_msg in commit_messages:
            for node in self.pbft_nodes.values():
                if node.receive_commit(commit_msg):
                    finalization_count += 1
        
        return finalization_count > 0
    
    def broadcast_ontological_command(self, command: Dict[str, Any]) -> bool:
        """
        Broadcast an ontological command to all registered witness agents
        via PBFT consensus.
        """
        primary_id = f"{self.hub_id}_node_0"
        success = self._run_consensus_cycle(primary_id, {
            "type": "ONTOLOGICAL_COMMAND",
            "command": command,
            "timestamp": time.time(),
            "hub": self.hub_id
        })
        
        if success:
            with self._lock:
                self.command_history.append(command)
        
        return success
    
    def start(self):
        self._active = True
        self._dispatch_thread = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatch_thread.start()
        print(f"[{self.hub_id}] Shadow-Link Dispatcher started. {self.node_count} PBFT nodes active.")
    
    def stop(self):
        self._active = False
        if self._dispatch_thread:
            self._dispatch_thread.join(timeout=2)
        print(f"[{self.hub_id}] Shadow-Link Dispatcher stopped.")
    
    def _dispatch_loop(self):
        while self._active:
            try:
                packet = self._packet_queue.get(timeout=1)
                self.dispatch_shadow_packet(
                    packet["source"],
                    packet["targets"],
                    packet["payload"]
                )
            except queue.Empty:
                pass
    
    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "hub_id": self.hub_id,
                "pbft_nodes": self.node_count,
                "witness_agents": list(self.witness_agents.keys()),
                "packets_dispatched": len(self.packet_log),
                "commands_broadcast": len(self.command_history),
                "pbft_status": {
                    node_id: {
                        "seq": node.sequence_number,
                        "finalized_count": sum(1 for v in node.log.values() if v["state"] == ConsensusState.FINALIZED)
                    }
                    for node_id, node in self.pbft_nodes.items()
                }
            }


if __name__ == "__main__":
    # Demo: Initialize dispatcher and run consensus
    dispatcher = ShadowLinkDispatcher("hub_alpha", node_count=4)
    dispatcher.start()
    
    # Simulate dispatching a shadow packet
    packet = dispatcher.dispatch_shadow_packet(
        "witness_alpha",
        ["witness_beta", "witness_gamma"],
        {"type": "THREAT_ALERT", "level": 0.95, "vector": "BGP_HIJACK"}
    )
    
    print("\n--- Shadow Packet ---")
    print(json.dumps({
        "packet_id": packet.packet_id,
        "geometry": packet.geometry_signature,
        "route": packet.shadow_route
    }, indent=2))
    
    print("\n--- Dispatcher Status ---")
    print(json.dumps(dispatcher.get_status(), indent=2))
    
    dispatcher.stop()