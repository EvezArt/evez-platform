from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from models import Event, ActionSpec


@dataclass(slots=True)
class RuleResult:
    matched: bool
    action: Optional[ActionSpec] = None
    reason: str = ""


RULES: Dict[str, Dict[str, Any]] = {
    "camera.capture": {"requires_confirmation": True, "min_confidence": 0.75},
    "screen.capture": {"requires_confirmation": True, "min_confidence": 0.70},
    "location.get": {"requires_confirmation": False, "min_confidence": 0.35},
    "speaker.speak": {"requires_confirmation": False, "min_confidence": 0.15},
    "microphone.listen": {"requires_confirmation": True, "min_confidence": 0.70},
    "microphone.listen_n": {"requires_confirmation": True, "min_confidence": 0.70},
    "notifications.send": {"requires_confirmation": False, "min_confidence": 0.10},
    "system.info": {"requires_confirmation": False, "min_confidence": 0.05},
    "shell": {"requires_confirmation": True, "min_confidence": 0.95},
    "verify": {"requires_confirmation": False, "min_confidence": 0.0},
    "manifest": {"requires_confirmation": False, "min_confidence": 0.0},
    "pending_list": {"requires_confirmation": False, "min_confidence": 0.0},
    "confirm": {"requires_confirmation": False, "min_confidence": 0.0},
    "reject": {"requires_confirmation": False, "min_confidence": 0.0},
    "nodes": {"requires_confirmation": False, "min_confidence": 0.0},
    "health": {"requires_confirmation": False, "min_confidence": 0.0},
    "history": {"requires_confirmation": False, "min_confidence": 0.0},
    "revenue_opportunity": {"requires_confirmation": False, "min_confidence": 0.50},
    "generate_offer": {"requires_confirmation": True, "min_confidence": 0.70},
    "send_outreach": {"requires_confirmation": True, "min_confidence": 0.80},
    "deliver_product": {"requires_confirmation": False, "min_confidence": 0.0},
}


def resolve(event: Event) -> RuleResult:
    rule = RULES.get(event.type)
    if not rule:
        if event.proposed_action.get("action"):
            return RuleResult(
                matched=True,
                action=ActionSpec(
                    name=str(event.proposed_action.get("action")),
                    target=str(event.proposed_action.get("target", "")),
                    payload=dict(event.proposed_action.get("payload") or {}),
                    requires_confirmation=bool(event.proposed_action.get("requires_confirmation", False)),
                    min_confidence=float(event.proposed_action.get("min_confidence", 0.0)),
                    retries=int(event.proposed_action.get("retries", 0)),
                ),
                reason="proposed_action",
            )
        return RuleResult(matched=False, reason="no_rule")

    action = ActionSpec(
        name=event.proposed_action.get("action") or event.type,
        target=str(event.proposed_action.get("target", "")),
        payload=dict(event.proposed_action.get("payload") or event.payload or {}),
        requires_confirmation=bool(rule.get("requires_confirmation", False)),
        min_confidence=float(rule.get("min_confidence", 0.0)),
        retries=int(rule.get("retries", 0)),
        verify=bool(rule.get("verify", True)),
        tags={"rule": event.type},
    )
    return RuleResult(matched=True, action=action, reason="rule")
