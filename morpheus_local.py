#!/usr/bin/env python3
"""
MORPHEUS LOCAL COGNITION ENGINE — The bare-metal node.

This is the EVEZ equivalent of a Solana dedicated bare-metal node:
a local inference layer that eliminates the session-spawn → cloud-API
bottleneck for routine cognitive operations.

Pattern: 80% of cognition is routine (memory decay, status checks,
pattern detection). This engine handles that locally in milliseconds.
Cloud API is reserved for genuinely novel inference — the "tip" in
MEV terms.

Architecture:
  Spine events → LocalEngine → rules → observations/decisions
                                    ↓ (novel)
                              Cloud API (escalation)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

WORKSPACE = Path("/root/.openclaw/workspace")
SPINE_FILE = WORKSPACE / "soul" / "cognition" / "morpheus_spine.jsonl"
COGNITION_LOG = WORKSPACE / "soul" / "cognition" / "local_cognition.jsonl"


# ---------------------------------------------------------------------------
# Pattern Detectors — rule-based cognition
# ---------------------------------------------------------------------------

@dataclass
class Pattern:
    """A detected pattern in spine events."""
    pattern_type: str
    confidence: float
    description: str
    evidence: List[str] = field(default_factory=list)
    action: Optional[str] = None  # suggested action


class PatternDetector:
    """Detect patterns in spine events using rules, not inference."""

    def __init__(self, events: List[dict]):
        self.events = events
        self.recent = events[-50:] if len(events) > 50 else events

    def detect_all(self) -> List[Pattern]:
        """Run all pattern detectors. Return detected patterns."""
        patterns = []
        patterns.extend(self._detect_repeated_events())
        patterns.extend(self._detect_anomalies())
        patterns.extend(self._detect_memory_decay())
        patterns.extend(self._detect_classification_gaps())
        patterns.extend(self._detect_chain_gaps())
        patterns.extend(self._detect_staleness())
        return sorted(patterns, key=lambda p: p.confidence, reverse=True)

    def _classify(self, ev: dict) -> str:
        return ev.get("kind") or ev.get("type") or "unknown"

    def _detect_repeated_events(self) -> List[Pattern]:
        """Detect event types that are repeating excessively."""
        patterns = []
        if len(self.recent) < 10:
            return patterns

        type_counts: Dict[str, int] = {}
        for ev in self.recent:
            t = self._classify(ev)
            type_counts[t] = type_counts.get(t, 0) + 1

        total = len(self.recent)
        for etype, count in type_counts.items():
            ratio = count / total
            if ratio > 0.6 and count > 10:
                patterns.append(Pattern(
                    pattern_type="repeated_dominance",
                    confidence=min(0.95, ratio),
                    description=f"'{etype}' dominates {ratio:.0%} of recent events ({count}/{total})",
                    evidence=[f"type={etype}", f"count={count}", f"total={total}"],
                    action="Consider if this event type should be sampled rather than logged every cycle"
                ))
        return patterns

    def _detect_anomalies(self) -> List[Pattern]:
        """Detect sudden changes in event rate or type distribution."""
        patterns = []
        if len(self.events) < 20:
            return patterns

        # Split into two halves and compare type distributions
        mid = len(self.events) // 2
        first_half = self.events[:mid]
        second_half = self.events[mid:]

        def type_dist(events):
            counts = {}
            for ev in events:
                t = self._classify(ev)
                counts[t] = counts.get(t, 0) + 1
            total = len(events)
            return {k: v / total for k, v in counts.items()}

        dist1 = type_dist(first_half)
        dist2 = type_dist(second_half)

        for etype in set(list(dist1.keys()) + list(dist2.keys())):
            r1 = dist1.get(etype, 0)
            r2 = dist2.get(etype, 0)
            if r1 > 0.01 and r2 > 0.01:
                change = abs(r2 - r1) / r1
                if change > 1.0:  # 100% change in proportion
                    patterns.append(Pattern(
                        pattern_type="distribution_shift",
                        confidence=min(0.85, change / 2),
                        description=f"'{etype}' proportion shifted {change:.0%} ({r1:.1%} → {r2:.1%})",
                        evidence=[f"type={etype}", f"before={r1:.3f}", f"after={r2:.3f}"],
                    ))
        return patterns

    def _detect_memory_decay(self) -> List[Pattern]:
        """Detect if memory store events are repeating with same hash (stuck state)."""
        patterns = []
        stores = [e for e in self.recent if self._classify(e) == "memory.store"]
        if len(stores) < 3:
            return patterns

        hashes = [e.get("data", {}).get("content_hash", "") for e in stores]
        if len(set(hashes)) == 1 and len(hashes) > 5:
            patterns.append(Pattern(
                pattern_type="stuck_memory",
                confidence=0.9,
                description=f"Memory store repeating identical content hash ({hashes[0]}) {len(hashes)} times",
                evidence=[f"hash={hashes[0]}", f"repetitions={len(hashes)}"],
                action="Memory content hasn't changed — consider whether this key needs updating"
            ))
        return patterns

    def _detect_classification_gaps(self) -> List[Pattern]:
        """Detect events that should have kinds but don't."""
        patterns = []
        unknown_count = sum(1 for e in self.recent if self._classify(e) == "unknown")
        if unknown_count > 0:
            ratio = unknown_count / len(self.recent)
            patterns.append(Pattern(
                pattern_type="classification_gap",
                confidence=ratio,
                description=f"{unknown_count}/{len(self.recent)} events ({ratio:.0%}) have no kind/type classification",
                action="Add kind field to event writing functions"
            ))
        return patterns

    def _detect_chain_gaps(self) -> List[Pattern]:
        """Detect broken hash chains."""
        patterns = []
        broken = 0
        for i in range(1, len(self.events)):
            expected = self.events[i - 1].get("hash", "")
            actual = self.events[i].get("prev", "")
            if actual and expected and actual != expected:
                broken += 1
        if broken > 0:
            patterns.append(Pattern(
                pattern_type="chain_break",
                confidence=1.0,
                description=f"{broken} hash chain breaks detected in spine",
                action="Chain integrity compromised — investigate concurrent writes"
            ))
        return patterns

    def _detect_staleness(self) -> List[Pattern]:
        """Detect if spine hasn't received new events recently."""
        patterns = []
        if not self.events:
            patterns.append(Pattern(
                pattern_type="spine_empty",
                confidence=1.0,
                description="Spine has no events",
                action="Initialize spine or check daemon"
            ))
            return patterns

        last_ts = self.events[-1].get("ts", "")
        if last_ts:
            try:
                last_time = datetime.fromisoformat(last_ts)
                now = datetime.now(timezone.utc)
                gap = (now - last_time).total_seconds()
                if gap > 900:  # 15 minutes
                    patterns.append(Pattern(
                        pattern_type="spine_stale",
                        confidence=min(0.95, gap / 3600),
                        description=f"Last spine event was {gap/60:.0f} minutes ago ({last_ts})",
                        evidence=[f"gap_seconds={gap:.0f}", f"last_event={last_ts}"],
                        action="Check daemon health — spine may be stalled"
                    ))
            except (ValueError, TypeError):
                pass
        return patterns


