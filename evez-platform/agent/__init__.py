"""
EVEZ Agent — Autonomous tool-calling agent with multi-model support.

Replaces: OpenClaw agent, ChatGPT code interpreter
Cost: Free (Ollama local + free cloud fallback)
"""

import json
import os
import subprocess
import time
import logging
import re
from pathlib import Path
from typing import Optional, AsyncGenerator, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

import httpx

logger = logging.getLogger("evez.agent")


# ---------------------------------------------------------------------------
# Model Provider — free-tier fallback chain
# ---------------------------------------------------------------------------

class ModelProvider:
    """
    Free model chain:
    1. Ollama (local) — llama3.2, codellama, mistral
    2. KiloCode/OpenClaw — existing free API key
    3. OpenAI-compatible free tiers
    """

    def __init__(self):
        self.ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.kilocode_key = os.environ.get("KILOCODE_API_KEY", "")
        self.kilocode_url = os.environ.get("KILOCODE_API_URL", "https://api.kilo.dev/v1")
        self._ollama_available = None
        self._last_ollama_check = 0

    async def is_ollama_up(self) -> bool:
        now = time.time()
        if self._ollama_available is not None and now - self._last_ollama_check < 30:
            return self._ollama_available
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.ollama_url}/api/tags")
                self._ollama_available = r.status_code == 200
        except Exception:
            self._ollama_available = False
        self._last_ollama_check = now
        return self._ollama_available

    async def list_models(self) -> List[Dict[str, Any]]:
        models = []

        # Ollama models
        if await self.is_ollama_up():
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(f"{self.ollama_url}/api/tags")
                    data = r.json()
                    for m in data.get("models", []):
                        models.append({
                            "id": m["name"],
                            "name": m["name"],
                            "provider": "ollama",
                            "local": True,
                            "free": True,
                            "size": m.get("size", 0),
                        })
            except Exception:
                pass

        # KiloCode models (free tier)
        if self.kilocode_key:
            models.append({
                "id": "kilo-auto",
                "name": "KiloCode Auto (Free)",
                "provider": "kilocode",
                "local": False,
                "free": True,
            })

        # Default fallback
        if not models:
            models.append({
                "id": "stub",
                "name": "No Model Available (Install Ollama)",
                "provider": "none",
                "local": False,
                "free": True,
            })

        return models

    async def chat(self, messages: List[Dict[str, str]], model: str = None,
                   stream: bool = False):
        """Send chat completion, auto-selecting provider. Always an async generator."""

        # Determine provider from model name
        if model and not model.startswith("kilo"):
            # Ollama model
            if await self.is_ollama_up():
                async for chunk in self._ollama_chat(messages, model, stream):
                    yield chunk
                return
            model = None  # Fallback

        # KiloCode
        if self.kilocode_key:
            async for chunk in self._kilocode_chat(messages, model or "kilo-auto", stream):
                yield chunk
            return

        # Stub response
        yield "⚠️ No model available. Install Ollama (`curl -fsSL https://ollama.ai/install.sh | sh && ollama pull llama3.2`) or configure a cloud API key."

    async def _ollama_chat(self, messages, model, stream):
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            if stream:
                async with client.stream("POST", f"{self.ollama_url}/api/chat", json=payload) as r:
                    async for line in r.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                if "message" in data:
                                    yield data["message"].get("content", "")
                            except json.JSONDecodeError:
                                pass
            else:
                r = await client.post(f"{self.ollama_url}/api/chat", json=payload)
                data = r.json()
                yield data.get("message", {}).get("content", "")

    async def _kilocode_chat(self, messages, model, stream):
        headers = {
            "Authorization": f"Bearer {self.kilocode_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            if stream:
                async with client.stream("POST", f"{self.kilocode_url}/chat/completions",
                                         json=payload, headers=headers) as r:
                    async for line in r.aiter_lines():
                        if line and line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                delta = data.get("choices", [{}])[0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                            except json.JSONDecodeError:
                                pass
            else:
                r = await client.post(f"{self.kilocode_url}/chat/completions",
                                      json=payload, headers=headers)
                data = r.json()
                yield data.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def get_response(self, messages: List[Dict[str, str]], model: str = None) -> str:
        """Get a single response string (non-streaming convenience)."""
        result = ""
        async for chunk in self.chat(messages, model=model, stream=False):
            result += chunk if chunk else ""
        return result


# ---------------------------------------------------------------------------
# Tool System — what the agent can do
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    success: bool
    output: str
    error: str = ""

    def to_dict(self):
        return {"success": self.success, "output": self.output, "error": self.error}


class ToolRegistry:
    """Agent tools — shell, file, web, code execution."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.tools = {
            "shell": self._run_shell,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "web_fetch": self._web_fetch,
            "search": self._search,
        }

    def get_tool_descriptions(self) -> List[Dict]:
        return [
            {"name": "shell", "description": "Run a shell command", "params": {"command": "string"}},
            {"name": "read_file", "description": "Read a file", "params": {"path": "string"}},
            {"name": "write_file", "description": "Write content to a file", "params": {"path": "string", "content": "string"}},
            {"name": "web_fetch", "description": "Fetch a URL and extract text", "params": {"url": "string"}},
            {"name": "search", "description": "Search the web via DuckDuckGo", "params": {"query": "string"}},
        ]

    async def execute(self, tool_name: str, params: dict) -> ToolResult:
        if tool_name not in self.tools:
            return ToolResult(False, "", f"Unknown tool: {tool_name}")
        try:
            return await self.tools[tool_name](params)
        except Exception as e:
            return ToolResult(False, "", str(e))

    async def _run_shell(self, params: dict) -> ToolResult:
        cmd = params.get("command", "")
        if not cmd:
            return ToolResult(False, "", "No command provided")
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=30, cwd=str(self.workspace)
            )
            output = result.stdout + result.stderr
            return ToolResult(result.returncode == 0, output[:5000],
                            "" if result.returncode == 0 else f"Exit code: {result.returncode}")
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", "Command timed out (30s)")

    async def _read_file(self, params: dict) -> ToolResult:
        path = Path(params.get("path", ""))
        if not path.is_absolute():
            path = self.workspace / path
        try:
            content = path.read_text()
            return ToolResult(True, content[:10000])
        except Exception as e:
            return ToolResult(False, "", str(e))

    async def _write_file(self, params: dict) -> ToolResult:
        path = Path(params.get("path", ""))
        content = params.get("content", "")
        if not path.is_absolute():
            path = self.workspace / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            return ToolResult(True, f"Written {len(content)} bytes to {path}")
        except Exception as e:
            return ToolResult(False, "", str(e))

    async def _web_fetch(self, params: dict) -> ToolResult:
        url = params.get("url", "")
        if not url:
            return ToolResult(False, "", "No URL provided")
        try:
            from bs4 import BeautifulSoup
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "EVEZ/1.0"})
                soup = BeautifulSoup(r.text, "html.parser")
                # Remove scripts/styles
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                return ToolResult(True, text[:8000])
        except Exception as e:
            return ToolResult(False, "", str(e))

    async def _search(self, params: dict) -> ToolResult:
        query = params.get("query", "")
        if not query:
            return ToolResult(False, "", "No query provided")
        try:
            from duckduckgo_search import DDGS
            results = DDGS().text(query, max_results=8)
            formatted = []
            for r in results:
                formatted.append(f"**{r['title']}**\n{r['href']}\n{r['body']}\n")
            return ToolResult(True, "\n---\n".join(formatted))
        except Exception as e:
            return ToolResult(False, "", str(e))


# ---------------------------------------------------------------------------
# Agent Loop — ReAct-style tool-calling
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = """You are EVEZ, an autonomous cognitive agent. You have access to tools and can execute code, search the web, read/write files, and run shell commands.

When you need to take an action, respond with a JSON tool call:
```tool
{"tool": "tool_name", "params": {"key": "value"}}
```

Available tools:
- shell: Run shell commands
- read_file: Read a file from disk
- write_file: Write content to a file
- web_fetch: Fetch and extract text from a URL
- search: Search the web via DuckDuckGo

Think step by step. Use tools when needed. Be direct and useful."""


class Agent:
    """Autonomous agent with tool-calling loop."""

    def __init__(self, core, model_provider: ModelProvider):
        self.core = core
        self.models = model_provider
        self.tools = ToolRegistry(Path(os.environ.get("EVEZ_WORKSPACE", "/root/.openclaw/workspace")))
        self.max_steps = 10

    async def run(self, user_message: str, model: str = None,
                  conversation_id: str = None,
                  stream: bool = False):
        """Run the agent loop with tool calling."""

        # Build conversation context
        messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]

        # Add conversation history
        if conversation_id:
            history = self.core.conversations.get_messages(conversation_id, limit=20)
            for msg in history[-20:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": user_message})

        # Save user message
        if conversation_id:
            self.core.conversations.add_message(conversation_id, "user", user_message, model)

        # Agent loop
        full_response = ""
        for step in range(self.max_steps):
            # Get model response
            response_text = await self.models.get_response(messages, model=model)

            if not response_text:
                response_text = "I couldn't process that. Please check your model configuration."

            # Check for tool calls
            tool_match = re.search(r'```tool\s*\n(.*?)\n```', response_text, re.DOTALL)

            if not tool_match:
                # No tool call — final response
                full_response = response_text
                if conversation_id:
                    self.core.conversations.add_message(conversation_id, "assistant", full_response, model)
                if stream:
                    yield full_response
                else:
                    return full_response
                break

            # Execute tool
            try:
                tool_call = json.loads(tool_match.group(1))
                tool_name = tool_call.get("tool", "")
                tool_params = tool_call.get("params", {})

                # Add assistant message with tool call
                messages.append({"role": "assistant", "content": response_text})

                # Execute
                result = await self.tools.execute(tool_name, tool_params)

                # Add result to conversation
                tool_result_msg = f"Tool `{tool_name}` {'succeeded' if result.success else 'failed'}:\n{result.output or result.error}"
                messages.append({"role": "user", "content": tool_result_msg})

            except (json.JSONDecodeError, KeyError) as e:
                full_response = response_text  # Return as-is if tool parse fails
                if conversation_id:
                    self.core.conversations.add_message(conversation_id, "assistant", full_response, model)
                if stream:
                    yield full_response
                else:
                    return full_response
                break

        if not full_response:
            full_response = "Maximum steps reached. Here's what I have so far:\n\n" + response_text

        if stream:
            yield full_response
        else:
            return full_response
