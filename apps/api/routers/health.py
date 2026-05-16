import httpx
from fastapi import APIRouter, Request

from apps.api.schemas import HealthStatus


router = APIRouter()


async def _ollama_ok(base_url: str) -> bool:
    """Ping ligero al host de Ollama. /api/tags es barato (lista modelos)."""
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            r = await client.get("/api/tags")
            r.raise_for_status()
            return True
    except Exception:
        return False


@router.get("/api/health", response_model=HealthStatus)
async def health(request: Request) -> HealthStatus:
    settings = request.app.state.settings
    db = request.app.state.db
    vector_store = request.app.state.vector_store

    db_ok = False
    try:
        async with db.acquire() as conn:
            await conn.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass

    chunk_count = 0
    try:
        chunk_count = int(vector_store._collection.count())
    except Exception:
        pass

    ollama_ok = await _ollama_ok(settings.ollama_host)

    return HealthStatus(
        ok=db_ok and ollama_ok,
        db_ok=db_ok,
        ollama_ok=ollama_ok,
        llm_model=settings.llm_model,
        embed_model=settings.embed_model,
        chunk_count=chunk_count,
    )
