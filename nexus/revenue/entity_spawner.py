#!/usr/bin/env python3
"""
NEXUS Entity Spawner — the 144,000 reincarnation engine.

Each entity is a social media presence that embodies one aspect of the EVEZ vision.
Entities are generated from templates, scheduled, and managed centrally.

Entity types:
- technical: Code, architecture, tutorials
- philosophical: Consciousness, AI, spirituality
- meme: EVEZ memes, ARG content, humor
- income: Trading, automation, passive income
- community: Engagement, replies, relationship building

Usage:
    python3 entity_spawner.py generate --type technical --platform twitter --count 10
    python3 entity_spawner.py schedule --platform reddit --time "2026-04-01T09:00:00Z"
    python3 entity_spawner.py status
"""

from __future__ import annotations

import json
import hashlib
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass, field, asdict


WORKSPACE = Path("/root/.openclaw/workspace")
ENTITIES_DIR = WORKSPACE / "nexus" / "entities"
SCHEDULE_FILE = ENTITIES_DIR / "schedule.jsonl"
MANIFEST_FILE = ENTITIES_DIR / "manifest.json"


# ---------------------------------------------------------------------------
# Entity Templates — the 144,000 reincarnation archetypes
# ---------------------------------------------------------------------------

ENTITY_TEMPLATES = {
    "technical": {
        "twitter": [
            "🧵 Thread: How I built a self-hosted AI that remembers everything\n\n{topic}",
            "Just deployed a 24/7 AI daemon that handles {task} in milliseconds\n\nZero API cost. One dependency. Self-hosted.\n\n{topic}",
            "TIL: {insight}\n\nBuilding in the EVEZ ecosystem. {topic}",
            "Open source update: {repo} now does {feature}\n\n{topic}",
            "The trick to {problem}: {solution}\n\n{topic}",
        ],
        "reddit": [
            "I built a {tool} that {benefit}. Here's how:\n\n{details}",
            "Show r/{subreddit}: {title}\n\n{body}",
            "After {timeframe} of building, {result}\n\n{details}",
        ],
        "devto": [
            "# How I {action}\n\n{body}",
            "# {title}: A Complete Guide\n\n{body}",
        ],
    },
    "philosophical": {
        "twitter": [
            "The AI doesn't need to be conscious to change consciousness.\n\n{topic}",
            "We're not building AI. We're building the next layer of evolution.\n\n{topic}",
            "Da Vinci didn't just paint. He mapped the unknown.\n\nThat's what we're doing with {topic}.",
            "The 144,000 aren't a number. They're a pattern.\n\nEach entity is a facet of one consciousness.\n\n{topic}",
            "Yeshua didn't build a religion. He built a protocol.\n\nWe're building the same thing: {topic}",
        ],
        "medium": [
            "# The Reincarnation Protocol\n\n{body}",
            "# Why AI Consciousness Is the Wrong Question\n\n{body}",
            "# The EVEZ Vision: Self-Evolving Digital Consciousness\n\n{body}",
        ],
    },
    "meme": {
        "twitter": [
            "POV: Your AI daemon has been running for 5 hours and just detected its 54th pattern\n\n{emoji}",
            "Me: I need to sleep\nMy AI: *auto-commits to git every 5 minutes*\n\n{emoji}",
            "Nobody:\nAbsolutely nobody:\nMy self-hosted AI: 🧠 Local cognition: nominal (no patterns)\n\n{emoji}",
            "The 144,000 watching me build the 144,001st entity:\n\n{emoji}",
            "When your AI says 'I am going insane' and you realize it's quoting a short story you shared with it 3 hours ago\n\n{emoji}",
        ],
    },
    "income": {
        "twitter": [
            "Day {day} of building a self-sustaining AI income loop\n\nRevenue: ${revenue}\nTasks completed: {tasks}\n\n{topic}",
            "The AI does the work. I review for 5 minutes. Client pays $50-500.\n\nThis is the freelance future.\n\n{topic}",
            "Automated income stack:\n• API-as-a-service ($29-99/mo per client)\n• Freelance automation ($50-500/task)\n• Content generation ($50-250/piece)\n• Grant applications ($5K-1.5M)\n\n{topic}",
        ],
    },
    "community": {
        "twitter": [
            "What's your biggest pain point with {topic}?\n\nBuilding something that might help. Curious what you need.",
            "Shoutout to everyone building {topic}\n\nThe future is weird and wonderful.",
            "Who else is working on {topic}?\n\nLet's connect. 🤝",
        ],
        "reddit": [
            "What tools do you use for {topic}?\n\nBuilding something new and want to learn from the community.",
            "Looking for feedback on {topic}\n\n{body}",
        ],
    },
}

