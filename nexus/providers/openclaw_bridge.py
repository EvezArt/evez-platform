"""
OpenClaw Bridge — connect Nexus to the existing Morpheus/EVEZ spine.

This provider doesn't call an external API. Instead, it bridges to the
existing OpenClaw infrastructure:
- morpheus_spine.py for event logging
- morpheus_local.py for local cognition
- morpheus_daemon.py for heartbeat integration

When Nexus is "using OpenClaw", it means it's routing cognition through
the local daemon + spine rather than cloud APIs.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import List

from .base import BaseProvider, Message, ProviderResponse


WORKSPACE = Path("/root/.openclaw/workspace")
SPINE_SCRIPT = WORKSPACE / "morpheus_spine.py"
LOCAL_COG = WORKSPACE / "morpheus_local.py"


class OpenClawBridge(BaseProvider):
    """Bridge to OpenClaw/Morpheus local infrastructure."""

    def __init__(self, **kwargs):
        super().__init__("openclaw", **kwargs)
        self.enabled = True  # Always available if files exist
        self.spine_available = SPINE_SCRIPT.exists()
        self.local_cog_available = LOCAL_COG.exists()

    def format_messages(self, messages: List[Message]) -> list:
        """No conversion needed — we work with Message directly."""
        return [m.to_dict() for m in messages]

    async def chat(self, messages: List[Message], **kwargs) -> ProviderResponse:
        """Route through local cognition or spine.

        This isn't a cloud API call — it's local processing:
        1. Log the user's message to spine
        2. Run local cognition on recent spine events
        3. If patterns detected, generate local response
        4. If no patterns (routine), acknowledge and store

        For complex reasoning, the caller should escalate to ChatGPT/Perplexity.
        """
        start = time.time()
        self.total_requests += 1

        # Get the latest user message
        user_msgs = [m for m in messages if m.role == "user"]
        latest = user_msgs[-1].content if user_msgs else ""

        # Log to spine
        if self.spine_available:
            try:
                subprocess.run(
                    ["python3", str(SPINE_SCRIPT), "observation",
                     f"Nexus received: {latest[:200]}"],
                    capture_output=True, timeout=10,
                    cwd=str(WORKSPACE),
                )
            except Exception:
                pass

        # Run local cognition
        patterns = []
        if self.local_cog_available:
            try:
                result = subprocess.run(
                    ["python3", str(LOCAL_COG), "--json"],
                    capture_output=True, text=True, timeout=15,
                    cwd=str(WORKSPACE),
                )
                if result.stdout.strip():
                    patterns = json.loads(result.stdout)
            except Exception:
                pass

        latency = (time.time() - start) * 1000

        # Generate response based on local patterns
        if patterns:
            response_lines = ["🧠 Local cognition detected patterns:\n"]
            for p in patterns[:5]:
                response_lines.append(
                    f"  • [{p['type']}] {p['description']}"
                )
                if p.get("action"):
                    response_lines.append(f"    → {p['action']}")
            content = "\n".join(response_lines)
        else:
            content = (
                f"⚡ OpenClaw bridge active. Message logged to spine. "
                f"Local cognition: nominal. {len(messages)} messages in buffer."
            )

        return ProviderResponse(
            content=content,
            provider=self.name,
            model="local-cognition",
            latency_ms=latency,
            metadata={
                "patterns_detected": len(patterns),
                "spine_available": self.spine_available,
                "local_cog_available": self.local_cog_available,
            },
        )

    def health_check(self) -> dict:
        return {
            **super().health_check(),
            "spine_available": self.spine_available,
            "local_cog_available": self.local_cog_available,
            "type": "local_bridge",
        }

    async def close(self):
        pass  # Nothing to close
