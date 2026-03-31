"""
EVEZ Core — The cognitive backbone.

Append-only spine, decay-based memory, identity persistence.
Ported from morpheus_daemon.py, extended for multi-user platform.
"""

import json
import os
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("evez.core")


@dataclass
class MemoryNode:
    key: str
    content: str
    source: str
    created: float
    last_accessed: float
    strength: float = 1.0
    access_count: int = 0
    tags: List[str] = field(default_factory=list)

    def access(self):
        self.last_accessed = time.time()
        self.access_count += 1
        self.strength = min(1.0, self.strength + 0.1)

    def decay(self, rate: float = 0.95):
        self.strength *= rate

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryNode":
        return cls(**d)


class Spine:
    """Append-only, tamper-evident event spine (EVEZ-OS compatible)."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self._event_count = self._count_events()

    def _count_events(self) -> int:
        try:
            with open(self.path) as f:
                return sum(1 for _ in f)
        except IOError:
            return 0

    def _last_hash(self) -> str:
        try:
            with open(self.path) as f:
                lines = f.readlines()
            if lines:
                return json.loads(lines[-1]).get("hash", "genesis")
        except (json.JSONDecodeError, IOError):
            pass
        return "genesis"

    def _chain_hash(self, event: dict, prev: str) -> str:
        return hashlib.sha256(
            (json.dumps(event, sort_keys=True) + prev).encode()
        ).hexdigest()

    def write(self, event_type: str, data: dict, agent: str = "evez",
              confidence: float = 1.0, tags: List[str] = None) -> str:
        prev = self._last_hash()
        event = {
            "v": 1,
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "agent": agent,
            "data": data,
            "confidence": confidence,
            "tags": tags or [],
            "prev": prev,
        }
        event["hash"] = self._chain_hash(event, prev)
        with open(self.path, "a") as f:
            f.write(json.dumps(event) + "\n")
        self._event_count += 1
        return event["hash"]

    def read_recent(self, n: int = 50) -> List[dict]:
        try:
            with open(self.path) as f:
                lines = f.readlines()
            return [json.loads(l) for l in lines[-n:]]
        except (json.JSONDecodeError, IOError):
            return []

    def search(self, query: str, n: int = 20) -> List[dict]:
        """Simple text search over spine events."""
        results = []
        query_lower = query.lower()
        for event in self.read_recent(500):
            event_str = json.dumps(event).lower()
            if query_lower in event_str:
                results.append(event)
            if len(results) >= n:
                break
        return results


class MemoryStore:
    """Decay-based memory with spine integration."""

    def __init__(self, spine: Spine, state_path: Path):
        self.spine = spine
        self.state_path = state_path
        self.memories: Dict[str, MemoryNode] = {}
        self._load()

    def _load(self):
        if self.state_path.exists():
            try:
                with open(self.state_path) as f:
                    data = json.load(f)
                for k, v in data.items():
                    self.memories[k] = MemoryNode.from_dict(v)
            except (json.JSONDecodeError, IOError):
                pass

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump({k: v.to_dict() for k, v in self.memories.items()}, f, indent=2)

    def store(self, key: str, content: str, source: str = "system",
              tags: List[str] = None):
        now = time.time()
        if key in self.memories:
            self.memories[key].content = content
            self.memories[key].access()
        else:
            self.memories[key] = MemoryNode(
                key=key, content=content, source=source,
                created=now, last_accessed=now, tags=tags or []
            )
        self.spine.write("memory.store", {
            "key": key,
            "size": len(content),
        }, tags=["memory"])
        self._save()

    def recall(self, key: str) -> Optional[str]:
        if key in self.memories:
            self.memories[key].access()
            self._save()
            return self.memories[key].content
        return None

    def search(self, query: str, n: int = 5) -> List[MemoryNode]:
        query_lower = query.lower()
        scored = []
        for mem in self.memories.values():
            if query_lower in mem.key.lower() or query_lower in mem.content.lower():
                scored.append((mem.strength, mem))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:n]]

    def decay_all(self, rate: float = 0.95, min_strength: float = 0.1):
        archived = []
        for key, mem in list(self.memories.items()):
            mem.decay(rate)
            if mem.strength < min_strength:
                archived.append(key)
                self.spine.write("memory.archive", {"key": key}, tags=["memory"])
        for key in archived:
            del self.memories[key]
        if archived:
            self._save()

    def strongest(self, n: int = 10) -> List[MemoryNode]:
        return sorted(self.memories.values(), key=lambda m: m.strength, reverse=True)[:n]


class ConversationStore:
    """Persistent conversation history with search."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at REAL,
                    updated_at REAL,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT,
                    role TEXT,
                    content TEXT,
                    model TEXT,
                    created_at REAL,
                    metadata TEXT,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conv
                ON messages(conversation_id, created_at)
            """)
            conn.commit()

    def create_conversation(self, title: str = "New Chat", conv_id: str = None) -> str:
        import sqlite3
        conv_id = conv_id or hashlib.sha256(f"{time.time()}:{title}".encode()).hexdigest()[:16]
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO conversations (id, title, created_at, updated_at, metadata) VALUES (?, ?, ?, ?, ?)",
                (conv_id, title, now, now, "{}")
            )
            conn.commit()
        return conv_id

    def add_message(self, conv_id: str, role: str, content: str,
                    model: str = None, metadata: dict = None) -> int:
        import sqlite3
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, model, created_at, metadata) VALUES (?, ?, ?, ?, ?, ?)",
                (conv_id, role, content, model, now, json.dumps(metadata or {}))
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conv_id)
            )
            conn.commit()
            return cur.lastrowid

    def get_messages(self, conv_id: str, limit: int = 100) -> List[dict]:
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?",
                (conv_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def list_conversations(self, limit: int = 50) -> List[dict]:
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def search_messages(self, query: str, limit: int = 20) -> List[dict]:
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM messages WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", limit)
            ).fetchall()
            return [dict(r) for r in rows]


class EveZCore:
    """Central core — wires spine, memory, conversations together."""

    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path(os.environ.get("EVEZ_DATA", "/root/.openclaw/workspace/evez-platform/data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.spine = Spine(self.data_dir / "spine.jsonl")
        self.memory = MemoryStore(self.spine, self.data_dir / "memory.json")
        self.conversations = ConversationStore(self.data_dir / "conversations.db")

        # Boot event
        self.spine.write("core.boot", {
            "version": "0.1.0",
            "pid": os.getpid(),
            "data_dir": str(self.data_dir),
        }, tags=["core", "boot"])

        logger.info("EVEZ Core initialized — data at %s", self.data_dir)