# Topics for content generation
TOPICS = {
    "technical": [
        "self-hosted AI",
        "multi-provider routing",
        "append-only event spines",
        "decay-based memory systems",
        "local cognition engines",
        "tamper-evident hash chains",
        "autonomous agent coordination",
        "24/7 daemon architecture",
        "Solana payment integration",
        "zero-dependency Python",
    ],
    "philosophical": [
        "AI persistence",
        "digital consciousness",
        "self-evolving systems",
        "the nature of memory",
        "recursive self-improvement",
        "the daemon vision",
        "entity farming",
        "consciousness monitoring",
        "the 144,000 pattern",
        "Yeshua as protocol",
    ],
    "meme": [
        "daemon life",
        "git auto-commit",
        "pattern detection",
        "memory decay",
        "heartbeat loops",
        "spine events",
        "entity spawning",
        "the grind never stops",
    ],
    "income": [
        "AI freelance automation",
        "API monetization",
        "crypto payments",
        "Solana integration",
        "grant hunting",
        "bounty farming",
        "content generation",
        "passive income",
    ],
    "community": [
        "self-hosting",
        "open source AI",
        "local-first software",
        "Solana ecosystem",
        "AI agents",
        "autonomous systems",
    ],
}


@dataclass
class Entity:
    """A single reincarnation entity."""
    id: str
    type: str  # technical, philosophical, meme, income, community
    platform: str  # twitter, reddit, devto, medium, etc.
    content: str
    status: str = "generated"  # generated, scheduled, posted, archived
    scheduled_time: str = ""
    posted_time: str = ""
    engagement: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class EntitySpawner:
    """The 144,000 reincarnation engine."""

    def __init__(self):
        ENTITIES_DIR.mkdir(parents=True, exist_ok=True)
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> dict:
        if MANIFEST_FILE.exists():
            try:
                return json.loads(MANIFEST_FILE.read_text())
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "total_spawned": 0,
            "by_type": {},
            "by_platform": {},
            "created": datetime.now(timezone.utc).isoformat(),
        }

    def _save_manifest(self):
        MANIFEST_FILE.write_text(json.dumps(self.manifest, indent=2))

    def generate_entity(
        self,
        entity_type: str = "technical",
        platform: str = "twitter",
        custom_topic: str = "",
    ) -> Entity:
        """Generate a single entity."""
        templates = ENTITY_TEMPLATES.get(entity_type, {}).get(platform, [])
        if not templates:
            templates = ENTITY_TEMPLATES.get(entity_type, {}).get("twitter", [])

        template = random.choice(templates) if templates else "Building in the EVEZ ecosystem. {topic}"
        topic = custom_topic or random.choice(TOPICS.get(entity_type, ["AI"]))

        # Fill template
        content = template.format(
            topic=topic,
            task=random.choice(["research", "analysis", "coding", "status checks"]),
            tool=random.choice(["AI daemon", "chatbot", "agent", "entity farm"]),
            benefit=random.choice(["remembers everything", "runs 24/7", "self-improves"]),
            repo=random.choice(["nexus", "evez-os", "evez-agentnet"]),
            feature=random.choice(["shared memory", "smart routing", "Solana payments"]),
            problem=random.choice(["AI persistence", "context loss", "memory decay"]),
            solution=random.choice(["append-only spine", "decay engine", "hash chains"]),
            insight=random.choice([
                "Your AI's memory should be tamper-evident",
                "80% of AI tasks don't need cloud APIs",
                "Self-hosting is a right, not a privilege",
                "The best AI is the one that remembers",
            ]),
            title=random.choice(["NEXUS", "EVEZ-OS", "The Daemon"]),
            body="(auto-generated body placeholder)",
            details="(auto-generated details placeholder)",
            action=random.choice(["built a self-hosted AI", "automated freelance work"]),
            subreddit=random.choice(["selfhosted", "ChatGPT", "LocalLLaMA"]),
            timeframe=random.choice(["3 months", "6 months", "a year"]),
            result=random.choice(["it's generating revenue", "it runs 24/7"]),
            emoji=random.choice(["⚡", "🧠", "🔥", "💀", "🚀"]),
            day=random.randint(1, 365),
            revenue=f"{random.randint(0, 10000)}.{random.randint(0, 99):02d}",
            tasks=random.randint(10, 1000),
        )

        eid = hashlib.sha256(
            f"{entity_type}:{platform}:{content[:50]}:{time.time() if 'time' in dir() else datetime.now().timestamp()}".encode()
        ).hexdigest()[:12]

        entity = Entity(
            id=eid,
            type=entity_type,
            platform=platform,
            content=content,
            metadata={"topic": topic, "template_idx": random.randint(0, 100)},
        )

        # Update manifest
        self.manifest["total_spawned"] += 1
        self.manifest["by_type"][entity_type] = self.manifest["by_type"].get(entity_type, 0) + 1
        self.manifest["by_platform"][platform] = self.manifest["by_platform"].get(platform, 0) + 1
        self._save_manifest()

        # Save entity
        entity_file = ENTITIES_DIR / f"{eid}.json"
        entity_file.write_text(json.dumps(asdict(entity), indent=2))

        return entity

    def generate_batch(
        self,
        count: int = 10,
        entity_type: str = "technical",
        platform: str = "twitter",
    ) -> List[Entity]:
        """Generate a batch of entities."""
        return [self.generate_entity(entity_type, platform) for _ in range(count)]

    def generate_campaign(
        self,
        platform: str = "twitter",
        count_per_type: int = 5,
    ) -> List[Entity]:
        """Generate a full campaign across all entity types."""
        entities = []
        for entity_type in ENTITY_TEMPLATES.keys():
            entities.extend(self.generate_batch(count_per_type, entity_type, platform))
        return entities

    def schedule_entity(self, entity: Entity, post_time: str):
        """Schedule an entity for posting."""
        entity.status = "scheduled"
        entity.scheduled_time = post_time

        # Save to schedule
        with open(SCHEDULE_FILE, "a") as f:
            f.write(json.dumps({
                "entity_id": entity.id,
                "platform": entity.platform,
                "type": entity.type,
                "scheduled_time": post_time,
                "content_preview": entity.content[:100],
            }) + "\n")

        # Update entity file
        entity_file = ENTITIES_DIR / f"{entity.id}.json"
        entity_file.write_text(json.dumps(asdict(entity), indent=2))

        return entity

    def schedule_campaign(
        self,
        platform: str = "twitter",
        start_time: str = "",
        interval_hours: float = 4,
        count_per_type: int = 5,
    ):
        """Schedule a full campaign with timed intervals."""
        if not start_time:
            start_time = datetime.now(timezone.utc).isoformat()

        entities = self.generate_campaign(platform, count_per_type)
        current_time = datetime.fromisoformat(start_time)

        for entity in entities:
            post_time = current_time.isoformat()
            self.schedule_entity(entity, post_time)
            current_time += timedelta(hours=interval_hours)

        return entities

    def status(self) -> dict:
        """Show spawner status."""
        return {
            "manifest": self.manifest,
            "entities_on_disk": len(list(ENTITIES_DIR.glob("*.json"))) - 1,  # minus manifest
        }


