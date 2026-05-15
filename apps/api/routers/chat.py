from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from apps.api.rag.prompt import SYSTEM_PROMPT, build_user_prompt
from apps.api.rag.retriever import retrieve
from apps.api.schemas import ChatMessage, ChatRequest, Source
from apps.api.routers.threads import list_messages, _parse_sources, MessageOut
import json


router = APIRouter()


def _sse(data: str, event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    # SSE requires data lines to be prefixed; newlines inside data must be split.
    safe = data.replace("\r\n", "\n")
    lines = "\n".join(f"data: {ln}" for ln in safe.split("\n"))
    return f"{prefix}{lines}\n\n"


@router.post("/api/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    app = request.app
    settings = app.state.settings
    vector_store = app.state.vector_store
    ollama_embedder = app.state.ollama_embedder
    ollama = app.state.ollama

    async def gen() -> AsyncIterator[str]:
        try:
            chunks = await retrieve(vector_store, ollama_embedder, payload.question, k=settings.top_k, min_score=settings.min_score)
            # Filtra ruido semántico: chunks por debajo del umbral rara vez
            # aportan a la respuesta y ensucian los chips de fuentes del widget.
            relevant = [c for c in chunks if c.score >= settings.min_score]
            sources = [
                Source(url=c.url, title=c.title, score=c.score).model_dump()
                for c in relevant
            ]
            yield _sse(json.dumps(sources, ensure_ascii=False), event="sources")

            user_prompt = build_user_prompt(payload.question, relevant, settings.max_context_chars)

            full_history: list[ChatMessage] = []
            if payload.thread_id:
                thread_messages = await list_messages(payload.thread_id, request)
                for msg_out in thread_messages:
                    full_history.append(ChatMessage(role=msg_out.role, content=msg_out.content))

            # Priorizar el historial del hilo sobre el historial del payload si ambos existen
            if payload.history:
                full_history.extend(payload.history)

            history = [m.model_dump() for m in full_history]

            async for token in ollama.stream_chat(SYSTEM_PROMPT, user_prompt, history=history):
                yield _sse(token, event="token")

            yield _sse("ok", event="done")
        except Exception as e:  # surfaced as a friendly Spanish error to the UI
            err = {"error": "Hubo un problema al procesar tu pregunta.", "detail": str(e)}
            yield _sse(json.dumps(err, ensure_ascii=False), event="error")

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
