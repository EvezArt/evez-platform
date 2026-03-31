#!/usr/bin/env python3
"""
NEXUS API Server — monetized task execution API.

This is the revenue-generating endpoint. Clients pay per task or subscribe monthly.

Usage:
    python3 api_server.py --port 8877
    curl -X POST http://localhost:8877/v1/tasks \
      -H "Authorization: Bearer <api_key>" \
      -H "Content-Type: application/json" \
      -d '{"type":"research","description":"Solana MEV strategies 2026"}'
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent))
from income_engine import IncomeEngine, Task


WORKSPACE = Path("/root/.openclaw/workspace")
NEXUS_DIR = WORKSPACE / "nexus"
API_KEYS_FILE = NEXUS_DIR / "api_keys.json"

# Pricing tiers (USD)
PRICING = {
    "research": 0.50,    # Per research query
    "writing": 1.00,     # Per 1000 words
    "coding": 2.00,      # Per code generation
    "analysis": 1.00,    # Per analysis
    "trading": 5.00,     # Per trade signal
}

# Rate limits
RATE_LIMITS = {
    "free": 10,      # 10 tasks/day
    "basic": 100,    # 100 tasks/day
    "pro": 1000,     # 1000 tasks/day
    "enterprise": -1 # Unlimited
}


class APIKeyManager:
    """Manage API keys and billing."""

    def __init__(self):
        self.keys = self._load()

    def _load(self) -> dict:
        if API_KEYS_FILE.exists():
            try:
                return json.loads(API_KEYS_FILE.read_text())
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save(self):
        API_KEYS_FILE.write_text(json.dumps(self.keys, indent=2))

    def generate_key(self, client_id: str, tier: str = "free") -> str:
        """Generate a new API key."""
        raw = f"{client_id}:{tier}:{time.time()}"
        key = "nxk_" + hashlib.sha256(raw.encode()).hexdigest()[:32]
        self.keys[key] = {
            "client_id": client_id,
            "tier": tier,
            "created": datetime.now(timezone.utc).isoformat(),
            "tasks_today": 0,
            "total_tasks": 0,
            "total_spent_usd": 0.0,
            "last_reset": datetime.now(timezone.utc).isoformat(),
        }
        self._save()
        return key

    def validate(self, key: str) -> Optional[dict]:
        """Validate an API key. Returns key info or None."""
        info = self.keys.get(key)
        if not info:
            return None

        # Reset daily counter
        now = datetime.now(timezone.utc)
        try:
            last_reset = datetime.fromisoformat(info["last_reset"])
            if (now - last_reset).days >= 1:
                info["tasks_today"] = 0
                info["last_reset"] = now.isoformat()
                self._save()
        except (ValueError, TypeError):
            pass

        # Check rate limit
        limit = RATE_LIMITS.get(info["tier"], 10)
        if limit > 0 and info["tasks_today"] >= limit:
            return None  # Rate limited

        return info

    def record_usage(self, key: str, cost_usd: float):
        """Record task usage."""
        if key in self.keys:
            self.keys[key]["tasks_today"] += 1
            self.keys[key]["total_tasks"] += 1
            self.keys[key]["total_spent_usd"] += cost_usd
            self._save()


# Global state
engine = None
key_manager = None


class APIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the Nexus API."""

    def do_GET(self):
        if self.path == "/":
            self._json_response({
                "name": "NEXUS API",
                "version": "0.1.0",
                "endpoints": {
                    "POST /v1/tasks": "Submit a task",
                    "GET /v1/tasks/{id}": "Get task status",
                    "GET /v1/tasks": "List tasks",
                    "GET /v1/health": "Health check",
                    "GET /v1/pricing": "Pricing info",
                },
            })
        elif self.path == "/v1/health":
            health = engine.core.health() if engine else {}
            self._json_response({"status": "ok", **health})
        elif self.path == "/v1/pricing":
            self._json_response({
                "pricing": PRICING,
                "tiers": {
                    "free": {"tasks_per_day": 10, "price": "$0/month"},
                    "basic": {"tasks_per_day": 100, "price": "$29/month"},
                    "pro": {"tasks_per_day": 1000, "price": "$99/month"},
                    "enterprise": {"tasks_per_day": "unlimited", "price": "contact"},
                },
            })
        elif self.path == "/v1/tasks":
            # List tasks (requires auth)
            key_info = self._authenticate()
            if not key_info:
                return
            tasks = list(engine.tasks.values())[-20:]
            self._json_response({
                "tasks": [
                    {
                        "id": t.id, "type": t.type, "status": t.status,
                        "description": t.description[:100],
                        "created": t.created, "revenue_usd": t.revenue_usd,
                    }
                    for t in tasks
                ]
            })
        elif self.path.startswith("/v1/tasks/"):
            task_id = self.path.split("/")[-1]
            task = engine.tasks.get(task_id)
            if task:
                self._json_response({
                    "id": task.id, "type": task.type, "status": task.status,
                    "description": task.description,
                    "result": task.result,
                    "created": task.created, "completed": task.completed,
                    "revenue_usd": task.revenue_usd,
                })
            else:
                self._error(404, "Task not found")
        else:
            # Serve dashboard
            dashboard_file = NEXUS_DIR / "dashboard.html"
            if dashboard_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(dashboard_file.read_bytes())
            else:
                self._error(404, "Not found")

    def do_POST(self):
        if self.path == "/v1/tasks":
            key_info = self._authenticate()
            if not key_info:
                return

            body = self._read_body()
            if not body:
                return

            task_type = body.get("type", "research")
            description = body.get("description", "")
            provider = body.get("provider", "auto")

            if not description:
                self._error(400, "Missing 'description'")
                return

            # Calculate price
            price = PRICING.get(task_type, 1.0)

            # Create and execute task
            async def run():
                task = await engine.submit_task(
                    task_type=task_type,
                    description=description,
                    price_usd=price,
                    client_id=key_info["client_id"],
                    provider=provider,
                )
                key_manager.record_usage(auth_key, price)
                task = await engine.execute_task(task.id)
                return task

            auth_key = self.headers.get("Authorization", "").replace("Bearer ", "")
            loop = asyncio.new_event_loop()
            try:
                task = loop.run_until_complete(run())
                self._json_response({
                    "id": task.id,
                    "type": task.type,
                    "status": task.status,
                    "result": task.result,
                    "cost_usd": task.revenue_usd,
                }, status=201)
            except Exception as e:
                self._error(500, str(e))
            finally:
                loop.close()
        else:
            self._error(404, "Not found")

    def _authenticate(self) -> Optional[dict]:
        """Authenticate request via Bearer token."""
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._error(401, "Missing Authorization header. Use: Bearer <api_key>")
            return None

        key = auth[7:]
        info = key_manager.validate(key)
        if not info:
            self._error(403, "Invalid or rate-limited API key")
            return None
        return info

    def _read_body(self) -> Optional[dict]:
        """Read and parse JSON body."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            return json.loads(body)
        except Exception:
            self._error(400, "Invalid JSON body")
            return None

    def _json_response(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def _error(self, status: int, message: str):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode())

    def log_message(self, format, *args):
        pass  # Suppress logs


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--generate-key", type=str, help="Generate API key for client")
    parser.add_argument("--tier", type=str, default="free")
    args = parser.parse_args()

    global engine, key_manager
    engine = IncomeEngine()
    key_manager = APIKeyManager()

    if args.generate_key:
        key = key_manager.generate_key(args.generate_key, args.tier)
        print(f"API Key: {key}")
        print(f"Tier: {args.tier}")
        print(f"Rate limit: {RATE_LIMITS.get(args.tier, 10)} tasks/day")
        return

    server = HTTPServer(("0.0.0.0", args.port), APIHandler)
    print(f"⚡ NEXUS API Server listening on 0.0.0.0:{args.port}")
    print(f"  Dashboard: http://localhost:{args.port}/")
    print(f"  API Docs:  http://localhost:{args.port}/v1/health")
    print(f"  Pricing:   http://localhost:{args.port}/v1/pricing")
    server.serve_forever()


if __name__ == "__main__":
    main()
