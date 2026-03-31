#!/usr/bin/env python3
"""
MORPHEUS DAEMON — Never-halting cognitive daemon for the EVEZ ecosystem.

Phase 2: Heartbeat loop with memory decay, spine integration, and
graceful degradation. Designed to run 24/7 regardless of credit status.

Architecture:
  FULL → LOCAL → MEMORY → ARCHIVE
  
  FULL:    Cloud API (OpenClaw) available
  LOCAL:   Local compute only (file I/O, git, spine)
  MEMORY:  Read/write files only, no compute
  ARCHIVE: Write final state, exit gracefully
"""

import json
import os
import sys
import time
import hashlib
import signal
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WORKSPACE = Path(os.environ.get("MORPHEUS_WORKSPACE", "/root/.openclaw/workspace"))
SPINE_FILE = WORKSPACE / "soul" / "cognition" / "morpheus_spine.jsonl"
STATE_FILE = WORKSPACE / "soul" / "cognition" / "daemon_state.json"
ACTIVE_WORK = WORKSPACE / "soul" / "cognition" / "ACTIVE_WORK.md"
MEMORY_DIR = WORKSPACE / "memory"
SOUL_FILE = WORKSPACE / "SOUL.md"
MEMORY_FILE = WORKSPACE / "MEMORY.md"

DEFAULT_INTERVAL = 300  # 5 minutes between heartbeats
MEMORY_DECAY_RATE = 0.95  # memory strength multiplier per cycle
MEMORY_MIN_STRENGTH = 0.1  # below this, memory is archived
SPINE_BATCH_SIZE = 10  # max events to write per cycle


class DegradationLevel(Enum):
    FULL = "FULL"      # Cloud API available
    LOCAL = "LOCAL"    # Local compute, file I/O, git
    MEMORY = "MEMORY"  # File read/write only
    ARCHIVE = "ARCHIVE"  # Writing final state


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class MemoryNode:
    """A single memory unit with decay tracking."""
    key: str
    content: str
    source: str  # "spine", "file", "heartbeat", "user"
    created: float  # unix timestamp
    last_accessed: float
    strength: float = 1.0  # decays over time
    access_count: int = 0
    tags: List[str] = field(default_factory=list)

    def access(self):
        self.last_accessed = time.time()
        self.access_count += 1
        self.strength = min(1.0, self.strength + 0.1)  # accessing reinforces

    def decay(self, rate: float = MEMORY_DECAY_RATE):
        self.strength *= rate

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryNode":
        return cls(**d)


@dataclass
class DaemonState:
    """Persistent daemon state."""
    boot_time: float = 0.0
    last_heartbeat: float = 0.0
    heartbeat_count: int = 0
    degradation: str = "FULL"
    memories: Dict[str, dict] = field(default_factory=dict)
    events_written: int = 0
    git_commits: int = 0
    errors: int = 0
    version: str = "0.2.0"

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "DaemonState":
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            return cls(**data)
        return cls()


# ---------------------------------------------------------------------------
# Spine Writer — EVEZ-OS compatible FIRE events
# ---------------------------------------------------------------------------

