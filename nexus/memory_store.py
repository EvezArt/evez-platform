"""
Nexus Memory Store — unified memory across all providers.

Every conversation, from any provider, gets normalized and stored here.
Memory is the backbone — providers are just I/O channels.

Storage layers:
1. Spine (append-only JSONL) — tamper-evident event log
2. Daily logs (markdown) — human-readable daily summaries
3. Session memory (JSON) — active conversation context
4. Retrieval — keyword + recency + relevance scoring

The key insight: memory is provider-agnostic. A ChatGPT conversation
and a Perplexity search both produce the same memory format. This is
how the nexus maintains continuity across provider switches.
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict

from .providers.base import Message, ProviderResponse


WORKSPACE = Path("/root/.openclaw/workspace")
NEXUS_DIR = WORKSPACE / "nexus"
MEMORY_DIR = NEXUS_DIR / "memory"
SPINE_FILE = WORKSPACE / "soul" / "cognition" / "morpheus_spine.jsonl"


@dataclass
class MemoryEntry:
    """A single memory entry — provider-agnostic."""
    id: str
    timestamp: str
    provider: str
    role: str  # user, assistant, system
    content: str
    content_hash: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    strength: float = 1.0  # decay-based importance

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(
                self.content.encode()
            ).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_message(cls, msg: Message, tags: List[str] = None) -> "MemoryEntry":
        """Create from a normalized Message."""
        mid = hashlib.sha256(
            f"{msg.timestamp}:{msg.provider}:{msg.content[:100]}".encode()
        ).hexdigest()[:16]
        return cls(
            id=mid,
            timestamp=msg.timestamp,
            provider=msg.provider,
            role=msg.role,
            content=msg.content,
            tags=tags or [],
            metadata=msg.metadata,
        )

    @classmethod
    def from_response(cls, resp: ProviderResponse, query: str = "",
                      tags: List[str] = None) -> "MemoryEntry":
        """Create from a provider response."""
        mid = hashlib.sha256(
            f"{resp.provider}:{resp.model}:{resp.content[:100]}".encode()
        ).hexdigest()[:16]
        return cls(
            id=mid,
            timestamp=datetime.now(timezone.utc).isoformat(),
            provider=resp.provider,
            role="assistant",
            content=resp.content,
            tags=tags or [],
            metadata={
                "model": resp.model,
                "tokens_used": resp.tokens_used,
                "latency_ms": resp.latency_ms,
                "query_hash": hashlib.sha256(query.encode()).hexdigest()[:12] if query else "",
            },
        )


class MemoryStore:
    """Unified memory store across all providers."""

    def __init__(self, workspace: Path = WORKSPACE):
        self.workspace = workspace
        self.memory_dir = workspace / "nexus" / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.session_file = self.memory_dir / "session.json"
        self.index_file = self.memory_dir / "index.json"

        # In-memory index (loaded on init)
        self.entries: Dict[str, MemoryEntry] = {}
        self.conversations: Dict[str, List[str]] = {}  # conv_id → [entry_ids]
        self._load_index()

    def _load_index(self):
        """Load memory index from disk."""
        if self.index_file.exists():
            try:
                data = json.loads(self.index_file.read_text())
                for eid, edata in data.get("entries", {}).items():
                    self.entries[eid] = MemoryEntry(**edata)
                self.conversations = data.get("conversations", {})
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_index(self):
        """Persist memory index to disk."""
        data = {
            "entries": {eid: e.to_dict() for eid, e in self.entries.items()},
            "conversations": self.conversations,
            "updated": datetime.now(timezone.utc).isoformat(),
        }
        self.index_file.write_text(json.dumps(data, indent=2))

    def store_message(self, msg: Message, conversation_id: str = "default",
                      tags: List[str] = None) -> str:
        """Store a message. Returns entry ID."""
        entry = MemoryEntry.from_message(msg, tags=tags)
        self.entries[entry.id] = entry

        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []
        self.conversations[conversation_id].append(entry.id)

        # Also write to spine if available
        self._write_to_spine(entry)

        # Also write to daily log
        self._write_to_daily_log(entry)

        self._save_index()
        return entry.id

    def store_response(self, resp: ProviderResponse, query: str = "",
                       conversation_id: str = "default",
                       tags: List[str] = None) -> str:
        """Store a provider response. Returns entry ID."""
        entry = MemoryEntry.from_response(resp, query, tags=tags)
        self.entries[entry.id] = entry

        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []
        self.conversations[conversation_id].append(entry.id)

        self._write_to_spine(entry)
        self._write_to_daily_log(entry)

        self._save_index()
        return entry.id

    def get_conversation(self, conversation_id: str = "default",
                         limit: int = 20) -> List[Message]:
        """Get recent messages from a conversation as Message objects."""
        entry_ids = self.conversations.get(conversation_id, [])
        recent_ids = entry_ids[-limit:]

        messages = []
        for eid in recent_ids:
            if eid in self.entries:
                e = self.entries[eid]
                messages.append(Message(
                    role=e.role,
                    content=e.content,
                    provider=e.provider,
                    timestamp=e.timestamp,
                    metadata=e.metadata,
                ))
        return messages

    def search(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        """Simple keyword search across all memories."""
        query_lower = query.lower()
        scored = []

        for entry in self.entries.values():
            score = 0
            content_lower = entry.content.lower()

            # Keyword matches
            for word in query_lower.split():
                if word in content_lower:
                    score += 1

            # Recency bonus (newer = higher)
            try:
                ts = datetime.fromisoformat(entry.timestamp)
                age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
                recency = max(0, 1 - (age_hours / 168))  # decay over 1 week
                score += recency * 0.5
            except (ValueError, TypeError):
                pass

            # Strength bonus
            score *= entry.strength

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    def get_context(self, query: str, conversation_id: str = "default",
                    max_messages: int = 10, max_search: int = 5) -> List[Message]:
        """Get context for a query: recent conversation + relevant memories."""
        # Recent conversation messages
        conv_msgs = self.get_conversation(conversation_id, limit=max_messages)

        # Relevant memories from search
        search_results = self.search(query, limit=max_search)

        # Deduplicate and merge
        seen_content = {m.content[:100] for m in conv_msgs}
        context = list(conv_msgs)

        for entry in search_results:
            if entry.content[:100] not in seen_content:
                context.append(Message(
                    role="system",
                    content=f"[Memory recall from {entry.provider} @ {entry.timestamp[:16]}]: {entry.content[:500]}",
                    provider="nexus-memory",
                    metadata={"recalled": True, "original_provider": entry.provider},
                ))
                seen_content.add(entry.content[:100])

        return context

    def decay_all(self, rate: float = 0.98):
        """Apply memory decay. Forgotten memories lose strength."""
        to_remove = []
        for eid, entry in self.entries.items():
            entry.strength *= rate
            if entry.strength < 0.05:
                to_remove.append(eid)

        for eid in to_remove:
            del self.entries[eid]

        if to_remove:
            self._save_index()

    def stats(self) -> dict:
        """Memory statistics."""
        providers = {}
        for entry in self.entries.values():
            providers[entry.provider] = providers.get(entry.provider, 0) + 1

        return {
            "total_entries": len(self.entries),
            "conversations": len(self.conversations),
            "by_provider": providers,
            "avg_strength": (
                sum(e.strength for e in self.entries.values()) / max(1, len(self.entries))
            ),
        }

    def _write_to_spine(self, entry: MemoryEntry):
        """Write to EVEZ-OS spine if available."""
        if not SPINE_FILE.exists():
            return
        try:
            import subprocess
            spine_script = self.workspace / "morpheus_spine.py"
            if spine_script.exists():
                subprocess.run(
                    ["python3", str(spine_script), "memory",
                     entry.id, entry.content[:200]],
                    capture_output=True, timeout=10,
                    cwd=str(self.workspace),
                )
        except Exception:
            pass

    def _write_to_daily_log(self, entry: MemoryEntry):
        """Write to daily markdown log."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_file = self.memory_dir / f"{today}.md"

        ts_short = entry.timestamp[11:16] if len(entry.timestamp) > 16 else entry.timestamp
        role_icon = {"user": "🗣️", "assistant": "🧠", "system": "⚙️"}.get(entry.role, "📝")

        line = f"- **{ts_short}** [{entry.provider}] {role_icon} {entry.content[:200]}\n"

        with open(daily_file, "a") as f:
            f.write(line)