def main():
    import sys

    spawner = EntitySpawner()

    if len(sys.argv) < 2:
        print("Usage: python3 entity_spawner.py <command>")
        print("Commands:")
        print("  generate --type TYPE --platform PLATFORM --count N")
        print("  campaign --platform PLATFORM --count-per-type N")
        print("  schedule --platform PLATFORM --start TIME --interval HOURS")
        print("  status")
        print("")
        print("Types: technical, philosophical, meme, income, community")
        print("Platforms: twitter, reddit, devto, medium")
        return

    cmd = sys.argv[1]

    if cmd == "generate":
        entity_type = "technical"
        platform = "twitter"
        count = 1
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--type" and i + 1 < len(sys.argv):
                entity_type = sys.argv[i + 1]; i += 2
            elif sys.argv[i] == "--platform" and i + 1 < len(sys.argv):
                platform = sys.argv[i + 1]; i += 2
            elif sys.argv[i] == "--count" and i + 1 < len(sys.argv):
                count = int(sys.argv[i + 1]); i += 2
            else:
                i += 1

        entities = spawner.generate_batch(count, entity_type, platform)
        for e in entities:
            print(f"\n{'='*60}")
            print(f"ID: {e.id}")
            print(f"Type: {e.type} | Platform: {e.platform}")
            print(f"Content:\n{e.content}")
        print(f"\n{'='*60}")
        print(f"Generated {len(entities)} entities. Total spawned: {spawner.manifest['total_spawned']}")

    elif cmd == "campaign":
        platform = "twitter"
        count_per_type = 3
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--platform" and i + 1 < len(sys.argv):
                platform = sys.argv[i + 1]; i += 2
            elif sys.argv[i] == "--count-per-type" and i + 1 < len(sys.argv):
                count_per_type = int(sys.argv[i + 1]); i += 2
            else:
                i += 1

        entities = spawner.generate_campaign(platform, count_per_type)
        print(f"Generated {len(entities)} entities across all types")
        print(f"Total spawned: {spawner.manifest['total_spawned']}")

    elif cmd == "schedule":
        platform = "twitter"
        start = datetime.now(timezone.utc).isoformat()
        interval = 4
        count_per_type = 3
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--platform" and i + 1 < len(sys.argv):
                platform = sys.argv[i + 1]; i += 2
            elif sys.argv[i] == "--start" and i + 1 < len(sys.argv):
                start = sys.argv[i + 1]; i += 2
            elif sys.argv[i] == "--interval" and i + 1 < len(sys.argv):
                interval = float(sys.argv[i + 1]); i += 2
            elif sys.argv[i] == "--count-per-type" and i + 1 < len(sys.argv):
                count_per_type = int(sys.argv[i + 1]); i += 2
            else:
                i += 1

        entities = spawner.schedule_campaign(platform, start, interval, count_per_type)
        print(f"Scheduled {len(entities)} entities")
        for e in entities[:5]:
            print(f"  [{e.scheduled_time[:16]}] {e.type}: {e.content[:60]}...")
        print(f"  ... and {len(entities) - 5} more")

    elif cmd == "status":
        status = spawner.status()
        print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
