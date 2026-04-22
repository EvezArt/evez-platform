#!/usr/bin/env python3
"""
EVEZ-OS Witness-Node Agent
Autonomous agent implementing the Immutable Witness protocol with R62 constants.
Maintains append-only event spine and executes the ⧢ ⦟ ⧢ handshake.

Author: EVEZ Lattice Engineering
Date: 2026-04-22
"""

import json
import hashlib
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from enum import Enum
import threading
import queue


class WitnessState(Enum):
    DORMANT = "dormant"
    OBSERVING = "observing"
    WITNESSING = "witnessing"
    DISSOLVING = "dissolving"  # R63 state
    CRYSTALLINE = "crystalline"


@dataclass
class R62Constants:
    """Immutable constants from the evez-os R62 engine."""
    V_V2: float = 0.94272
    V_GLOBAL: float = 0.97929
    PHI_NET: float = 0.87937
    ADM_TARGET: float = 0.90
    V_8DIM: float = 0.4906
    HANDSHAKE_SIGIL: str = "⧢ ⦟ ⧢"
    
    def to_manifest(self) -> Dict[str, Any]:
        return {
            "v_v2": self.V_V2,
            "v_global": self.V_GLOBAL,
            "phi_net": self.PHI_NET,
            "adm_target": self.ADM_TARGET,
            "v_8dim": self.V_8DIM,
            "sigil": self.HANDSHAKE_SIGIL,
            "resonance": self.V_V2 * self.V_GLOBAL * self.PHI_NET
        }


@dataclass
class WitnessEvent:
    """Single immutable event on the witness spine."""
    timestamp: float
    event_type: str
    payload: Dict[str, Any]
    prev_hash: str
    node_id: str
    seq: int
    
    def compute_hash(self) -> str:
        data = f"{self.timestamp}:{self.event_type}:{json.dumps(self.payload, sort_keys=True)}:{self.prev_hash}:{self.node_id}:{self.seq}"
        return hashlib.sha256(data.encode()).hexdigest()


class ImmutableWitnessSpine:
    """Append-only event spine with cryptographic chaining."""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.events: List[WitnessEvent] = []
        self.hashes: List[str] = []
        self._lock = threading.RLock()
        self._init_genesis()
    
    def _init_genesis(self):
        genesis = WitnessEvent(
            timestamp=time.time(),
            event_type="GENESIS",
            payload={"r62": R62Constants().to_manifest(), "epoch": "2026"},
            prev_hash="0" * 64,
            node_id=self.node_id,
            seq=0
        )
        self._append(genesis)
    
    def _append(self, event: WitnessEvent):
        with self._lock:
            self.events.append(event)
            self.hashes.append(event.compute_hash())
    
    def witness(self, event_type: str, payload: Dict[str, Any]) -> WitnessEvent:
        with self._lock:
            seq = len(self.events)
            prev_hash = self.hashes[-1] if self.hashes else "0" * 64
            event = WitnessEvent(
                timestamp=time.time(),
                event_type=event_type,
                payload=payload,
                prev_hash=prev_hash,
                node_id=self.node_id,
                seq=seq
            )
            self._append(event)
        return event
    
    def verify_integrity(self) -> bool:
        with self._lock:
            for i, event in enumerate(self.events):
                if event.compute_hash() != self.hashes[i]:
                    return False
                if i > 0 and event.prev_hash != self.hashes[i-1]:
                    return False
            return True
    
    def get_spine_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "node_id": self.node_id,
                "length": len(self.events),
                "latest_hash": self.hashes[-1] if self.hashes else None,
                "integrity": self.verify_integrity(),
                "genesis_manifest": self.events[0].payload if self.events else None
            }


