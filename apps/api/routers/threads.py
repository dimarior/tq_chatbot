"""Endpoints de persistencia de hilos.

Implementa la superficie que assistant-ui's RemoteThreadListAdapter espera.
La paginación usa created_at ISO como cursor (descendente, hilos más recientes
primero). El orden del sidebar es estable: abrir, renombrar o responder un hilo
no debe cambiar su posición. El chat (`/api/chat`) sigue siendo stateless: la
persistencia es responsabilidad de estos endpoints.
"""
from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response

from apps.api.schemas import (
    ChatMessage,
    MessageAppend,
    MessageOut,
    Source,
    ThreadCreate,
    ThreadListOut,
    ThreadOut,
    ThreadPatch,
    TitleRequest,
    TitleResponse,
)

router = APIRouter()

PAGE_SIZE = 30

TITLE_SYSTEM = (
    "Eres un asistente que genera títulos breves. Devuelve únicamente el "
    "título, en español, máximo 6 palabras, sin comillas ni puntos finales."
)


def _title_user_prompt(messages: list[ChatMessage]) -> str:
    sample = "\n".join(f"{m.role.upper()}: {m.content[:400]}" for m in messages[:4])
    return (
        "Resume el tema principal de esta conversación en un título corto "
        f"(máx. 6 palabras), en español:\n\n{sample}"
    )


def _parse_sources(value: object) -> list[Source] | None:
    if not value:
        return None
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        return None
    return [Source(**s) for s in value]


@router.get("/api/threads", response_model=ThreadListOut)
async def list_threads(request: Request, after: str | None = None) -> ThreadListOut:
    pool = request.app.state.pool
    cursor_dt: datetime | None = None
    if after:
        try:
            cursor_dt = datetime.fromisoformat(after)
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Cursor inválido") from e

    async with pool.acquire() as conn:
        if cursor_dt is None:
            rows = await conn.fetch(
                """
                SELECT id, title, archived, created_at
                FROM conversations
                WHERE EXISTS (
                    SELECT 1
                    FROM messages
                    WHERE conversation_id = conversations.id
                )
                ORDER BY created_at DESC
                LIMIT $1
                """,
                PAGE_SIZE + 1,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, title, archived, created_at
                FROM conversations
                WHERE created_at < $1
                  AND EXISTS (
                      SELECT 1
                      FROM messages
                      WHERE conversation_id = conversations.id
                  )
                ORDER BY created_at DESC
                LIMIT $2
                """,
                cursor_dt,
                PAGE_SIZE + 1,
            )

    next_cursor: str | None = None
    if len(rows) > PAGE_SIZE:
        next_cursor = rows[PAGE_SIZE - 1]["created_at"].isoformat()
        rows = rows[:PAGE_SIZE]

    threads = [ThreadOut(id=r["id"], title=r["title"], archived=r["archived"]) for r in rows]
    return ThreadListOut(threads=threads, next_cursor=next_cursor)


@router.post("/api/threads", response_model=ThreadOut)
async def create_thread(payload: ThreadCreate, request: Request) -> ThreadOut:
    new_id = uuid4()
    # assistant-ui puede pedir un hilo "draft" que nunca recibe mensajes
    # (por ejemplo, al montar o recargar una ruta existente). No lo
    # persistimos aquí para evitar basura; la conversación se materializa en el
    # primer append de mensaje.
    return ThreadOut(id=new_id, title="Nueva conversación", archived=False)


@router.get("/api/threads/{thread_id}", response_model=ThreadOut)
async def get_thread(thread_id: UUID, request: Request) -> ThreadOut:
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, title, archived FROM conversations WHERE id = $1",
            thread_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Hilo no encontrado")
    return ThreadOut(id=row["id"], title=row["title"], archived=row["archived"])


@router.patch("/api/threads/{thread_id}", status_code=204)
async def patch_thread(thread_id: UUID, payload: ThreadPatch, request: Request) -> Response:
    pool = request.app.state.pool
    sets: list[str] = []
    args: list = [thread_id]
    if payload.title is not None:
        args.append(payload.title)
        sets.append(f"title = ${len(args)}")
    if payload.archived is not None:
        args.append(payload.archived)
        sets.append(f"archived = ${len(args)}")
    if not sets:
        raise HTTPException(status_code=400, detail="Sin cambios")
    sets.append("updated_at = now()")

    async with pool.acquire() as conn:
        result = await conn.execute(
            f"UPDATE conversations SET {', '.join(sets)} WHERE id = $1",
            *args,
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=404, detail="Hilo no encontrado")
    return Response(status_code=204)


@router.delete("/api/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: UUID, request: Request) -> Response:
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM conversations WHERE id = $1", thread_id)
    return Response(status_code=204)


@router.post("/api/threads/{thread_id}/title", response_model=TitleResponse)
async def generate_title(thread_id: UUID, payload: TitleRequest, request: Request) -> TitleResponse:
    pool = request.app.state.pool
    ollama = request.app.state.ollama

    # Pre-check barato (un roundtrip) antes de gastar 2-5s en el LLM.
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM conversations WHERE id = $1", thread_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Hilo no encontrado")

    msgs = [m for m in payload.messages if m.content.strip()]
    if not msgs:
        return TitleResponse(title="Nueva conversación")

    raw = await ollama.complete(TITLE_SYSTEM, _title_user_prompt(msgs))
    # Modelos a veces devuelven el título envuelto en comillas o con prefijos.
    title = raw.strip().strip('"').strip("'").splitlines()[0][:80] or "Nueva conversación"

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE conversations
            SET title = $2, updated_at = now()
            WHERE id = $1
            """,
            thread_id,
            title,
        )

    return TitleResponse(title=title)


@router.get("/api/threads/{thread_id}/messages", response_model=list[MessageOut])
async def list_messages(thread_id: UUID, request: Request) -> list[MessageOut]:
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM conversations WHERE id = $1", thread_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Hilo no encontrado")
        rows = await conn.fetch(
            """
            SELECT id, parent_id, role, content, sources, created_at
            FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC
            """,
            thread_id,
        )

    out: list[MessageOut] = []
    for r in rows:
        sources = _parse_sources(r["sources"])
        out.append(
            MessageOut(
                id=r["id"],
                parent_id=r["parent_id"],
                role=r["role"],
                content=r["content"],
                sources=sources,
                created_at=r["created_at"],
            )
        )
    return out


@router.post("/api/threads/{thread_id}/messages")
async def append_message(thread_id: UUID, payload: MessageAppend, request: Request) -> dict:
    pool = request.app.state.pool
    msg = payload.message
    msg_id = msg.id or uuid4()
    sources_json = (
        json.dumps([s.model_dump() for s in msg.sources], ensure_ascii=False)
        if msg.sources is not None
        else None
    )

    # Un solo statement: INSERT + UPDATE conversations.updated_at via CTE.
    # La FK valida la existencia del hilo; un re-post idempotente (ON CONFLICT)
    # no bumpea updated_at, lo cual es la semántica correcta.
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO conversations (id)
            VALUES ($1)
            ON CONFLICT (id) DO NOTHING
            """,
            thread_id,
        )
        await conn.execute(
            """
            WITH ins AS (
                INSERT INTO messages (id, conversation_id, parent_id, role, content, sources)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                ON CONFLICT (id) DO NOTHING
                RETURNING conversation_id
            )
            UPDATE conversations
            SET updated_at = now()
            WHERE id = $2 AND EXISTS (SELECT 1 FROM ins)
            """,
            msg_id,
            thread_id,
            payload.parentId,
            msg.role,
            msg.content,
            sources_json,
        )

    return {"id": str(msg_id)}
