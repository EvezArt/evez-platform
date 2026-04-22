from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Optional


class GatewayClient:
    def __init__(self, host: str, port: int, token: str):
        self.host = host
        self.port = port
        self.token = token
        self.base_url = f"http://{host}:{port}"

    def _headers(self, payload: Dict[str, Any]) -> Dict[str, str]:
        ts = str(int(time.time()))
        nonce = uuid.uuid4().hex
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = hmac.new(
            self.token.encode("utf-8"),
            f"{ts}.{nonce}.{body}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-Agent-Token": self.token,
            "X-Agent-Timestamp": ts,
            "X-Agent-Nonce": nonce,
            "X-Agent-Signature": signature,
        }

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None, timeout: int = 8) -> Dict[str, Any]:
        payload = body or {}
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8") if method.upper() == "POST" else None,
            headers=self._headers(payload),
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            if not raw:
                return {"ok": True}
            return json.loads(raw)
        except urllib.error.URLError as exc:
            return {"ok": False, "_unreachable": True, "error": str(exc)}
        except Exception as exc:  # pragma: no cover - network/runtime errors are recorded, not fatal
            return {"ok": False, "error": str(exc)}

    def get(self, path: str, timeout: int = 8) -> Dict[str, Any]:
        return self._request("GET", path, timeout=timeout)

    def post(self, path: str, body: Dict[str, Any], timeout: int = 8) -> Dict[str, Any]:
        return self._request("POST", path, body=body, timeout=timeout)

    def health(self) -> Dict[str, Any]:
        return self.get("/health")

    def nodes(self) -> Dict[str, Any]:
        return self.get("/api/nodes")

    def chain(self) -> Dict[str, Any]:
        return self.get("/api/chain")

    def pending(self) -> Dict[str, Any]:
        return self.get("/api/pending")

    def verify(self) -> Dict[str, Any]:
        return self.get("/api/verify")

    def manifest(self) -> Dict[str, Any]:
        return self.get("/api/manifest")

    def confirm(self, action_id: str, approved: bool) -> Dict[str, Any]:
        return self.post("/api/confirm", {"actionId": action_id, "approved": approved})

    def simulate(self, cmd_type: str, target: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.post("/api/simulate", {"type": cmd_type, "target": target, "payload": payload})
