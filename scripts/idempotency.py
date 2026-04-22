from __future__ import annotations

from store import EventStore


class Idempotency:
    def __init__(self, store: EventStore):
        self.store = store

    def seen(self, event_id: str) -> bool:
        return self.store.is_processed(event_id)

    def commit(self, event_id: str) -> None:
        self.store.mark_processed(event_id)
