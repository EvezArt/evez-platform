from __future__ import annotations

import queue
import threading
from typing import Any, Callable, Dict, List, Optional

from store import EventStore
from models import Event

Subscriber = Callable[[Event], Dict[str, Any]]


class ActionBus:
    def __init__(self, store: EventStore):
        self.store = store
        self._queue: "queue.Queue[Event]" = queue.Queue()
        self._subscribers: List[Subscriber] = []
        self._pending: Dict[str, tuple[threading.Event, Dict[str, Any]]] = {}
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None

    def subscribe(self, handler: Subscriber) -> None:
        self._subscribers.append(handler)

    def publish(self, event: Event) -> str:
        self._queue.put(event)
        return event.id

    def request(self, event: Event, timeout: float = 15.0) -> Dict[str, Any]:
        waiter = threading.Event()
        self._pending[event.id] = (waiter, {})
        self.publish(event)
        if not waiter.wait(timeout):
            self._pending.pop(event.id, None)
            return {"ok": False, "error": "timeout", "event_id": event.id}
        _, result = self._pending.pop(event.id, (waiter, {}))
        return result or {"ok": True}

    def finish(self, event_id: str, outcome: Dict[str, Any]) -> None:
        holder = self._pending.get(event_id)
        if holder:
            waiter, current = holder
            current.update(outcome)
            waiter.set()

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    event = self._queue.get(timeout=0.25)
                except queue.Empty:
                    continue
                outcome: Dict[str, Any] = {"ok": False, "status": "unhandled"}
                for subscriber in list(self._subscribers):
                    try:
                        result = subscriber(event)
                        if result is not None:
                            outcome = result
                    except Exception as exc:
                        outcome = {"ok": False, "error": str(exc), "event_id": event.id}
                self.finish(event.id, outcome)
                self._queue.task_done()

        self._worker = threading.Thread(target=loop, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop.set()
