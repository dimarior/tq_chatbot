"""
chat_v2.py — Endpoint principal del agente TQ-Asistente.

Flujo del agente:
  1. El router analiza la pregunta del usuario.
  2. Si contiene palabras clave de datos concretos (telefono, horario, NIT, etc.)
     → Herramienta estructurada: respuesta determinista desde datos_estructurados.json
  3. Si es una pregunta abierta sobre la empresa, productos, historia, etc.
     → RAG: recuperacion semantica desde Chroma + respuesta generada por Qwen3-8B

Memoria del hilo: cuando el cliente envía `thread_id`, el endpoint carga el
historial completo desde la tabla `messages` antes de invocar al LLM. Sin
`thread_id` se usa el `history` del payload (modo stateless).
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from apps.api.rag.prompt import SYSTEM_PROMPT, build_user_prompt
from apps.api.rag.retriever import retrieve
from apps.api.schemas import ChatRequest, Source
from apps.api.tools.structured_tool import get_structured_data, needs_structured_tool


router = APIRouter()


STRUCTURED_RESPONSE_SYSTEM = """Eres TQ-Asistente, el agente oficial de Tecnoquímicas S.A.
Responde de forma directa, clara y profesional en español.
Presenta la información de forma ordenada. Máximo 4 oraciones."""


async def _load_history_from_db(pool, thread_id: UUID) -> list[dict[str, str]]:
    """Carga el historial de mensajes persistidos de un hilo.

    Usado cuando el cliente envía `thread_id`: el backend deja de depender de
    que el cliente reenvíe `history`. Si la tabla está vacía (hilo borrador)
    devuelve [].
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC
            """,
            thread_id,
        )
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def _sse(data: str, event: str | None = None) -> str:
    """Formatea un evento SSE correctamente."""
    prefix = f"event: {event}\n" if event else ""
    safe = data.replace("\r\n", "\n")
    lines = "\n".join(f"data: {ln}" for ln in safe.split("\n"))
    return f"{prefix}{lines}\n\n"


@router.post("/api/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    app = request.app
    settings = app.state.settings
    pool = app.state.pool
    vector_store = app.state.vector_store
    ollama = app.state.ollama

    async def gen() -> AsyncIterator[str]:
        try:
            # Memoria del hilo: si llega thread_id, la verdad del historial vive
            # en `messages`. Si no, modo stateless con lo que mande el cliente.
            if payload.thread_id:
                history = await _load_history_from_db(pool, payload.thread_id)
            else:
                history = [m.model_dump() for m in payload.history]

            if needs_structured_tool(payload.question):
                # ── Ruta A: herramienta estructurada (datos exactos) ──────────
                tool_source = [{
                    "url": "datos_estructurados.json",
                    "title": "Datos oficiales TQ (herramienta estructurada)",
                    "score": 1.0,
                }]
                yield _sse(json.dumps(tool_source, ensure_ascii=False), event="sources")

                structured_context = get_structured_data(payload.question)
                user_prompt = (
                    f"Información disponible sobre Tecnoquímicas:\n\n"
                    f"{structured_context}\n\n"
                    f"Pregunta del usuario: {payload.question}\n\n"
                    f"Responde de forma directa y concisa usando la información anterior."
                )

                async for token in ollama.stream_chat(
                    STRUCTURED_RESPONSE_SYSTEM,
                    user_prompt,
                    history=history,
                    temperature=payload.temperature,
                ):
                    yield _sse(token, event="token")

            else:
                # ── Ruta B: RAG sobre Chroma ──────────────────────────────────
                # El retriever ya descarta los chunks bajo min_score; no hace
                # falta un segundo filtro acá.
                chunks = await retrieve(
                    vector_store,
                    payload.question,
                    k=payload.top_k,
                    min_score=settings.min_score,
                )

                sources = [
                    Source(url=c.url, title=c.title, score=c.score).model_dump()
                    for c in chunks
                ]
                yield _sse(json.dumps(sources, ensure_ascii=False), event="sources")

                user_prompt = build_user_prompt(
                    payload.question,
                    chunks,
                    settings.max_context_chars,
                    corpus_note=app.state.corpus_stats.as_prompt_note(),
                )

                async for token in ollama.stream_chat(
                    SYSTEM_PROMPT,
                    user_prompt,
                    history=history,
                    temperature=payload.temperature,
                ):
                    yield _sse(token, event="token")

            yield _sse("ok", event="done")

        except Exception as e:
            err = {
                "error": "Hubo un problema al procesar tu pregunta.",
                "detail": str(e),
            }
            yield _sse(json.dumps(err, ensure_ascii=False), event="error")

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
