"""
Provider base class — all providers implement this interface.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


@dataclass
class Message:
    """Normalized message across all providers."""
    role: str  # "user", "assistant", "system"
    content: str
    provider: str  # "chatgpt", "perplexity", "openclaw", "nexus"
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        return cls(**d)

    def to_provider_format(self) -> dict:
        """Convert to provider-native format. Override in subclasses."""
        return {"role": self.role, "content": self.content}


@dataclass
class ProviderResponse:
    """Normalized response from any provider."""
    content: str
    provider: str
    model: str = ""
    tokens_used: int = 0
    latency_ms: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw: Optional[dict] = None  # full provider response for debugging


class BaseProvider(ABC):
    """Base class for all nexus providers."""

    def __init__(self, name: str, api_key: str = "", **kwargs):
        self.name = name
        self.api_key = api_key
        self.enabled = bool(api_key)
        self.error_count = 0
        self.total_requests = 0
        self.total_tokens = 0

    @abstractmethod
    async def chat(self, messages: List[Message], **kwargs) -> ProviderResponse:
        """Send messages, get response."""
        ...

    @abstractmethod
    def format_messages(self, messages: List[Message]) -> list:
        """Convert normalized messages to provider format."""
        ...

    def health_check(self) -> dict:
        """Provider health status."""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "error_count": self.error_count,
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
        }
