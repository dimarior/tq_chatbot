from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.core.config import get_settings
from apps.api.core.db import create_pool
from apps.api.llm.ollama_client import OllamaClient
from apps.api.rag.corpus_stats import compute_corpus_stats
from apps.api.routers import chat_v2, health, threads
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.pool = await create_pool(settings)
    app.state.ollama_embedder = OllamaEmbeddings(base_url=settings.ollama_host, model=settings.embed_model)
    app.state.vector_store = Chroma(persist_directory=settings.chroma_path, embedding_function=app.state.ollama_embedder)
    app.state.ollama = OllamaClient(settings.ollama_host, settings.llm_model)
    # Conteo agregado del corpus, calculado una vez al arranque. Preguntas como
    # "¿cuántos artículos científicos hay?" son agregadas, no semánticas: el RAG
    # no las puede responder desde los top-k chunks. Se refresca al reiniciar la
    # API tras re-ingestar.
    app.state.corpus_stats = await compute_corpus_stats(app.state.pool)
    try:
        yield
    finally:
        await app.state.ollama.aclose()
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
    app.include_router(chat_v2.router)
    app.include_router(threads.router)

    return app


app = create_app()