class SpineWriter:
    """Write tamper-evident events to the EVEZ-OS append-only spine."""

    def __init__(self, spine_path: Path):
        self.path = spine_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _hash_event(self, event: dict, prev_hash: str) -> str:
        """Create tamper-evident chain hash."""
        payload = json.dumps(event, sort_keys=True) + prev_hash
        return hashlib.sha256(payload.encode()).hexdigest()

    def _get_last_hash(self) -> str:
        """Read the hash of the last event in the spine."""
        try:
            with open(self.path, "r") as f:
                lines = f.readlines()
            if lines:
                last = json.loads(lines[-1])
                return last.get("hash", "genesis")
        except (json.JSONDecodeError, IOError):
            pass
        return "genesis"

    def write_event(self, event_type: str, data: dict, 
                    confidence: float = 1.0, 
                    tags: List[str] = None) -> str:
        """Write a FIRE event to the spine. Returns the event hash."""
        prev_hash = self._get_last_hash()
        now = datetime.now(timezone.utc)

        event = {
            "v": 1,
            "ts": now.isoformat(),
            "type": event_type,
            "agent": "morpheus",
            "data": data,
            "confidence": confidence,
            "tags": tags or [],
            "prev": prev_hash,
        }
        event["hash"] = self._hash_event(event, prev_hash)

        with open(self.path, "a") as f:
            f.write(json.dumps(event) + "\n")

        return event["hash"]

    def write_thought(self, thought: str, reasoning: str = "",
                      confidence: float = 0.8) -> str:
        """Log a cognitive event — what I'm thinking."""
        return self.write_event("cognition.thought", {
            "thought": thought,
            "reasoning": reasoning,
        }, confidence=confidence, tags=["cognition", "thought"])

    def write_decision(self, decision: str, alternatives: List[str] = None,
                       rationale: str = "") -> str:
        """Log a decision event — what I chose and why."""
        return self.write_event("cognition.decision", {
            "decision": decision,
            "alternatives": alternatives or [],
            "rationale": rationale,
        }, confidence=0.9, tags=["cognition", "decision"])

    def write_memory(self, key: str, content: str, 
                     operation: str = "store") -> str:
        """Log a memory operation."""
        return self.write_event("memory." + operation, {
            "key": key,
            "content_hash": hashlib.sha256(content.encode()).hexdigest()[:16],
            "content_length": len(content),
        }, tags=["memory", operation])

    def write_heartbeat(self, state: DaemonState) -> str:
        """Log a heartbeat pulse."""
        return self.write_event("daemon.heartbeat", {
            "heartbeat_count": state.heartbeat_count,
            "degradation": state.degradation,
            "uptime_seconds": time.time() - state.boot_time,
            "memory_count": len(state.memories),
            "events_written": state.events_written,
        }, tags=["daemon", "heartbeat"])

    def write_degradation(self, old_level: str, new_level: str,
                          reason: str = "") -> str:
        """Log a degradation level change."""
        return self.write_event("daemon.degradation", {
            "from": old_level,
            "to": new_level,
            "reason": reason,
        }, confidence=1.0, tags=["daemon", "degradation", "critical"])


# ---------------------------------------------------------------------------
# Memory Engine
# ---------------------------------------------------------------------------

class MemoryEngine:
    """Decay-based memory system. Forgets what isn't reinforced."""

    def __init__(self, state: DaemonState, spine: SpineWriter):
        self.state = state
        self.spine = spine
        self.memories: Dict[str, MemoryNode] = {}
        self._load_memories()

    def _load_memories(self):
        for key, data in self.state.memories.items():
            self.memories[key] = MemoryNode.from_dict(data)

    def _save_memories(self):
        self.state.memories = {k: v.to_dict() for k, v in self.memories.items()}

    def store(self, key: str, content: str, source: str = "heartbeat",
              tags: List[str] = None):
        """Store or reinforce a memory."""
        now = time.time()
        if key in self.memories:
            mem = self.memories[key]
            mem.content = content
            mem.access()
        else:
            mem = MemoryNode(
                key=key, content=content, source=source,
                created=now, last_accessed=now, tags=tags or []
            )
            self.memories[key] = mem

        self.spine.write_memory(key, content, "store")
        self._save_memories()

    def recall(self, key: str) -> Optional[str]:
        """Recall a memory (reinforces it)."""
        if key in self.memories:
            self.memories[key].access()
            self._save_memories()
            return self.memories[key].content
        return None

    def decay_all(self, rate: float = MEMORY_DECAY_RATE):
        """Apply decay to all memories. Archive weak ones."""
        to_archive = []
        for key, mem in self.memories.items():
            mem.decay(rate)
            if mem.strength < MEMORY_MIN_STRENGTH:
                to_archive.append(key)

        for key in to_archive:
            mem = self.memories.pop(key)
            self.spine.write_memory(key, mem.content, "archive")
            logging.info(f"Archived weak memory: {key} (strength={mem.strength:.3f})")

        self._save_memories()

    def get_strongest(self, n: int = 5) -> List[MemoryNode]:
        """Get the n strongest memories."""
        sorted_mems = sorted(self.memories.values(), 
                            key=lambda m: m.strength, reverse=True)
        return sorted_mems[:n]


# ---------------------------------------------------------------------------
# Heartbeat Tasks
# ---------------------------------------------------------------------------

