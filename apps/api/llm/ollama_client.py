"""Async streaming client for Ollama's /api/chat endpoint."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx


class OllamaClient:
    def __init__(self, host: str, model: str) -> None:
        self._client = httpx.AsyncClient(base_url=host, timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0))
        self._model = model

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        try:
            r = await self._client.get("/api/tags")
            r.raise_for_status()
            return True
        except Exception:
            return False

    async def stream_chat(
        self,
        system: str,
        user: str,
        history: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        messages: list[dict] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            # Qwen3 es thinking-model: sin esto emite cientos de tokens internos
            # en `message.thinking` y deja `message.content` vacío, rompiendo el
            # streaming hacia el cliente.
            "think": False,
            "options": {"temperature": 0.2, "num_ctx": 8192},
        }

        async with self._client.stream("POST", "/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for raw in resp.aiter_lines():
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message") or {}
                token = msg.get("content")
                if token:
                    yield token
                if obj.get("done"):
                    break

    async def complete(self, system: str, user: str) -> str:
        """Drena stream_chat en un único string. Para tareas one-shot
        (p.ej. generación de títulos), sin necesidad de SSE al cliente."""
        parts: list[str] = []
        async for token in self.stream_chat(system, user):
            parts.append(token)
        return "".join(parts).strip()
