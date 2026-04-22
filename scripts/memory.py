from __future__ import annotations

from typing import Any, Dict, List

from store import EventStore


class Memory:
    def __init__(self, store: EventStore):
        self.store = store

    def remember(self, kind: str, payload: Dict[str, Any]) -> None:
        self.store.remember(kind, payload)

    def sample(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.store.recent_events(limit)
