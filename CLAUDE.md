# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

RAG chatbot ("TQ-Asistente") about Tecnoquímicas S.A. and tqfarma. Full local stack — **sin Docker**: FastAPI + Chroma (langchain-community) + SQLite (sólo persistencia de hilos + checkpoints del grafo) + Ollama (Qwen3-8B + Qwen3-Embedding-0.6B). Orquestación con LangGraph; monitoreo opcional vía LangSmith. The frontend is a Next.js 15 + React 19 app built on [assistant-ui](https://www.assistant-ui.com/), served separately from the API on port 3000. User-facing copy stays in **Spanish**; identifiers in English.

This is a clean rewrite (2026-05). Evolución histórica relevante:
- Versión inicial: Postgres/pgvector para RAG + Streamlit. Reemplazada.
- 038ff91: migración pgvector → Chroma para el RAG.
- Commits posteriores: LangGraph + LangSmith para orquestación + monitoreo.
- Commits SQLite: Postgres → SQLite (un solo archivo); se elimina docker-compose.

## Layout

```
apps/api/        FastAPI service (core/, routers/, rag/, llm/, graph/)
                   routers: chat_v2 (SSE — traduce graph.astream a SSE), health, threads
                   graph/   → StateGraph: classify → (direct|structured|retrieve) → generate
                   rag/retriever.py → wrap thin sobre Chroma.similarity_search_with_score
                   rag/corpus_stats.py → cuenta noticias en la metadata de Chroma
                   core/db.py → Database (aiosqlite) con schema in-line + WAL
frontend/        Next.js + assistant-ui (app/, components/, lib/)
                   lib/tqChatAdapter.ts  → custom ChatModelAdapter parsing SSE
                   lib/threadListAdapter.tsx → RemoteThreadListAdapter + helpers de thread id
                   lib/sourcesStore.ts   → Zustand map messageId → Source[]
                   lib/settingsStore.ts  → Zustand: temperature + top_k del panel de parámetros
                   components/SettingsPanel.tsx → sliders en el sidebar derecho
scripts/         Manual data pipeline: fetch_sitemaps.py, ingest_to_rag.py (a Chroma), reset_rag.py
chroma_db/       Persist directory de Chroma (gitignored; generado por ingest)
tq.db            SQLite local con conversations + messages + checkpoints* (gitignored)
data/raw/        Per-URL JSON snapshots from scrape (gitignored)
```

The API path `apps.api.main:app` is the entry point. Scripts import from `apps.api.*`; run them from the repo root.

## Commands

```bash
# Backend (crea tq.db al primer arranque, idempotente):
make backend     # uv run uvicorn apps.api.main:app --reload --port 8000

# Frontend:
make frontend    # cd frontend && pnpm dev

# Ingesta:
make ingest      # uv run python scripts/ingest_to_rag.py

# Reset (borra tq.db + chroma_db; data/raw se conserva):
make reset

# Ollama corre nativo en el host (no en Docker):
ollama pull qwen3:8b
ollama pull qwen3-embedding:0.6b
```

Health: `curl http://localhost:8000/api/health`. UI: `http://localhost:3000`.

## Architectural rules

- **Data pipeline is idempotent.** `fetch_sitemaps.py` invokes the [`webclaw`](https://github.com/0xMassi/webclaw) CLI once per URL inside a `ThreadPoolExecutor` and writes `data/raw/<slug>.json` immediately on completion — only when the SHA-256 of the extracted markdown changes. `ingest_to_rag.py` skips reinsert cuando `metadata.content_hash` ya coincide en Chroma; los IDs son `uuid5(NAMESPACE_URL, "<url>#<idx>")` así que la reinserción reescribe en lugar de duplicar. Re-running both is a no-op. Preserve this property when editing.
- **Single vector store: Chroma local persistente.** El cliente vive en `app.state.vector_store` (creado en `main.py` con `embedding_function=OllamaEmbeddings(...)`). La recuperación usa `similarity_search_with_score` que devuelve distancia L2; el retriever la transforma a `1/(1+L2)` para que `min_score` siga teniendo semántica "mayor = más relevante". Recalibrar `settings.min_score` tras cambiar el modelo de embedding o el corpus.
- **Persistencia en SQLite local, no Postgres.** Todo lo persistente vive en `tq.db`:
  - Tablas `conversations` / `messages` (creadas por `apps/api/core/db.py` al arranque) — vista del frontend.
  - Tablas `checkpoints*` (creadas por `AsyncSqliteSaver.setup()`) — memoria del grafo.
  - WAL habilitado: lectores no bloquean a escritores cuando la checkpointer corre en paralelo.
  - Borrar `tq.db*` (incluye `-shm` y `-wal`) resetea toda la memoria del backend; Chroma queda intacto.
- **Streaming via SSE.** `POST /api/chat` returns `text/event-stream` with three event types: `sources` (JSON array), `token` (raw text), `done` (plus `error` on failure). The Next.js frontend consumes it inside `lib/tqChatAdapter.ts` via fetch + a manual SSE parser (`lib/sse.ts`). El payload incluye `thread_id` (opcional) y `temperature`/`top_k` (por turno, controlados por el `SettingsPanel`).
- **Memoria por hilo via checkpointer.** `AsyncSqliteSaver` mantiene el state del grafo en las tablas `checkpoints*` (creadas por `checkpointer.setup()` al arranque, idempotente). El endpoint sólo necesita pasar `configurable={"thread_id": ...}`; el reductor `add_messages` se encarga de acumular. El cliente sigue persistiendo cada turno vía `POST /api/threads/{id}/messages` para que la UI lo re-hidrate al recargar — son dos capas con responsabilidades distintas: checkpoints = estado del grafo, messages = vista de la UI.
- **Monitoreo via LangSmith.** Set `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` y cada nodo del grafo + cada llamada LangChain interna se traza automáticamente, sin instrumentación manual. El lifespan re-exporta los settings a `os.environ` antes de importar `langgraph`.
- **Sources en el frontend van por un canal aparte.** El stream SSE empuja un evento `sources` con `Source[]`; `tqChatAdapter` las guarda en `useSourcesStore` keyed por `assistantId`. El `threadHistoryAdapter` re-hidrata el store al abrir un hilo. No mezclar las citas con el content stream del modelo.
- **Spanish prompts.** `apps/api/rag/prompt.py` — keep system prompt in Spanish, keep the TOTAL/PARCIAL/NULA/SENSIBLE protocol, never expose the protocol to the user. Sensitive topics (recalls, litigation, salud) must redirect to official channels.
- **No tests in v1.** Manual smoke per README quickstart.

## Conventions

- Python 3.12, `uv` for deps. Web scraping runs out-of-process via la CLI `webclaw` — no hay deps de scraping en Python.
- Commit format: `tipo(scope): mensaje en español` — `feat`, `fix`, `chore`, `docs`, `refactor`.
- Embeddings vienen de `langchain-community.embeddings.OllamaEmbeddings`; chunking de `langchain-text-splitters`; vector store de `langchain-community.vectorstores.Chroma`. NO añadir más de LangChain sin justificación clara.
- El `integrated-chat/` folder es un experimento aparte — déjalo en paz.
