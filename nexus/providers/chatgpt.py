"""
ChatGPT Provider — OpenAI API adapter.

Handles conversation, reasoning, code generation, and creative tasks.
Best for: complex reasoning, code, creative writing, multi-turn dialogue.
"""

from __future__ import annotations

import time
import json
from typing import List, Optional

import httpx

from .base import BaseProvider, Message, ProviderResponse


CHATGPT_API = "https://api.openai.com/v1/chat/completions"

# Models in priority order (fallback chain)
CHATGPT_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
]


class ChatGPTProvider(BaseProvider):
    """OpenAI ChatGPT API adapter."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini",
                 system_prompt: str = "", **kwargs):
        super().__init__("chatgpt", api_key, **kwargs)
        self.model = model
        self.system_prompt = system_prompt
        self.client = httpx.AsyncClient(timeout=120.0)

    def format_messages(self, messages: List[Message]) -> list:
        """Convert to OpenAI message format."""
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
        """Send chat completion request to OpenAI."""
        if not self.enabled:
            return ProviderResponse(
                content="[ChatGPT disabled — no API key]",
                provider=self.name,
            )

        start = time.time()
        self.total_requests += 1

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": self.format_messages(messages),
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }

        # Optional tools/functions
        if "tools" in kwargs:
            payload["tools"] = kwargs["tools"]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = await self.client.post(
                CHATGPT_API,
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

            # Handle tool calls
            if message.get("tool_calls"):
                content = json.dumps(message["tool_calls"])

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
                    "finish_reason": choice.get("finish_reason"),
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                },
                raw=data,
            )

        except httpx.HTTPStatusError as e:
            self.error_count += 1
            error_body = e.response.text[:500] if e.response else str(e)
            return ProviderResponse(
                content=f"[ChatGPT error: {e.response.status_code}] {error_body}",
                provider=self.name,
                metadata={"error": True, "status_code": e.response.status_code},
            )
        except Exception as e:
            self.error_count += 1
            return ProviderResponse(
                content=f"[ChatGPT error: {type(e).__name__}] {str(e)}",
                provider=self.name,
                metadata={"error": True},
            )

    async def close(self):
        await self.client.aclose()
