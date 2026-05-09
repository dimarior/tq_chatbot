from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)


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
