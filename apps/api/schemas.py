from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


ChatRole = Literal["user", "assistant", "system"]
MessageRole = Literal["user", "assistant"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)
    conversation_id: UUID | None = None


class Source(BaseModel):
    url: str
    title: str | None = None
    score: float


class RetrievedChunk(BaseModel):
    document_id: int
    chunk_index: int
    content: str
    url: str
    title: str | None = None
    score: float


class HealthStatus(BaseModel):
    ok: bool
    db_ok: bool
    ollama_ok: bool
    llm_model: str
    embed_model: str
    chunk_count: int


# --- Threads / messages persistence -----------------------------------------

class ThreadOut(BaseModel):
    id: UUID
    title: str
    archived: bool


class ThreadListOut(BaseModel):
    threads: list[ThreadOut]
    next_cursor: str | None = None


class ThreadCreate(BaseModel):
    # assistant-ui envía localId; aceptado pero no usado (el servidor asigna su uuid).
    localId: str | None = None


class ThreadPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None


class MessageIn(BaseModel):
    id: UUID | None = None
    role: MessageRole
    content: str
    sources: list[Source] | None = None


class MessageAppend(BaseModel):
    message: MessageIn
    parentId: UUID | None = None


class MessageOut(BaseModel):
    id: UUID
    parent_id: UUID | None = None
    role: MessageRole
    content: str
    sources: list[Source] | None = None
    created_at: datetime


class TitleRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)


class TitleResponse(BaseModel):
    title: str
