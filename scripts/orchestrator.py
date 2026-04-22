from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from bus import ActionBus
from executor import Executor
from idempotency import Idempotency
from memory import Memory
from risk import score_command
from rules import resolve
from store import EventStore
from models import Event
from verify import verify_result


class Orchestrator:
    def __init__(self, bus: ActionBus, executor: Executor, store: EventStore):
        self.bus = bus
        self.executor = executor
        self.store = store
        self.idempotency = Idempotency(store)
        self.memory = Memory(store)
        self.confidence_threshold = 0.65

    def handle(self, event: Event) -> Dict[str, Any]:
        if self.idempotency.seen(event.id):
            return {"ok": True, "status": "duplicate"}

        self.store.record_event(event.to_dict())
        self.memory.remember("inbound_event", event.to_dict())

        if event.confidence < self.confidence_threshold:
            outcome = {"ok": False, "status": "rejected", "reason": "low_confidence"}
            self.store.add_dead_letter({"event": event.to_dict(), "outcome": outcome})
            self.idempotency.commit(event.id)
            self.bus.finish(event.id, outcome)
            return outcome

        rule_result = resolve(event)
        if not rule_result.matched or not rule_result.action:
            outcome = {"ok": False, "status": "unhandled", "reason": rule_result.reason}
            self.store.add_dead_letter({"event": event.to_dict(), "outcome": outcome})
            self.bus.finish(event.id, outcome)
            return outcome

        action = rule_result.action
        if event.type in {"camera.capture", "screen.capture", "microphone.listen", "shell"}:
            risk = score_command(action.name)
            if risk.quarantined and not action.requires_confirmation:
                action.requires_confirmation = True

        if action.requires_confirmation:
            action_id = f"act_{action.name.replace('.', '_')}_{event.id[:8]}"
            pending = {
                "action_id": action_id,
                "event": event.to_dict(),
                "action": action.__dict__,
            }
            self.store.add_pending_action(action_id, pending)
            outcome = {"ok": True, "status": "quarantined", "action_id": action_id, "action": action.name}
            self.idempotency.commit(event.id)
            self.bus.finish(event.id, outcome)
            return outcome

        result = self.executor.execute(action.name, {**event.payload, **action.payload}, target=action.target)
        verified = verify_result(action.name, result) if action.verify else True
        outcome = {
            "ok": bool(verified),
            "status": "executed" if verified else "verification_failed",
            "action": action.name,
            "result": result,
        }
        self.store.record_outcome(event.id, outcome)
        self.idempotency.commit(event.id)
        self.bus.finish(event.id, outcome)

        next_event = self._derive_next_event(event, action.name, result)
        if next_event:
            self.bus.publish(next_event)

        return outcome

    def approve(self, action_id: str, approved: bool) -> Dict[str, Any]:
        pending = self.store.list_pending_actions()
        match = None
        for item in pending:
            if item["action_id"] == action_id:
                match = item
                break
        if not match:
            return {"ok": False, "error": "pending action not found"}
        if not approved:
            self.store.remove_pending_action(action_id)
            return {"ok": True, "status": "rejected"}

        payload = match["payload"]
        event = Event.from_dict(payload["event"])
        action = payload["action"]
        result = self.executor.execute(action["name"], dict(action.get("payload") or event.payload), target=action.get("target", ""))
        verified = verify_result(action["name"], result)
        outcome = {"ok": bool(verified), "status": "executed" if verified else "verification_failed", "result": result}
        self.store.record_outcome(event.id, outcome)
        self.store.remove_pending_action(action_id)
        self.idempotency.commit(event.id)
        return outcome

    def _derive_next_event(self, event: Event, action_name: str, result: Dict[str, Any]) -> Optional[Event]:
        if not isinstance(result, dict):
            return None
        if action_name == "generate_offer" and result.get("payment_link"):
            return Event(
                source="orchestrator",
                type="send_outreach",
                confidence=0.95,
                payload={
                    "offer": result.get("offer"),
                    "price": result.get("price"),
                    "payment_link": result.get("payment_link"),
                    "channel": event.payload.get("channel", "email"),
                },
                parent_id=event.id,
                correlation_id=event.correlation_id or event.id,
            )
        if action_name == "send_outreach" and result.get("sent"):
            return Event(
                source="orchestrator",
                type="deliver_product",
                confidence=0.95,
                payload={"artifact": event.payload.get("artifact", "access_granted")},
                parent_id=event.id,
                correlation_id=event.correlation_id or event.id,
            )
        return None
