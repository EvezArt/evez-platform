from __future__ import annotations

from dataclasses import asdict
import subprocess
from typing import Any, Dict, Optional

from gateway import GatewayClient
from risk import score_command
from store import EventStore
from verify import verify_result


class Executor:
    def __init__(self, gateway: GatewayClient, store: EventStore, default_node: str = ""):
        self.gateway = gateway
        self.store = store
        self.default_node = default_node

    def _first_paired_node(self) -> Optional[str]:
        if self.default_node:
            return self.default_node
        data = self.gateway.nodes()
        if data.get("_unreachable"):
            return None
        nodes = data.get("nodes") or {}
        for node_id, node in nodes.items():
            if isinstance(node, dict) and node.get("paired"):
                return node_id
        return None

    def _local_preview(self, cmd_type: str) -> Dict[str, Any]:
        decision = score_command(cmd_type)
        return {
            "ok": True,
            "offline": True,
            "riskScore": decision.score,
            "quarantined": decision.quarantined,
            "reason": decision.reason,
        }

    def execute(self, action_name: str, payload: Dict[str, Any], target: str = "") -> Dict[str, Any]:
        node = target or self._first_paired_node() or "demo_node"
        if action_name == "health":
            return self.gateway.health()
        if action_name == "nodes":
            chain = self.gateway.chain()
            return {"ok": True, "nodes": self.gateway.nodes(), "chain": chain}
        if action_name == "history":
            return {"ok": True, "last_50": self.store.recent_events(50)}
        if action_name == "verify":
            return self.gateway.verify()
        if action_name == "manifest":
            return self.gateway.manifest()
        if action_name == "pending_list":
            return {"ok": True, "pending": self.store.list_pending_actions()}
        if action_name == "confirm":
            action_id = str(payload.get("action_id", ""))
            return self.gateway.confirm(action_id, approved=True)
        if action_name == "reject":
            action_id = str(payload.get("action_id", ""))
            return self.gateway.confirm(action_id, approved=False)

        if action_name == "generate_offer":
            offer = payload.get("offer") or "System optimization audit"
            price = payload.get("price") or 149
            payment_link = payload.get("payment_link") or "https://buy.stripe.com/test"
            return {"ok": True, "offer": offer, "price": price, "payment_link": payment_link, "status": "draft"}

        if action_name == "send_outreach":
            # The orchestrator can require confirmation before this is called.
            return {"ok": True, "sent": True, "status": "sent", "channel": payload.get("channel", "email")}

        if action_name == "deliver_product":
            return {"ok": True, "status": "delivered", "artifact": payload.get("artifact", "access_granted")}

        if action_name == "rotate_keys":
            return {"ok": True, "status": "rotated"}

        if action_name == "retry_with_backoff":
            return {"ok": True, "status": "scheduled"}

        if action_name == "patch_retry_logic":
            return {"ok": True, "status": "patched"}

        if action_name == "shell":
            cmd = str(payload.get("cmd", ""))
            if not cmd:
                return {"ok": False, "error": "missing command"}
            # Local shell execution is intentionally explicit and gated by the orchestrator.
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }

        # Gateway-backed device actions.
        action_payload: Dict[str, Any]
        if action_name == "speaker.speak":
            action_payload = {"text": payload.get("text") or payload.get("body") or "Hello"}
        elif action_name == "microphone.listen":
            action_payload = {"lang": payload.get("lang", "en-US"), "timeoutMs": int(payload.get("timeoutMs", 8000))}
        elif action_name == "notifications.send":
            action_payload = {"title": payload.get("title", "OpenClaw"), "body": payload.get("body", "Message from agent")}
        else:
            action_payload = dict(payload)

        response = self.gateway.simulate(action_name, node, action_payload)
        if response.get("_unreachable"):
            return self._local_preview(action_name)
        return response
