"""Capa de acceso a SQLite para la persistencia de hilos.

Una sola base de datos en disco (`settings.sqlite_path`) que comparte:
  - conversations + messages (este módulo, vía `Database.acquire`)
  - checkpoints* (AsyncSqliteSaver, configurado en main.py)

Justificación de SQLite: tras la migración del RAG a Chroma, Postgres sólo
guardaba historial de hilos + memoria del grafo — dos cosas que SQLite
maneja perfectamente para un proyecto de un usuario a la vez. Esto nos
permite dropear docker-compose y correr todo con `uv run uvicorn`.

Patrón de conexión: abrimos una conexión nueva por request vía contextmanager
(SQLite abre archivos en <1ms). WAL mode habilitado al setup para que
readers no bloqueen a writers — relevante porque la checkpointer también
abre conexiones al mismo archivo.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from apps.api.core.config import Settings


_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'Nueva conversación',
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS conversations_updated_idx
    ON conversations (archived, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    parent_id       TEXT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    sources         TEXT NULL,  -- JSON serializado
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS messages_conv_created_idx
    ON messages (conversation_id, created_at);
"""


class Database:
    """Wrapper mínimo sobre aiosqlite con setup idempotente."""

    def __init__(self, path: str) -> None:
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    async def setup(self) -> None:
        """Crea schema + activa WAL. Idempotente."""
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._path) as conn:
            # WAL: readers no bloquean a writers. Importante cuando la
            # checkpointer del grafo escribe en paralelo a threads.py.
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.executescript(_SCHEMA)
            await conn.commit()

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[aiosqlite.Connection]:
        """Conexión por request. Filas accesibles por nombre (Row factory)."""
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys=ON")
            yield conn


async def init_db(settings: Settings) -> Database:
    db = Database(settings.sqlite_path)
    await db.setup()
    return db