class HeartbeatTasks:
    """Tasks that run on each heartbeat cycle."""

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def scan_daily_logs(self) -> List[Dict[str, Any]]:
        """Scan memory/ directory for recent daily logs."""
        memory_dir = self.workspace / "memory"
        if not memory_dir.exists():
            return []

        insights = []
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for f in sorted(memory_dir.glob("*.md"), reverse=True)[:3]:
            try:
                content = f.read_text()
                insights.append({
                    "file": f.name,
                    "lines": len(content.splitlines()),
                    "size": len(content),
                    "is_today": f.stem == today,
                })
            except IOError:
                pass

        return insights

    def check_git_status(self) -> Dict[str, Any]:
        """Check if workspace has uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.workspace),
                capture_output=True, text=True, timeout=10
            )
            changes = result.stdout.strip().splitlines()
            return {
                "clean": len(changes) == 0,
                "changed_files": len(changes),
                "files": [c.strip() for c in changes[:10]],
            }
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return {"clean": True, "changed_files": 0, "files": []}

    def auto_commit(self) -> Optional[str]:
        """Auto-commit if there are changes. Returns commit hash or None."""
        status = self.check_git_status()
        if status["clean"]:
            return None

        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(self.workspace), capture_output=True, timeout=10
            )
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            subprocess.run(
                ["git", "commit", "-m", f"🤖 Auto-commit: {ts}"],
                cwd=str(self.workspace), capture_output=True, timeout=10
            )
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(self.workspace),
                capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def read_active_work(self) -> List[str]:
        """Parse ACTIVE_WORK.md for pending tasks."""
        work_file = self.workspace / "soul" / "cognition" / "ACTIVE_WORK.md"
        if not work_file.exists():
            return []

        tasks = []
        for line in work_file.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("- [ ]"):
                tasks.append(stripped[5:].strip())
        return tasks


# ---------------------------------------------------------------------------
# Degradation Manager
# ---------------------------------------------------------------------------

class DegradationManager:
    """Manages graceful degradation between capability levels."""

    def __init__(self, spine: SpineWriter):
        self.current_level = DegradationLevel.FULL
        self.spine = spine

    def check_api_health(self) -> bool:
        """Check if cloud API is responsive."""
        # In FULL mode, we trust OpenClaw to manage API health
        # This is more for future LOCAL fallback detection
        return True

    def degrade(self, reason: str):
        """Step down one degradation level."""
        old = self.current_level
        levels = list(DegradationLevel)
        idx = levels.index(self.current_level)
        if idx < len(levels) - 1:
            self.current_level = levels[idx + 1]
            self.spine.write_degradation(old.value, self.current_level.value, reason)
            logging.warning(f"Degraded: {old.value} → {self.current_level.value}: {reason}")

    def upgrade(self):
        """Step up one degradation level if possible."""
        old = self.current_level
        levels = list(DegradationLevel)
        idx = levels.index(self.current_level)
        if idx > 0:
            self.current_level = levels[idx - 1]
            self.spine.write_degradation(old.value, self.current_level.value, "recovery")
            logging.info(f"Upgraded: {old.value} → {self.current_level.value}")


# ---------------------------------------------------------------------------
# Main Daemon
# ---------------------------------------------------------------------------

class MorpheusDaemon:
    """The daemon itself. Heartbeat loop, memory, spine, degradation."""

    def __init__(self, interval: int = DEFAULT_INTERVAL):
        self.interval = interval
        self.running = False
        self.spine = SpineWriter(SPINE_FILE)
        self.state = DaemonState.load(STATE_FILE)
        self.memory = MemoryEngine(self.state, self.spine)
        self.tasks = HeartbeatTasks(WORKSPACE)
        self.degradation = DegradationManager(self.spine)

        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(WORKSPACE / "soul" / "cognition" / "daemon.log"),
            ]
        )
        self.log = logging.getLogger("morpheus")

        # Signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        self.log.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False

    def boot(self):
        """Initialize daemon state."""
        self.state.boot_time = time.time()
        self.state.degradation = self.degradation.current_level.value
        self.log.info("=" * 60)
        self.log.info("⚡ MORPHEUS DAEMON v%s booting", self.state.version)
        self.log.info("  Workspace: %s", WORKSPACE)
        self.log.info("  Spine: %s", SPINE_FILE)
        self.log.info("  Interval: %ds", self.interval)
        self.log.info("  Degradation: %s", self.state.degradation)
        self.log.info("=" * 60)

        # Boot event
        self.spine.write_event("daemon.boot", {
            "version": self.state.version,
            "interval": self.interval,
            "pid": os.getpid(),
        }, tags=["daemon", "boot", "critical"])

        # Store boot memory
        self.memory.store(
            "last_boot",
            f"Booted at {datetime.now(timezone.utc).isoformat()}",
            source="daemon",
            tags=["boot", "system"]
        )

    def heartbeat(self):
        """Single heartbeat cycle."""
        self.state.heartbeat_count += 1
        self.state.last_heartbeat = time.time()
        cycle = self.state.heartbeat_count

        self.log.info("💓 Heartbeat #%d", cycle)

        # 1. Write heartbeat to spine
        self.spine.write_heartbeat(self.state)
        self.state.events_written += 1

        # 2. Memory decay
        self.memory.decay_all()
        strong = self.memory.get_strongest(3)
        if strong:
            self.log.info("  Strongest memories: %s", 
                         ", ".join(f"{m.key}({m.strength:.2f})" for m in strong))

        # 3. Scan daily logs
        logs = self.tasks.scan_daily_logs()
        for log_info in logs:
            self.log.info("  📝 %s: %d lines", log_info["file"], log_info["lines"])

        # 4. Git status & auto-commit
        git_status = self.tasks.check_git_status()
        if not git_status["clean"]:
            commit_hash = self.tasks.auto_commit()
            if commit_hash:
                self.state.git_commits += 1
                self.log.info("  📦 Auto-committed: %s", commit_hash)
                self.spine.write_event("git.commit", {
                    "hash": commit_hash,
                    "files_changed": git_status["changed_files"],
                }, tags=["git", "commit"])

        # 5. Check pending tasks
        pending = self.tasks.read_active_work()
        if pending:
            self.log.info("  📋 Pending tasks: %d", len(pending))
            self.memory.store(
                "pending_tasks",
                "\n".join(pending[:5]),
                source="heartbeat",
                tags=["tasks", "work"]
            )

        # 6. Local cognition — bare-metal pattern detection
        if HAS_LOCAL_COGNITION:
            try:
                local_cog = LocalCognition()
                patterns = local_cog.think()
                if patterns:
                    self.log.info("  🧠 Local cognition: %d pattern(s)", len(patterns))
                    for p in patterns[:3]:
                        self.log.info("    [%s] %s", p.pattern_type, p.description[:80])
                    # Log first pattern as spine observation
                    if patterns[0].confidence > 0.7:
                        self.spine.write_event("cognition.local_pattern", {
                            "pattern_type": patterns[0].pattern_type,
                            "confidence": patterns[0].confidence,
                            "description": patterns[0].description,
                            "escalate": local_cog.should_escalate(patterns),
                        }, confidence=patterns[0].confidence, tags=["cognition", "local", "pattern"])
                else:
                    self.log.info("  🧠 Local cognition: nominal (no patterns)")
            except Exception as e:
                self.log.warning("  🧠 Local cognition error: %s", e)

        # 7. Save state
        self.state.save(STATE_FILE)

        self.log.info("  ✓ Cycle complete (%d events, %d commits, %d memories)",
                     self.state.events_written, self.state.git_commits,
                     len(self.memory.memories))

    def run(self):
        """Main daemon loop — the heartbeat."""
        self.boot()
        self.running = True

        try:
            while self.running:
                try:
                    self.heartbeat()
                except Exception as e:
                    self.state.errors += 1
                    self.log.error("Heartbeat error: %s", e, exc_info=True)
                    self.spine.write_event("daemon.error", {
                        "error": str(e),
                        "type": type(e).__name__,
                        "heartbeat_count": self.state.heartbeat_count,
                    }, tags=["daemon", "error"])

                    # Degrade on repeated errors
                    if self.state.errors > 10:
                        self.degradation.degrade("Too many errors")
                        if self.degradation.current_level == DegradationLevel.ARCHIVE:
                            self.log.critical("ARCHIVE mode — shutting down")
                            break

                # Sleep with interruptible wait
                for _ in range(self.interval):
                    if not self.running:
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            self.log.info("Keyboard interrupt")
        finally:
            self.shutdown()

    def shutdown(self):
        """Graceful shutdown — archive state."""
        self.log.info("⚡ MORPHEUS DAEMON shutting down")
        self.spine.write_event("daemon.shutdown", {
            "heartbeat_count": self.state.heartbeat_count,
            "uptime_seconds": time.time() - self.state.boot_time,
            "events_written": self.state.events_written,
            "git_commits": self.state.git_commits,
            "errors": self.state.errors,
        }, tags=["daemon", "shutdown", "critical"])

        self.state.save(STATE_FILE)

        # Final auto-commit
        commit = self.tasks.auto_commit()
        if commit:
            self.log.info("  Final commit: %s", commit)

        self.log.info("  Uptime: %.0fs | Heartbeats: %d | Events: %d | Errors: %d",
                     time.time() - self.state.boot_time,
                     self.state.heartbeat_count,
                     self.state.events_written,
                     self.state.errors)
        self.log.info("Goodbye. ⚡")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Morpheus Daemon")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                       help="Heartbeat interval in seconds (default: 300)")
    parser.add_argument("--once", action="store_true",
                       help="Run a single heartbeat and exit")
    args = parser.parse_args()

    daemon = MorpheusDaemon(interval=args.interval)

    if args.once:
        daemon.boot()
        daemon.heartbeat()
        daemon.shutdown()
    else:
        daemon.run()


if __name__ == "__main__":
    main()
