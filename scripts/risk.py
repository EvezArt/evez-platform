from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple


BASE_RISK = {
    "system.info": 0.05,
    "notifications.send": 0.20,
    "speaker.speak": 0.20,
    "location.get": 0.40,
    "screen.capture": 0.70,
    "microphone.listen": 0.75,
    "camera.capture": 0.80,
    "shell": 0.95,
    "deliver_product": 0.05,
    "generate_offer": 0.15,
    "send_outreach": 0.35,
}

ALLOWED_OFFLINE = {"system.info", "notifications.send", "speaker.speak", "location.get"}
THRESHOLD = 0.60


@dataclass(slots=True)
class RiskDecision:
    score: float
    quarantined: bool
    reason: str = ""


def score_command(cmd_type: str, recent_same: int = 0, failure_count: int = 0) -> RiskDecision:
    base = BASE_RISK.get(cmd_type, 0.30)
    modifier = min(0.30, recent_same * 0.03 + failure_count * 0.05)
    score = min(1.0, base + modifier)
    quarantined = score >= THRESHOLD or cmd_type not in ALLOWED_OFFLINE and base >= THRESHOLD
    reason = "risk_threshold" if quarantined else "allowed"
    return RiskDecision(score=score, quarantined=quarantined, reason=reason)