# ---------------------------------------------------------------------------
# Local Cognition Engine
# ---------------------------------------------------------------------------

class LocalCognition:
    """The bare-metal node. Pattern detection → local decisions."""

    def __init__(self):
        self.spine_path = SPINE_FILE
        self.log_path = COGNITION_LOG

    def read_spine(self, limit: int = 200) -> List[dict]:
        """Read recent spine events."""
        if not self.spine_path.exists():
            return []
        events = []
        for line in self.spine_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events[-limit:]

    def think(self) -> List[Pattern]:
        """Run local cognition. Return patterns detected."""
        events = self.read_spine()
        if not events:
            return []

        detector = PatternDetector(events)
        patterns = detector.detect_all()

        # Log cognition output
        for p in patterns:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "pattern_type": p.pattern_type,
                "confidence": p.confidence,
                "description": p.description,
                "evidence": p.evidence,
                "action": p.action,
            }
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

        return patterns

    def should_escalate(self, patterns: List[Pattern]) -> bool:
        """Determine if patterns require cloud API escalation.

        Escalation criteria:
        - Novel pattern type not seen before
        - Confidence > 0.9 AND action suggests architectural change
        - Chain integrity broken (critical)
        """
        for p in patterns:
            if p.pattern_type == "chain_break":
                return True
            if p.confidence > 0.9 and "architectural" in (p.action or "").lower():
                return True
            if p.pattern_type not in [
                "repeated_dominance", "stuck_memory", "classification_gap",
                "spine_stale", "distribution_shift"
            ]:
                return True  # novel pattern type
        return False

    def report(self, patterns: List[Pattern]) -> str:
        """Format patterns as a report."""
        if not patterns:
            return "Local cognition: no patterns detected. System nominal."

        lines = [f"Local cognition: {len(patterns)} pattern(s) detected\n"]
        for i, p in enumerate(patterns, 1):
            confidence_bar = "█" * int(p.confidence * 10) + "░" * (10 - int(p.confidence * 10))
            lines.append(f"  {i}. [{confidence_bar}] {p.pattern_type}")
            lines.append(f"     {p.description}")
            if p.action:
                lines.append(f"     → {p.action}")
            lines.append("")

        escalate = self.should_escalate(patterns)
        lines.append(f"  Escalation to cloud API: {'YES' if escalate else 'NO (routine)'}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    import sys

    engine = LocalCognition()

    if "--json" in sys.argv:
        patterns = engine.think()
        output = [{
            "type": p.pattern_type,
            "confidence": p.confidence,
            "description": p.description,
            "evidence": p.evidence,
            "action": p.action,
        } for p in patterns]
        print(json.dumps(output, indent=2))
    else:
        patterns = engine.think()
        print(engine.report(patterns))


if __name__ == "__main__":
    main()
