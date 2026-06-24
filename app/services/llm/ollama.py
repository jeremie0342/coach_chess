"""Thin async client around the local Ollama HTTP server.

Ollama exposes /api/generate (streaming) and /api/chat. We use /api/chat
with non-streaming responses to keep request handling simple.

Docs: https://github.com/ollama/ollama/blob/main/docs/api.md
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx
import json as _json

from app.core.config import get_settings


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str

    def asdict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


class OllamaClient:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        s = get_settings()
        self.base_url = (base_url or s.ollama_base_url).rstrip("/")
        self.model = model or s.ollama_model
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(300.0, connect=5.0),
        )

    async def __aenter__(self) -> "OllamaClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def list_models(self) -> list[dict]:
        r = await self._client.get("/api/tags")
        r.raise_for_status()
        return r.json().get("models", [])

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.3,
        num_predict: int = 512,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [m.asdict() for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
            },
        }
        r = await self._client.post("/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
        return (data.get("message") or {}).get("content", "").strip()

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.3,
        num_predict: int = 512,
    ) -> AsyncIterator[str]:
        """Stream the assistant content token by token via Ollama's NDJSON output."""
        payload = {
            "model": self.model,
            "messages": [m.asdict() for m in messages],
            "stream": True,
            "options": {"temperature": temperature, "num_predict": num_predict},
        }
        async with self._client.stream("POST", "/api/chat", json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                msg = obj.get("message") or {}
                chunk = msg.get("content", "")
                if chunk:
                    yield chunk
                if obj.get("done"):
                    return
