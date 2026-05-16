"""Endpoints de persistencia de hilos sobre SQLite.

Implementa la superficie que assistant-ui's RemoteThreadListAdapter espera.
La paginación usa created_at ISO como cursor (descendente, hilos más recientes
primero). El orden del sidebar es estable: abrir, renombrar o responder un
hilo no debe cambiar su posición. La memoria conversacional del LLM la lleva
LangGraph (AsyncSqliteSaver en las tablas `checkpoints*`); estas tablas
(`conversations`, `messages`) son la vista persistida para el frontend.
"""
from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from langchain_core.messages import HumanMessage, SystemMessage

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


def _parse_ts(value: object) -> datetime | None:
    """SQLite devuelve TEXT en formato ISO; lo convertimos a datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Tolera "...Z" o sin sufijo de zona horaria.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


@router.get("/api/threads", response_model=ThreadListOut)
async def list_threads(request: Request, after: str | None = None) -> ThreadListOut:
    db = request.app.state.db
    cursor: str | None = None
    if after:
        try:
            # Validamos parseando (lanza si es inválido) pero pasamos el
            # string crudo a la query — SQLite compara TEXT ISO 8601 ordenado.
            datetime.fromisoformat(after)
            cursor = after
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Cursor inválido") from e

    async with db.acquire() as conn:
        if cursor is None:
            cur = await conn.execute(
                """
                SELECT id, title, archived, created_at
                FROM conversations
                WHERE EXISTS (
                    SELECT 1
                    FROM messages
                    WHERE conversation_id = conversations.id
                )
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (PAGE_SIZE + 1,),
            )
            rows = await cur.fetchall()
        else:
            cur = await conn.execute(
                """
                SELECT id, title, archived, created_at
                FROM conversations
                WHERE created_at < ?
                  AND EXISTS (
                      SELECT 1
                      FROM messages
                      WHERE conversation_id = conversations.id
                  )
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (cursor, PAGE_SIZE + 1),
            )
            rows = await cur.fetchall()

    next_cursor: str | None = None
    if len(rows) > PAGE_SIZE:
        next_cursor = rows[PAGE_SIZE - 1]["created_at"]
        rows = rows[:PAGE_SIZE]

    threads = [
        ThreadOut(id=UUID(r["id"]), title=r["title"], archived=bool(r["archived"]))
        for r in rows
    ]
    return ThreadListOut(threads=threads, next_cursor=next_cursor)


@router.post("/api/threads", response_model=ThreadOut)
async def create_thread(payload: ThreadCreate, request: Request) -> ThreadOut:
    new_id = uuid4()
    # assistant-ui puede pedir un hilo "draft" que nunca recibe mensajes
    # (por ejemplo, al montar o recargar una ruta existente). No lo
    # persistimos aquí para evitar basura; la conversación se materializa
    # en el primer append de mensaje.
    return ThreadOut(id=new_id, title="Nueva conversación", archived=False)


@router.get("/api/threads/{thread_id}", response_model=ThreadOut)
async def get_thread(thread_id: UUID, request: Request) -> ThreadOut:
    db = request.app.state.db
    async with db.acquire() as conn:
        cur = await conn.execute(
            "SELECT id, title, archived FROM conversations WHERE id = ?",
            (str(thread_id),),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Hilo no encontrado")
    return ThreadOut(id=UUID(row["id"]), title=row["title"], archived=bool(row["archived"]))


@router.patch("/api/threads/{thread_id}", status_code=204)
async def patch_thread(thread_id: UUID, payload: ThreadPatch, request: Request) -> Response:
    db = request.app.state.db
    sets: list[str] = []
    args: list = []
    if payload.title is not None:
        sets.append("title = ?")
        args.append(payload.title)
    if payload.archived is not None:
        sets.append("archived = ?")
        args.append(1 if payload.archived else 0)
    if not sets:
        raise HTTPException(status_code=400, detail="Sin cambios")
    sets.append("updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")
    args.append(str(thread_id))

    async with db.acquire() as conn:
        cur = await conn.execute(
            f"UPDATE conversations SET {', '.join(sets)} WHERE id = ?",
            args,
        )
        await conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Hilo no encontrado")
    return Response(status_code=204)


@router.delete("/api/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: UUID, request: Request) -> Response:
    db = request.app.state.db
    async with db.acquire() as conn:
        await conn.execute("DELETE FROM conversations WHERE id = ?", (str(thread_id),))
        await conn.commit()
    return Response(status_code=204)


@router.post("/api/threads/{thread_id}/title", response_model=TitleResponse)
async def generate_title(thread_id: UUID, payload: TitleRequest, request: Request) -> TitleResponse:
    db = request.app.state.db
    chat_llm = request.app.state.chat_llm

    # Pre-check barato (un roundtrip) antes de gastar 2-5s en el LLM.
    async with db.acquire() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM conversations WHERE id = ?", (str(thread_id),)
        )
        exists = await cur.fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Hilo no encontrado")

    msgs = [m for m in payload.messages if m.content.strip()]
    if not msgs:
        return TitleResponse(title="Nueva conversación")

    response = await chat_llm.ainvoke(
        [
            SystemMessage(content=TITLE_SYSTEM),
            HumanMessage(content=_title_user_prompt(msgs)),
        ]
    )
    raw = response.content if isinstance(response.content, str) else ""
    # Modelos a veces devuelven el título envuelto en comillas o con prefijos.
    title = raw.strip().strip('"').strip("'").splitlines()[0][:80] or "Nueva conversación"

    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE conversations
            SET title = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?
            """,
            (title, str(thread_id)),
        )
        await conn.commit()

    return TitleResponse(title=title)


