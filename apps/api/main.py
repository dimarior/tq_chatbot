from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma

from apps.api.core.config import Settings, get_settings
from apps.api.core.db import init_db
from apps.api.llm.ollama_client import OllamaClient
from apps.api.rag.corpus_stats import compute_corpus_stats
from apps.api.routers import chat_v2, health, threads


def _configure_langsmith(settings: Settings) -> None:
    """Re-exporta el bloque LangSmith a os.environ antes de importar langgraph.

    langgraph/langchain leen LANGSMITH_* (y los legados LANGCHAIN_*) en tiempo
    de inicialización del cliente de tracing. Si los settings no están en el
    entorno cuando se compila el primer grafo, los traces no salen. El gate
    es estricto: hace falta TANTO el flag como la API key para activarse.
    """
    if not (settings.langsmith_tracing and settings.langsmith_api_key):
        os.environ.pop("LANGSMITH_TRACING", None)
        os.environ.pop("LANGCHAIN_TRACING_V2", None)
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_langsmith(settings)

    # Imports diferidos: hay que setear LANGSMITH_* en os.environ ANTES de
    # que langgraph se importe (resuelve su cliente de tracing en import time).
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from apps.api.graph import build_graph
    from apps.api.graph.llm import make_chat_llm

    app.state.settings = settings
    # Persistencia de hilos (conversations + messages). Mismo archivo SQLite
    # que la checkpointer del grafo, distintas tablas — no se pisan.
    app.state.db = await init_db(settings)

    embedder = OllamaEmbeddings(
        base_url=settings.ollama_host,
        model=settings.embed_model,
    )
    app.state.vector_store = Chroma(
        persist_directory=settings.chroma_path,
        embedding_function=embedder,
    )
    app.state.ollama = OllamaClient(settings.ollama_host, settings.llm_model)
    app.state.corpus_stats = compute_corpus_stats(app.state.vector_store)

    # ── Checkpointer de LangGraph ────────────────────────────────────────────
    # AsyncSqliteSaver gestiona su propia conexión aiosqlite al mismo archivo.
    # setup() crea las tablas checkpoints/checkpoint_blobs/checkpoint_writes/
    # checkpoint_migrations la primera vez (idempotente).
    checkpoint_conn = await aiosqlite.connect(settings.sqlite_path)
    checkpointer = AsyncSqliteSaver(checkpoint_conn)
    await checkpointer.setup()

    app.state.checkpoint_conn = checkpoint_conn
    app.state.checkpointer = checkpointer
    app.state.graph = build_graph(
        settings=settings,
        vector_store=app.state.vector_store,
        corpus_stats=app.state.corpus_stats,
        checkpointer=checkpointer,
    )

    # ChatOllama reutilizable para tareas one-shot fuera del grafo (p.ej.
    # generación de títulos en /api/threads/{id}/title).
    app.state.chat_llm = make_chat_llm(settings)

    try:
        yield
    finally:
        await app.state.ollama.aclose()
        await checkpoint_conn.close()


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
