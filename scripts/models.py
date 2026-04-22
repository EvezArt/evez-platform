from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional
import time
import uuid


@dataclass(slots=True)
class Event:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""
    type: str = ""
    confidence: float = 0.0
    payload: Dict[str, Any] = field(default_factory=dict)
    proposed_action: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    correlation_id: Optional[str] = None
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            source=data.get("source", ""),
            type=data.get("type", ""),
            confidence=float(data.get("confidence", 0.0)),
            payload=dict(data.get("payload") or {}),
            proposed_action=dict(data.get("proposed_action") or {}),
            timestamp=float(data.get("timestamp", time.time())),
            correlation_id=data.get("correlation_id"),
            parent_id=data.get("parent_id"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(slots=True)
class ActionSpec:
    name: str
    target: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    min_confidence: float = 0.0
    retries: int = 0
    verify: bool = True
    tags: Dict[str, Any] = field(default_factory=dict)
