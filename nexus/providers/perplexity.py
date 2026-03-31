"""
Perplexity Provider — search-augmented reasoning adapter.

Handles web search, research synthesis, citation-backed answers.
Best for: current events, fact-checking, research, anything requiring web data.

Perplexity's API returns answers with citations — perfect for grounding
reasoning in real-time data rather than training cutoff.
"""

from __future__ import annotations

import time
import json
from typing import List, Optional

import httpx

from .base import BaseProvider, Message, ProviderResponse


PERPLEXITY_API = "https://api.perplexity.ai/chat/completions"

# Models
PERPLEXITY_MODELS = [
    "sonar-pro",       # Most capable, web search
    "sonar",           # Fast, web search
    "sonar-reasoning", # Chain-of-thought with search
]


class PerplexityProvider(BaseProvider):
    """Perplexity AI API adapter."""

    def __init__(self, api_key: str, model: str = "sonar",
                 system_prompt: str = "", **kwargs):
        super().__init__("perplexity", api_key, **kwargs)
        self.model = model
        self.system_prompt = system_prompt
        self.client = httpx.AsyncClient(timeout=120.0)

    def format_messages(self, messages: List[Message]) -> list:
        """Convert to Perplexity message format."""
        formatted = []
        if self.system_prompt:
            formatted.append({"role": "system", "content": self.system_prompt})
        for msg in messages:
            formatted.append({
                "role": msg.role,
                "content": msg.content,
            })
        return formatted

    async def chat(self, messages: List[Message], **kwargs) -> ProviderResponse:
        """Send chat request to Perplexity."""
        if not self.enabled:
            return ProviderResponse(
                content="[Perplexity disabled — no API key]",
                provider=self.name,
            )

        start = time.time()
        self.total_requests += 1

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": self.format_messages(messages),
            "temperature": kwargs.get("temperature", 0.2),
            "return_citations": True,
            "return_images": False,
        }

        # Search domain filter
        if "search_domains" in kwargs:
            payload["search_domain_filter"] = kwargs["search_domains"]

        # Recency filter
        if "search_recency" in kwargs:
            payload["search_recency_filter"] = kwargs["search_recency"]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = await self.client.post(
                PERPLEXITY_API,
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            latency = (time.time() - start) * 1000

            # Extract response
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content", "")

            # Extract citations from metadata
            citations = []
            search_results = data.get("search_results", [])
            for sr in search_results:
                citations.append({
                    "title": sr.get("title", ""),
                    "url": sr.get("url", ""),
                    "date": sr.get("date", ""),
                })

            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            self.total_tokens += tokens

            return ProviderResponse(
                content=content or "[empty response]",
                provider=self.name,
                model=data.get("model", self.model),
                tokens_used=tokens,
                latency_ms=latency,
                metadata={
                    "citations": citations,
                    "finish_reason": choice.get("finish_reason"),
                },
                raw=data,
            )

        except httpx.HTTPStatusError as e:
            self.error_count += 1
            error_body = e.response.text[:500] if e.response else str(e)
            return ProviderResponse(
                content=f"[Perplexity error: {e.response.status_code}] {error_body}",
                provider=self.name,
                metadata={"error": True, "status_code": e.response.status_code},
            )
        except Exception as e:
            self.error_count += 1
            return ProviderResponse(
                content=f"[Perplexity error: {type(e).__name__}] {str(e)}",
                provider=self.name,
                metadata={"error": True},
            )

    async def close(self):
        await self.client.aclose()
