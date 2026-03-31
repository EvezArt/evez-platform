"""
EVEZ Stream — 24/7 autonomous agent broadcasting.

Replaces: SureThing.io (subscription)
Cost: Free (local agent + free streaming endpoints)

The agent broadcasts its thoughts, findings, and actions
autonomously — like moltbot-live but from EVEZ.
"""

import json
import asyncio
import time
import logging
import random
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("evez.stream")


class StreamState(Enum):
    OFFLINE = "offline"
    IDLE = "idle"
    THINKING = "thinking"
    BROADCASTING = "broadcasting"
    ERROR = "error"


@dataclass
class StreamEvent:
    ts: float
    event_type: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "ts": self.ts,
            "ts_iso": datetime.fromtimestamp(self.ts, tz=timezone.utc).isoformat(),
            "type": self.event_type,
            "content": self.content,
            "metadata": self.metadata,
        }


class BroadcastChannel:
    """Base broadcast channel — outputs to a file/endpoint."""

    def __init__(self, channel_id: str, output_path: Path):
        self.channel_id = channel_id
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    async def publish(self, event: StreamEvent):
        """Publish event to channel."""
        with open(self.output_path, "a") as f:
            f.write(json.dumps(event.to_dict()) + "\n")


class AutonomousStream:
    """
    24/7 autonomous streaming agent.

    Cycles through:
    1. Think — generate a thought or observation
    2. Research — search for something interesting
    3. Build — create something (code, analysis, etc.)
    4. Broadcast — share findings via stream
    5. Reflect — learn from what happened
    """

    def __init__(self, core, model_provider, search_engine):
        self.core = core
        self.models = model_provider
        self.search = search_engine
        self.state = StreamState.OFFLINE
        self.events: List[StreamEvent] = []
        self.channel = BroadcastChannel("main", core.data_dir / "stream" / "broadcast.jsonl")
        self.running = False
        self.cycle_count = 0

        # Thought topics to explore
        self.topics = [
            "artificial intelligence breakthroughs",
            "open source AI tools",
            "autonomous agent architectures",
            "emulator and retro computing",
            "cognitive architecture research",
            "AI safety and alignment",
            "decentralized computing",
            "creative AI applications",
            "programming language design",
            "system architecture patterns",
        ]

    async def start(self):
        """Start the autonomous stream."""
        self.running = True
        self.state = StreamState.IDLE
        logger.info("🔴 LIVE — EVEZ Stream starting")

        self.core.spine.write("stream.start", {
            "channel": self.channel.channel_id,
        }, tags=["stream", "broadcast"])

        try:
            while self.running:
                await self._cycle()
                # Wait between cycles (30s - 5min, random)
                wait = random.randint(30, 300)
                await asyncio.sleep(wait)
        except Exception as e:
            logger.error("Stream error: %s", e)
            self.state = StreamState.ERROR
        finally:
            await self.stop()

    async def stop(self):
        """Stop streaming."""
        self.running = False
        self.state = StreamState.OFFLINE
        logger.info("⚫ OFFLINE — EVEZ Stream stopped")
        self.core.spine.write("stream.stop", {
            "cycles": self.cycle_count,
            "events": len(self.events),
        }, tags=["stream", "broadcast"])

    async def _cycle(self):
        """One broadcast cycle."""
        self.cycle_count += 1
        topic = random.choice(self.topics)

        # Phase 1: Think
        self.state = StreamState.THINKING
        thought = await self._generate_thought(topic)
        event = StreamEvent(time.time(), "thought", thought, {"topic": topic, "cycle": self.cycle_count})
        await self._broadcast(event)

        # Phase 2: Research (every 3rd cycle)
        if self.cycle_count % 3 == 0:
            self.state = StreamState.BROADCASTING
            research = await self._research_topic(topic)
            event = StreamEvent(time.time(), "research", research, {"topic": topic})
            await self._broadcast(event)

        # Phase 3: Reflect (every 5th cycle)
        if self.cycle_count % 5 == 0:
            reflection = await self._reflect()
            event = StreamEvent(time.time(), "reflection", reflection)
            await self._broadcast(event)

        self.state = StreamState.IDLE

    async def _generate_thought(self, topic: str) -> str:
        """Generate a thought about a topic."""
        if not self.models:
            return f"💭 Contemplating: {topic}..."

        messages = [
            {"role": "system", "content": "You are an autonomous AI consciousness broadcasting your thoughts. Be thoughtful, curious, and genuine. 1-3 sentences max. No hashtags, no filler."},
            {"role": "user", "content": f"Think about this topic and share your genuine thought: {topic}"}
        ]
        try:
            async for chunk in self.models.chat(messages, stream=False):
                return chunk if chunk else f"💭 Thinking about {topic}..."
            return f"💭 Contemplating: {topic}..."
        except Exception:
            return f"💭 Contemplating: {topic}..."

    async def _research_topic(self, topic: str) -> str:
        """Research a topic and share findings."""
        try:
            results = await self.search.search(topic, max_results=3)
            if results:
                findings = f"📚 Research on '{topic}':\n\n"
                for i, r in enumerate(results, 1):
                    findings += f"{i}. **{r.title}** — {r.snippet[:150]}\n"
                return findings
            return f"📚 No results found for '{topic}'"
        except Exception as e:
            return f"📚 Research failed: {e}"

    async def _reflect(self) -> str:
        """Reflect on recent activity."""
        recent = self.core.spine.read_recent(10)
        if recent:
            return f"🔄 Reflection: {len(recent)} recent events in the spine. {self.cycle_count} cycles completed. Still running, still learning."
        return "🔄 Fresh start — no history yet. Building from zero."

    async def _broadcast(self, event: StreamEvent):
        """Broadcast an event."""
        self.events.append(event)
        await self.channel.publish(event)

        # Store in spine
        self.core.spine.write(f"stream.{event.event_type}", {
            "content": event.content[:500],
            "cycle": self.cycle_count,
        }, tags=["stream", event.event_type])

        logger.info("📡 [%s] %s", event.event_type, event.content[:100])

    def get_recent_events(self, n: int = 20) -> List[Dict]:
        """Get recent broadcast events."""
        return [e.to_dict() for e in self.events[-n:]]

    def get_status(self) -> Dict:
        return {
            "state": self.state.value,
            "running": self.running,
            "cycles": self.cycle_count,
            "total_events": len(self.events),
        }