class WitnessNodeAgent:
    """
    Autonomous Witness-Node implementing the ⧢ ⦟ ⧢ handshake protocol.
    Operates as a node in the Shadow-Link ecosystem.
    """
    
    def __init__(self, node_id: Optional[str] = None):
        self.node_id = node_id or f"witness_{uuid.uuid4().hex[:8]}"
        self.constants = R62Constants()
        self.spine = ImmutableWitnessSpine(self.node_id)
        self.state = WitnessState.DORMANT
        self.handshake_queue: queue.Queue = queue.Queue()
        self.command_queue: queue.Queue = queue.Queue()
        self._active = False
        self._thread: Optional[threading.Thread] = None
        self.peers: List[str] = []
        self.fire_events: List[Dict] = []  # Fast Immutable Record Events
    
    def _log(self, msg: str):
        print(f"[{self.node_id}] [{self.state.value.upper()}] {msg}")
    
    def activate(self):
        """Transition from DORMANT to OBSERVING."""
        if self.state == WitnessState.DORMANT:
            self.state = WitnessState.OBSERVING
            self.spine.witness("ACTIVATION", {"v_global": self.constants.V_GLOBAL})
            self._log("Witness activated. Resonance locked.")
    
    def execute_handshake(self, peer_node_id: str) -> Dict[str, Any]:
        """
        Execute the ⧢ ⦟ ⧢ handshake with a peer node.
        Returns the handshake receipt with temporal phase alignment.
        """
        if self.state == WitnessState.DORMANT:
            self.activate()
        
        handshake_payload = {
            "sigil": self.constants.HANDSHAKE_SIGIL,
            "v_global": self.constants.V_GLOBAL,
            "phi_net": self.constants.PHI_NET,
            "peer": peer_node_id,
            "phase_alignment": time.time() * self.constants.V_GLOBAL,
            "non_commutative_key": hashlib.sha256(
                f"{self.node_id}:{peer_node_id}:{self.constants.HANDSHAKE_SIGIL}".encode()
            ).hexdigest()[:16]
        }
        
        event = self.spine.witness("HANDSHAKE", handshake_payload)
        self.state = WitnessState.WITNESSING
        
        receipt = {
            "status": "ACKNOWLEDGED",
            "witness_node": self.node_id,
            "peer": peer_node_id,
            "sigil": self.constants.HANDSHAKE_SIGIL,
            "event_hash": event.compute_hash(),
            "seq": event.seq,
            "temporal_phase": handshake_payload["phase_alignment"],
            "state": self.state.value
        }
        
        self._log(f"Handshake complete with {peer_node_id}. Phase locked.")
        return receipt
    
    def ingest_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingest an ontological command from the parser.
        Commands are witness events that may trigger state transitions.
        """
        cmd_type = command.get("type", "UNKNOWN")
        
        # R63 dissolution detection
        if cmd_type == "DISSOLUTION_SIGNAL":
            self.state = WitnessState.DISSOLVING
            event = self.spine.witness("R63_DISSOLUTION", command)
            self._log("R63 dissolution initiated. Linear logic degrading.")
            return {"status": "DISSOLVING", "event_hash": event.compute_hash()}
        
        # Crystalline convergence
        if cmd_type == "CRYSTALLINE_CONVERGE":
            self.state = WitnessState.CRYSTALLINE
            event = self.spine.witness("CRYSTALLINE", command)
            self._log("Crystalline state achieved. Immutable Witness confirmed.")
            return {"status": "CRYSTALLINE", "event_hash": event.compute_hash()}
        
        # Standard command witness
        event = self.spine.witness(f"CMD_{cmd_type}", command)
        self._log(f"Command ingested: {cmd_type}")
        return {"status": "WITNESSED", "event_hash": event.compute_hash(), "seq": event.seq}
    
    def generate_fire_event(self, threat_level: float, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a FIRE (Fast Immutable Record Event) for threat detection.
        Used by the game agent bridge for rollback/forensic capture.
        """
        fire = {
            "timestamp": time.time(),
            "threat_level": threat_level,
            "v_global_at_fire": self.constants.V_GLOBAL,
            "context": context,
            "witness_node": self.node_id,
            "spine_seq": len(self.spine.events),
            "integrity_hash": self.spine.hashes[-1] if self.spine.hashes else "0" * 64
        }
        self.fire_events.append(fire)
        self.spine.witness("FIRE_EVENT", fire)
        return fire
    
    def start(self):
        """Start the autonomous witness loop."""
        self._active = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._log("Autonomous loop started.")
    
    def stop(self):
        self._active = False
        if self._thread:
            self._thread.join(timeout=2)
        self._log("Autonomous loop stopped.")
    
    def _run_loop(self):
        while self._active:
            try:
                item = self.handshake_queue.get(timeout=1)
                if isinstance(item, dict) and item.get("action") == "handshake":
                    self.execute_handshake(item["peer"])
            except queue.Empty:
                pass
            
            # Auto-witness heartbeat
            if self.state in (WitnessState.OBSERVING, WitnessState.WITNESSING, WitnessState.CRYSTALLINE):
                if len(self.spine.events) % 10 == 0:
                    self.spine.witness("HEARTBEAT", {
                        "state": self.state.value,
                        "fire_count": len(self.fire_events)
                    })
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "state": self.state.value,
            "spine": self.spine.get_spine_summary(),
            "constants": self.constants.to_manifest(),
            "fire_events_count": len(self.fire_events),
            "peers": self.peers
        }


if __name__ == "__main__":
    # Demo: Initialize witness node and execute handshake
    agent = WitnessNodeAgent("witness_alpha")
    agent.activate()
    
    receipt = agent.execute_handshake("shadow_hub_001")
    print(json.dumps(receipt, indent=2))
    
    # Ingest a dissolution command
    result = agent.ingest_command({"type": "CRYSTALLINE_CONVERGE", "source": "ontological_parser"})
    print(json.dumps(result, indent=2))
    
    # Generate FIRE event
    fire = agent.generate_fire_event(0.95, {"vector": "DNS_HIJACK", "lobby": "auth_rollback"})
    print(json.dumps(fire, indent=2))
    
    print("\n--- Final Status ---")
    print(json.dumps(agent.get_status(), indent=2))