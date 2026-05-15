"""
chat.py — Endpoint principal del agente TQ-Asistente.

Flujo del agente:
  1. El router analiza la pregunta del usuario.
  2. Si contiene palabras clave de datos concretos (telefono, horario, NIT, etc.)
     → Herramienta estructurada: respuesta determinista desde datos_estructurados.json
  3. Si es una pregunta abierta sobre la empresa, productos, historia, etc.
     → RAG: recuperacion semantica desde pgvector + respuesta generada por Qwen3-8B

El historial de conversacion se recibe del cliente en cada turno (stateless en
el backend; la persistencia es responsabilidad de los endpoints /api/threads/*).
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


async def _load_history_from_db(pool, thread_id: UUID) -> list[dict[str, str]]:
    """Carga el historial de mensajes de un hilo desde la base de datos."""
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


# ── Prompt de sistema para el agente enrutador ───────────────────────────────
AGENT_ROUTER_SYSTEM = """Eres TQ-Asistente, el agente conversacional oficial de Tecnoquímicas S.A.

Tienes acceso a dos fuentes de información:

HERRAMIENTA 1 — Base de conocimiento documental (RAG):
Usa esta herramienta para preguntas abiertas sobre historia, productos, marcas,
sostenibilidad, innovación, cultura corporativa, valores, y cualquier tema que
requiera comprensión de contexto amplio.

HERRAMIENTA 2 — Datos estructurados:
Usa esta herramienta para preguntas específicas con respuesta exacta: teléfono,
horario de atención, NIT, dirección de sedes, lista de marcas, portal de empleo.

Reglas:
1. Responde SIEMPRE en español neutro, claro y profesional.
2. Basa tu respuesta ÚNICAMENTE en la información proporcionada en el contexto.
3. Si no tienes la información, di exactamente: "No encuentro esa información en
   las fuentes disponibles. Te recomiendo consultar www.tqconfiable.com"
4. Máximo 6 oraciones, salvo que el usuario pida detalle.
5. No menciones cuál herramienta usaste ni el proceso interno.
"""

STRUCTURED_RESPONSE_SYSTEM = """Eres TQ-Asistente, el agente oficial de Tecnoquímicas S.A.
Responde de forma directa, clara y profesional en español.
Presenta la información de forma ordenada. Máximo 4 oraciones."""


def _sse(data: str, event: str | None = None) -> str:
    """Formatea un evento SSE correctamente."""
    prefix = f"event: {event}\n" if event else ""
    safe = data.replace("\r\n", "\n")
    lines = "\n".join(f"data: {ln}" for ln in safe.split("\n"))
    return f"{prefix}{lines}\n\n"


@router.post("/api/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    """
    Endpoint principal del agente conversacional.

    El agente decide entre dos rutas:
    - Ruta A (datos estructurados): respuesta determinista para datos concretos
    - Ruta B (RAG): recuperacion semantica + generacion con Qwen3-8B
    """
    app = request.app
    settings = app.state.settings
    pool = app.state.pool
    embedder = app.state.embedder
    ollama = app.state.ollama

    async def gen() -> AsyncIterator[str]:
        try:
            # Si hay thread_id, cargar historial desde la base de datos
            # (memoria persistente entre sesiones). Si no, usar el historial
            # que envia el cliente.
            if payload.thread_id:
                history = await _load_history_from_db(pool, payload.thread_id)
            else:
                history = [m.model_dump() for m in payload.history]

            # ── DECISION DEL ROUTER ──────────────────────────────────────────
            # El router analiza la pregunta y decide qué herramienta usar.
            # Esta es la lógica del agente: no responde directamente sino que
            # primero selecciona la herramienta adecuada.

            if needs_structured_tool(payload.question):
                # ── RUTA A: Herramienta de datos estructurados ────────────────
                # Para preguntas con datos concretos: telefono, horario, NIT, etc.
                # No usa RAG ni embeddings — recuperacion determinista desde JSON.

                # Indicar al cliente que no hay fuentes RAG (datos son internos)
                tool_source = [{
                    "url": "datos_estructurados.json",
                    "title": "Datos oficiales TQ (herramienta estructurada)",
                    "score": 1.0
                }]
                yield _sse(json.dumps(tool_source, ensure_ascii=False), event="sources")

                # Recuperar datos exactos
                structured_context = get_structured_data(payload.question)

                # Construir prompt con los datos estructurados como contexto
                user_prompt = (
                    f"Información disponible sobre Tecnoquímicas:\n\n"
                    f"{structured_context}\n\n"
                    f"Pregunta del usuario: {payload.question}\n\n"
                    f"Responde de forma directa y concisa usando la información anterior."
                )

                # Generar respuesta con el LLM usando los datos estructurados
                async for token in ollama.stream_chat(
                    STRUCTURED_RESPONSE_SYSTEM, user_prompt, history=history
                ):
                    yield _sse(token, event="token")

            else:
                # ── RUTA B: RAG — recuperacion semantica ──────────────────────
                # Para preguntas abiertas sobre la empresa, historia, productos, etc.
                # Recupera chunks relevantes por similitud coseno desde pgvector.

                chunks = await retrieve(pool, embedder, payload.question, k=settings.top_k)

                # Filtrar ruido semantico: chunks bajo el umbral no aportan contexto
                relevant = [c for c in chunks if c.score >= settings.min_score]

                sources = [
                    Source(url=c.url, title=c.title, score=c.score).model_dump()
                    for c in relevant
                ]
                yield _sse(json.dumps(sources, ensure_ascii=False), event="sources")

                # Construir prompt con los chunks recuperados. Se adjunta el
                # conteo agregado del corpus (calculado al arranque) para que
                # el LLM pueda responder preguntas de cantidad que la
                # recuperación semántica top-k no cubre.
                user_prompt = build_user_prompt(
                    payload.question,
                    relevant,
                    settings.max_context_chars,
                    corpus_note=app.state.corpus_stats.as_prompt_note(),
                )

                # Generar respuesta con el LLM usando el contexto RAG
                async for token in ollama.stream_chat(
                    SYSTEM_PROMPT, user_prompt, history=history
                ):
                    yield _sse(token, event="token")

            yield _sse("ok", event="done")

        except Exception as e:
            err = {
                "error": "Hubo un problema al procesar tu pregunta.",
                "detail": str(e)
            }
            yield _sse(json.dumps(err, ensure_ascii=False), event="error")

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
