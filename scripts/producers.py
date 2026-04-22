from __future__ import annotations

from typing import Optional

from models import Event


def emit_health_probe() -> Event:
    return Event(source="system", type="health", confidence=1.0, payload={})


def emit_revenue_opportunity() -> Event:
    return Event(
        source="revenue_agent",
        type="revenue_opportunity",
        confidence=0.9,
        payload={
            "audience": "developers",
            "problem": "slow or fragmented automation",
            "offer": "automation audit",
            "price": 149,
            "payment_link": "https://buy.stripe.com/test",
            "channel": "email",
        },
        proposed_action={
            "action": "generate_offer",
            "payload": {
                "offer": "automation audit",
                "price": 149,
                "payment_link": "https://buy.stripe.com/test",
                "channel": "email",
            },
        },
    )


def emit_error_pattern(pattern: str = "api_failure_repeat") -> Event:
    return Event(source="learning", type=pattern, confidence=0.88, payload={"pattern": pattern})
