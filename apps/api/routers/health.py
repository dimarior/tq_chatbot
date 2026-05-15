from fastapi import APIRouter, Request

from apps.api.schemas import HealthStatus


router = APIRouter()


@router.get("/api/health", response_model=HealthStatus)
async def health(request: Request) -> HealthStatus:
    settings = request.app.state.settings
    pool = request.app.state.pool
    vector_store = request.app.state.vector_store
    ollama = request.app.state.ollama

    # DB de persistencia (conversations/messages). Ping mínimo.
    db_ok = False
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        pass

    # Conteo de chunks vivos en el vector store (Chroma).
    chunk_count = 0
    try:
        chunk_count = int(vector_store._collection.count())
    except Exception:
        # Cliente Chroma podría no exponer _collection en futuras versiones; si
        # eso pasa, el health quedará en 0 pero no tumba el endpoint.
        pass

    ollama_ok = await ollama.health()

    return HealthStatus(
        ok=db_ok and ollama_ok,
        db_ok=db_ok,
        ollama_ok=ollama_ok,
        llm_model=settings.llm_model,
        embed_model=settings.embed_model,
        chunk_count=chunk_count,
    )
