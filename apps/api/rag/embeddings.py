"""Embedding backend with two interchangeable implementations.

`ollama` calls Ollama's HTTP API. `sentence-transformers` loads the HF model
in-process — used as fallback when Ollama upstream lacks the Qwen3-Embedding tag.
The selection is driven by the `EMBED_BACKEND` env var.
"""
from __future__ import annotations

from typing import Protocol

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from apps.api.core.config import Settings


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def aclose(self) -> None: ...


class OllamaEmbedder:
    def __init__(self, host: str, model: str) -> None:
        self._client = httpx.AsyncClient(base_url=host, timeout=60.0)
        self._model = model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def _embed_one(self, text: str) -> list[float]:
        r = await self._client.post(
            "/api/embeddings",
            json={"model": self._model, "prompt": text},
        )
        r.raise_for_status()
        return r.json()["embedding"]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Ollama's /api/embeddings is single-input; loop sequentially.
        # For batched throughput, switch to /api/embed (newer, batch-capable).
        out: list[list[float]] = []
        for t in texts:
            out.append(await self._embed_one(t))
        return out

    async def aclose(self) -> None:
        await self._client.aclose()


class SentenceTransformersEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # lazy import

        self._model = SentenceTransformer(model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Library is sync; embeddings on CPU are fast enough for our scale.
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]

    async def aclose(self) -> None:
        return None


def build_embedder(settings: Settings) -> Embedder:
    backend = settings.embed_backend.lower()
    if backend == "ollama":
        return OllamaEmbedder(settings.ollama_host, settings.embed_model)
    if backend == "sentence-transformers":
        return SentenceTransformersEmbedder(settings.embed_model)
    raise ValueError(f"Unknown EMBED_BACKEND: {settings.embed_backend}")