@router.get("/api/threads/{thread_id}/messages", response_model=list[MessageOut])
async def list_messages(thread_id: UUID, request: Request) -> list[MessageOut]:
    db = request.app.state.db
    async with db.acquire() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM conversations WHERE id = ?", (str(thread_id),)
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Hilo no encontrado")
        cur = await conn.execute(
            """
            SELECT id, parent_id, role, content, sources, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            """,
            (str(thread_id),),
        )
        rows = await cur.fetchall()

    out: list[MessageOut] = []
    for r in rows:
        out.append(
            MessageOut(
                id=UUID(r["id"]),
                parent_id=UUID(r["parent_id"]) if r["parent_id"] else None,
                role=r["role"],
                content=r["content"],
                sources=_parse_sources(r["sources"]),
                created_at=_parse_ts(r["created_at"]),
            )
        )
    return out


@router.post("/api/threads/{thread_id}/messages")
async def append_message(thread_id: UUID, payload: MessageAppend, request: Request) -> dict:
    db = request.app.state.db
    msg = payload.message
    msg_id = msg.id or uuid4()
    sources_json = (
        json.dumps([s.model_dump() for s in msg.sources], ensure_ascii=False)
        if msg.sources is not None
        else None
    )

    # SQLite no soporta CTEs con DML chained al estilo de Postgres. Lo
    # resolvemos en dos statements dentro de una transacción: primero
    # materializamos el hilo si no existía, después insertamos el mensaje
    # y bumpeamos updated_at si la inserción no fue idempotent-skip.
    async with db.acquire() as conn:
        try:
            await conn.execute("BEGIN")
            await conn.execute(
                """
                INSERT INTO conversations (id)
                VALUES (?)
                ON CONFLICT (id) DO NOTHING
                """,
                (str(thread_id),),
            )
            cur = await conn.execute(
                """
                INSERT INTO messages
                    (id, conversation_id, parent_id, role, content, sources)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    str(msg_id),
                    str(thread_id),
                    str(payload.parentId) if payload.parentId else None,
                    msg.role,
                    msg.content,
                    sources_json,
                ),
            )
            if cur.rowcount > 0:
                await conn.execute(
                    """
                    UPDATE conversations
                    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    WHERE id = ?
                    """,
                    (str(thread_id),),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    return {"id": str(msg_id)}
