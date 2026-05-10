from fastapi import APIRouter, Request

from apps.api.schemas import HealthStatus


router = APIRouter()


@router.get("/api/health", response_model=HealthStatus)
async def health(request: Request) -> HealthStatus:
    settings = request.app.state.settings
    pool = request.app.state.pool
    ollama = request.app.state.ollama

    db_ok = False
    chunk_count = 0
    try:
        async with pool.acquire() as conn:
            chunk_count = int(await conn.fetchval("SELECT count(*) FROM chunks"))
        db_ok = True
    except Exception:
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
