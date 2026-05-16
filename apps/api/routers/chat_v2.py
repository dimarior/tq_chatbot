"""
chat_v2.py — Endpoint principal del agente TQ-Asistente.

Después de la introducción del grafo LangGraph (commits feat/graph), este
módulo es un traductor delgado entre el StateGraph y SSE: parsea la request,
invoca graph.astream con stream_mode=["updates", "messages"] y traduce los
eventos del grafo al contrato SSE que el frontend ya consume:

  event: sources   data: JSON array de {url, title, score}
  event: token     data: delta de texto (el cliente acumula)
  event: done      data: "ok"
  event: error     data: {"error": "...", "detail": "..."}

La memoria del hilo la maneja AsyncPostgresSaver: el grafo carga el state
previo desde la tabla `checkpoints` (creada por el checkpointer al arranque)
usando `configurable.thread_id`. El cliente sigue enviando `history` por
compatibilidad pero el backend lo ignora — el `messages` del state es la
única fuente de verdad para el LLM.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk

from apps.api.schemas import ChatRequest, Source


router = APIRouter()


def _sse(data: str, event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    safe = data.replace("\r\n", "\n")
    lines = "\n".join(f"data: {ln}" for ln in safe.split("\n"))
    return f"{prefix}{lines}\n\n"


def _sources_payload(sources) -> str:
    """Acepta tanto modelos Pydantic como dicts (depende de cómo LangGraph
    serializa los nodos al pasar por updates)."""
    out: list[dict] = []
    for s in sources or []:
        if isinstance(s, Source):
            out.append(s.model_dump())
        elif isinstance(s, dict):
            out.append(s)
    return json.dumps(out, ensure_ascii=False)


@router.post("/api/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    graph = request.app.state.graph

    async def gen() -> AsyncIterator[str]:
        try:
            config = {"configurable": {"thread_id": str(payload.thread_id)}}
            inputs = {"question": payload.question}

            async for stream_mode, data in graph.astream(
                inputs,
                config=config,
                stream_mode=["updates", "messages"],
            ):
                if stream_mode == "updates":
                    # data es {node_name: {state_keys_changed: ...}}.
                    # Sólo nos interesan los nodos que producen sources.
                    for node_name, update in data.items():
                        if node_name in ("structured", "retrieve"):
                            sources = update.get("sources", []) if update else []
                            yield _sse(_sources_payload(sources), event="sources")

                elif stream_mode == "messages":
                    # data es (BaseMessage|MessageChunk, metadata).
                    # Filtramos en dos pasos:
                    # 1) Sólo el nodo `generate` — evita emitir los tokens
                    #    del clasificador del router como respuesta al usuario.
                    # 2) Sólo AIMessageChunk — descarta los HumanMessage y
                    #    AIMessage completos que LangGraph también emite por
                    #    este canal cuando `generate_node` retorna
                    #    `{"messages": [HumanMessage(q), AIMessage(full)]}`
                    #    y `add_messages` los aplica al state. Sin este filtro
                    #    el frontend recibía la pregunta del usuario y la
                    #    respuesta completa duplicadas tras los chunks.
                    chunk, metadata = data
                    if metadata.get("langgraph_node") != "generate":
                        continue
                    if not isinstance(chunk, AIMessageChunk):
                        continue
                    piece = chunk.content if isinstance(chunk.content, str) else ""
                    if piece:
                        yield _sse(piece, event="token")

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
