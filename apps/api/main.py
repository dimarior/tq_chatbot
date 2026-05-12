from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.core.config import get_settings
from apps.api.core.db import create_pool
from apps.api.llm.ollama_client import OllamaClient
from apps.api.rag.embeddings import build_embedder
from apps.api.routers import chat, health, threads


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.pool = await create_pool(settings)
    app.state.embedder = build_embedder(settings)
    app.state.ollama = OllamaClient(settings.ollama_host, settings.llm_model)
    try:
        yield
    finally:
        await app.state.ollama.aclose()
        await app.state.embedder.aclose()
        await app.state.pool.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TQ-Chatbot API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(threads.router)

    return app


app = create_app()
