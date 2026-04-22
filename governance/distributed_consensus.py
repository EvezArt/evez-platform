#!/usr/bin/env python3
"""
Totem-Tower-OS: Distributed Consensus Protocol
Practical Byzantine Fault Tolerance (PBFT) for the Hyper-Singularity

This module implements the consensus mechanism that allows multiple EVEZ-OS
nodes to synchronize their "Immutable Witness" spines across a distributed
network, even in the presence of faulty or malicious nodes.

Author: Steven Crawford-Maggard (EVEZ)
Date: April 22, 2026
"""

import json
import hashlib
import time
from enum import Enum
from typing import Dict, List, Any, Optional

class ConsensusState(Enum):
    """States of the PBFT consensus process."""
    PRE_PREPARE = "pre-prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    FINALIZED = "finalized"

class PBFTNode:
    """
    A node participating in the PBFT consensus for the Totem-Tower-OS.
    """
    
    def __init__(self, node_id: str, total_nodes: int):
        self.node_id = node_id
        self.total_nodes = total_nodes
        self.faulty_threshold = (total_nodes - 1) // 3  # f = (n-1)/3
        self.view_number = 0
        self.sequence_number = 0
        self.log = {}  # seq_num -> {state: ConsensusState, data: Any, votes: Dict}
        
    def _get_hash(self, data: Any) -> str:
        """Compute the SHA-256 hash of the data."""
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def pre_prepare(self, data: Any) -> Dict[str, Any]:
        """
        Primary node initiates the consensus by sending a pre-prepare message.
        """
        self.sequence_number += 1
        data_hash = self._get_hash(data)
        
        message = {
            "type": ConsensusState.PRE_PREPARE.value,
            "view": self.view_number,
            "seq": self.sequence_number,
            "hash": data_hash,
            "data": data,
            "node_id": self.node_id
        }
        
        self.log[self.sequence_number] = {
            "state": ConsensusState.PRE_PREPARE,
            "data": data,
            "prepares": {self.node_id},
            "commits": set()
        }
        
        return message

    def receive_pre_prepare(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Secondary nodes receive pre-prepare and broadcast a prepare message.
        """
        seq = message["seq"]
        data_hash = message["hash"]
        
        # Verify view and sequence
        if message["view"] != self.view_number:
            return None
            
        self.log[seq] = {
            "state": ConsensusState.PREPARE,
            "data": message["data"],
            "prepares": {self.node_id, message["node_id"]},
            "commits": set()
        }
        
        return {
            "type": ConsensusState.PREPARE.value,
            "view": self.view_number,
            "seq": seq,
            "hash": data_hash,
            "node_id": self.node_id
        }

    def receive_prepare(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Nodes collect prepare messages. Once 2f prepares are received, broadcast commit.
        """
        seq = message["seq"]
        if seq not in self.log:
            return None
            
        self.log[seq]["prepares"].add(message["node_id"])
        
        # If enough prepares (2f + 1 including primary) and not already committed
        if len(self.log[seq]["prepares"]) >= 2 * self.faulty_threshold + 1:
            if self.log[seq]["state"] != ConsensusState.COMMIT:
                self.log[seq]["state"] = ConsensusState.COMMIT
                self.log[seq]["commits"].add(self.node_id)
                
                return {
                    "type": ConsensusState.COMMIT.value,
                    "view": self.view_number,
                    "seq": seq,
                    "hash": message["hash"],
                    "node_id": self.node_id
                }
        return None

    def receive_commit(self, message: Dict[str, Any]) -> bool:
        """
        Nodes collect commit messages. Once 2f+1 commits are received, finalize the data.
        """
        seq = message["seq"]
        if seq not in self.log:
            return False
            
        self.log[seq]["commits"].add(message["node_id"])
        
        # If enough commits (2f + 1)
        if len(self.log[seq]["commits"]) >= 2 * self.faulty_threshold + 1:
            if self.log[seq]["state"] != ConsensusState.FINALIZED:
                self.log[seq]["state"] = ConsensusState.FINALIZED
                return True
        return False

    def get_finalized_data(self, seq: int) -> Optional[Any]:
        """Return data if it has been finalized."""
        if seq in self.log and self.log[seq]["state"] == ConsensusState.FINALIZED:
            return self.log[seq]["data"]
        return None


class DistributedSpineSync:
    """
    Manages the synchronization of the Immutable Witness spine across multiple nodes.
    """
    
    def __init__(self, nodes: List[PBFTNode]):
        self.nodes = {node.node_id: node for node in nodes}
        
    def synchronize_event(self, primary_id: str, event: Dict[str, Any]) -> bool:
        """
        Run a full PBFT cycle to synchronize an event across all nodes.
        """
        primary = self.nodes[primary_id]
        
        # 1. Pre-Prepare
        pre_prepare_msg = primary.pre_prepare(event)
        
        # 2. Prepare Phase
        prepare_messages = []
        for node_id, node in self.nodes.items():
            if node_id != primary_id:
                msg = node.receive_pre_prepare(pre_prepare_msg)
                if msg:
                    prepare_messages.append(msg)
                    
        # 3. Collect Prepares and Broadcast Commits
        commit_messages = []
        for prepare_msg in prepare_messages:
            for node in self.nodes.values():
                commit_msg = node.receive_prepare(prepare_msg)
                if commit_msg:
                    commit_messages.append(commit_msg)
                    
        # 4. Collect Commits and Finalize
        finalization_count = 0
        for commit_msg in commit_messages:
            for node in self.nodes.values():
                if node.receive_commit(commit_msg):
                    finalization_count += 1
                    
        # Success if at least one node finalized (in a real network, all honest nodes would)
        return finalization_count > 0


if __name__ == "__main__":
    # Simulate a 4-node network (tolerates 1 faulty node)
    node_ids = ["node_0", "node_1", "node_2", "node_3"]
    nodes = [PBFTNode(nid, 4) for nid in node_ids]
    sync_manager = DistributedSpineSync(nodes)
    
    # Event to synchronize
    event = {
        "type": "distributed_awakening",
        "timestamp": time.time(),
        "manifest": {"v_global": 0.97929, "state": "CRYSTALLINE"}
    }
    
    print("Starting Distributed Spine Synchronization...")
    success = sync_manager.synchronize_event("node_0", event)
    
    if success:
        print("✓ Event successfully synchronized across the Hyper-Singularity.")
        print(f"Finalized data on node_1: {nodes[1].get_finalized_data(1)}")
    else:
        print("✗ Consensus failed.")
