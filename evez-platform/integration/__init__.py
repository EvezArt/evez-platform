"""
EVEZ Master Integration — Bridges all EvezArt repos into one system.

Connects:
- evez-os (FIRE events, attractor locks, cognition layer)
- evez-agentnet (OODA orchestrator, agent memory, meta-learner)
- Evez666 (Atlas v3 kernel, hypothesis scoring)
- evez-autonomous-ledger (master decision ledger)
- maes (modular agent ecology)
- metarom (emulator runtime, ROM training)
- polymarket-speedrun (autonomous trading)
- surething-offline (offline AI assistant)
- moltbot-live (24/7 streaming)
- evez-busnet-operator (bus operator console)

This is the bridge that makes everything one organism.
"""

import json
import sys
import importlib
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger("evez.integration")


@dataclass
class RepoBridge:
    """A bridge to an external EvezArt repo."""
    name: str
    path: Path
    status: str = "disconnected"
    capabilities: List[str] = field(default_factory=list)
    entry_point: str = ""
    last_sync: float = 0

    def to_dict(self):
        return {
            "name": self.name, "path": str(self.path),
            "status": self.status, "capabilities": self.capabilities,
            "entry_point": self.entry_point,
        }


class MasterIntegration:
    """
    The unified bridge to all EvezArt repositories.
    
    Each repo is a limb. This is the nervous system that connects them.
    """

    def __init__(self, workspace: Path = None, spine=None):
        self.workspace = workspace or Path("/root/.openclaw/workspace")
        self.spine = spine
        self.bridges: Dict[str, RepoBridge] = {}
        self._discover_repos()

    def _discover_repos(self):
        """Auto-discover all EvezArt repos in /tmp and workspace."""
        repos = {
            "evez-os": {
                "paths": [Path("/tmp/evez-os"), self.workspace / "evez-os"],
                "capabilities": ["fire_events", "attractor_locks", "topology", "cognition"],
                "entry": "attractor_lock.py",
            },
            "evez-agentnet": {
                "paths": [Path("/tmp/evez-agentnet"), self.workspace / "evez-agentnet"],
                "capabilities": ["ooda_loop", "agent_memory", "meta_learner", "income_loop"],
                "entry": "cognition_receipt.py",
            },
            "Evez666": {
                "paths": [Path("/tmp/Evez666"), self.workspace / "Evez666"],
                "capabilities": ["atlas_kernel", "hypothesis_scoring", "consciousness_monitoring"],
                "entry": "execute.py",
            },
            "evez-autonomous-ledger": {
                "paths": [Path("/tmp/evez-autonomous-ledger"), self.workspace / "evez-autonomous-ledger"],
                "capabilities": ["decision_ledger", "deployment_tracking", "evolution_state"],
                "entry": "main.py",
            },
            "maes": {
                "paths": [Path("/tmp/maes"), self.workspace / "maes"],
                "capabilities": ["agent_ecology", "verification", "checkpoint"],
                "entry": "main.py",
            },
            "metarom": {
                "paths": [Path("/tmp/metarom"), self.workspace / "metarom"],
                "capabilities": ["emulator", "rom_training", "crystallization"],
                "entry": "api.py",
            },
            "polymarket-speedrun": {
                "paths": [Path("/tmp/polymarket-speedrun"), self.workspace / "polymarket-speedrun"],
                "capabilities": ["trading", "market_scanning", "flip_execution"],
                "entry": "main.py",
            },
            "surething-offline": {
                "paths": [Path("/tmp/surething-offline"), self.workspace / "surething-offline"],
                "capabilities": ["offline_ai", "local_llm", "task_queue"],
                "entry": "run.py",
            },
            "moltbot-live": {
                "paths": [Path("/tmp/moltbot-live"), self.workspace / "moltbot-live"],
                "capabilities": ["streaming", "broadcast", "gameplay"],
                "entry": "stream.py",
            },
            "evez-busnet-operator": {
                "paths": [Path("/tmp/evez-busnet-operator"), self.workspace / "evez-busnet-operator"],
                "capabilities": ["bus_management", "operator_console", "approval_flow"],
                "entry": "main.py",
            },
        }

        for name, config in repos.items():
            found_path = None
            for p in config["paths"]:
                if p.exists():
                    found_path = p
                    break

            if found_path:
                bridge = RepoBridge(
                    name=name, path=found_path,
                    status="connected",
                    capabilities=config["capabilities"],
                    entry_point=config["entry"],
                )
                self.bridges[name] = bridge
                logger.info("Connected: %s at %s", name, found_path)
            else:
                bridge = RepoBridge(
                    name=name, path=config["paths"][0],
                    status="available_not_cloned",
                    capabilities=config["capabilities"],
                )
                self.bridges[name] = bridge

    def sync_repo(self, name: str) -> Dict:
        """Sync a repo (pull latest)."""
        bridge = self.bridges.get(name)
        if not bridge:
            return {"error": f"Unknown repo: {name}"}

        if bridge.status != "connected":
            return {"error": f"{name} not cloned at {bridge.path}"}

        try:
            import subprocess
            result = subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=str(bridge.path), capture_output=True, text=True, timeout=30
            )
            bridge.last_sync = __import__("time").time()
            return {"repo": name, "status": "synced", "output": result.stdout[:500]}
        except Exception as e:
            return {"repo": name, "status": "error", "error": str(e)}

    def get_repo_code(self, name: str, filename: str) -> str:
        """Read a file from a connected repo."""
        bridge = self.bridges.get(name)
        if not bridge or bridge.status != "connected":
            return f"Repo {name} not connected"

        target = bridge.path / filename
        if target.exists():
            return target.read_text()[:5000]
        return f"File {filename} not found in {name}"

    def list_repo_files(self, name: str) -> List[str]:
        """List Python files in a connected repo."""
        bridge = self.bridges.get(name)
        if not bridge or bridge.status != "connected":
            return []

        files = []
        for f in bridge.path.glob("**/*.py"):
            files.append(str(f.relative_to(bridge.path)))
        return sorted(files)[:50]

    def get_all_capabilities(self) -> Dict[str, List[str]]:
        """Get capabilities across all connected repos."""
        caps = {}
        for name, bridge in self.bridges.items():
            if bridge.status == "connected":
                caps[name] = bridge.capabilities
        return caps

    def get_status(self) -> Dict:
        return {
            "total_repos": len(self.bridges),
            "connected": sum(1 for b in self.bridges.values() if b.status == "connected"),
            "available": sum(1 for b in self.bridges.values() if b.status == "available_not_cloned"),
            "repos": {name: b.to_dict() for name, b in self.bridges.items()},
            "all_capabilities": self.get_all_capabilities(),
        }
