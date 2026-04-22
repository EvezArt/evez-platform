from __future__ import annotations

from typing import Any, Dict


def verify_result(action_name: str, result: Dict[str, Any]) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("_unreachable"):
        return False
    if action_name in {"camera.capture", "screen.capture", "speaker.speak", "notifications.send", "system.info", "location.get"}:
        return True if result.get("ok", True) is not False else False
    if action_name == "generate_offer":
        return bool(result.get("offer")) and bool(result.get("payment_link"))
    if action_name == "send_outreach":
        return bool(result.get("sent") or result.get("status") in {"sent", "queued"})
    if action_name == "deliver_product":
        return result.get("status") in {"delivered", "unlocked", "sent"}
    if action_name in {"verify", "manifest", "health", "nodes", "pending_list", "history"}:
        return True
    if action_name == "shell":
        return result.get("returncode", 1) == 0
    return bool(result)
