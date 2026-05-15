# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

RAG chatbot ("TQ-Asistente") about Tecnoquímicas S.A. and tqfarma. Full local stack: FastAPI + Chroma (langchain-community) + Postgres (sólo persistencia de hilos) + Ollama (Qwen3-8B + Qwen3-Embedding-0.6B). The frontend is a Next.js 15 + React 19 app built on [assistant-ui](https://www.assistant-ui.com/), served separately from the API on port 3000. User-facing copy stays in **Spanish**; identifiers in English.

This is a clean rewrite (2026-05). The previous Streamlit/Gemini pipeline was deleted. An earlier version of this branch used Postgres/pgvector for retrieval; tras el commit `038ff91` migramos a Chroma local persistente — el schema pgvector está deprecado pero las migrations aún lo crean (ver "Architectural rules").

## Layout

```
apps/api/        FastAPI service (core/, routers/, rag/, llm/)
                   routers: chat_v2 (SSE), health, threads (persistencia de hilos)
                   rag/retriever.py → wrap thin sobre Chroma.similarity_search_with_score
                   rag/corpus_stats.py → cuenta noticias en la metadata de Chroma
frontend/        Next.js + assistant-ui (app/, components/, lib/)
                   lib/tqChatAdapter.ts  → custom ChatModelAdapter parsing SSE
                   lib/threadListAdapter.tsx → RemoteThreadListAdapter + helpers de thread id
                   lib/sourcesStore.ts   → Zustand map messageId → Source[]
                   lib/settingsStore.ts  → Zustand: temperature + top_k del panel de parámetros
                   components/SettingsPanel.tsx → sliders en el sidebar derecho
scripts/         Manual data pipeline: fetch_sitemaps.py, ingest_to_rag.py (a Chroma), reset_rag.py
migrations/      001_init.sql (legacy pgvector, deprecated), 002_conversations.sql (chat history)
chroma_db/       Persist directory de Chroma (gitignored; generado por ingest)
data/raw/        Per-URL JSON snapshots from scrape (gitignored)
```

The API path `apps.api.main:app` is the entry point. Scripts import from `apps.api.*`; run them from the repo root.

## Commands

```bash
docker compose up -d                  # postgres + api (port 8000)

brew install 0xMassi/webclaw/webclaw   # one-time, only on dev machines that fetch
uv sync
uv run python scripts/fetch_sitemaps.py --site all   # idempotent: skips if hash unchanged. Requires `webclaw` on PATH.
uv run python scripts/ingest_to_rag.py               # idempotent: per-doc transactional upsert

cd frontend && pnpm install && pnpm dev   # Next.js on port 3000
```

Health: `curl http://localhost:8000/api/health`. UI: `http://localhost:3000`.

## Architectural rules

- **Data pipeline is idempotent.** `fetch_sitemaps.py` invokes the [`webclaw`](https://github.com/0xMassi/webclaw) CLI once per URL inside a `ThreadPoolExecutor` and writes `data/raw/<slug>.json` immediately on completion — only when the SHA-256 of the extracted markdown changes. `ingest_to_rag.py` skips reinsert cuando `metadata.content_hash` ya coincide en Chroma; los IDs son `uuid5(NAMESPACE_URL, "<url>#<idx>")` así que la reinserción reescribe en lugar de duplicar. Re-running both is a no-op. Preserve this property when editing.
- **Single vector store: Chroma local persistente.** El cliente vive en `app.state.vector_store` (creado en `main.py` con `embedding_function=OllamaEmbeddings(...)`). La recuperación usa `similarity_search_with_score` que devuelve distancia L2; el retriever la transforma a `1/(1+L2)` para que `min_score` siga teniendo semántica "mayor = más relevante". Recalibrar `settings.min_score` tras cambiar el modelo de embedding o el corpus.
- **Postgres ya no participa en RAG.** Las tablas `documents` y `chunks` siguen creándose por `migrations/001_init.sql` (legacy) pero NO se consultan. Postgres sólo guarda `conversations` y `messages` (memoria persistente del hilo). Si tocas el ingest o el retriever, asume Chroma — no añadas SQL a esa ruta.
- **Streaming via SSE.** `POST /api/chat` returns `text/event-stream` with three event types: `sources` (JSON array), `token` (raw text), `done` (plus `error` on failure). The Next.js frontend consumes it inside `lib/tqChatAdapter.ts` via fetch + a manual SSE parser (`lib/sse.ts`). El payload incluye `thread_id` (opcional) y `temperature`/`top_k` (por turno, controlados por el `SettingsPanel`).
- **Memoria por hilo.** Si el cliente envía `thread_id`, `chat_v2.py` carga el historial completo desde `messages` antes de invocar al LLM (función `_load_history_from_db`). Sin `thread_id`, modo stateless con `payload.history`. El cliente sigue persistiendo cada turno vía `POST /api/threads/{id}/messages` para que la UI lo pueda re-hidratar.
- **Sources en el frontend van por un canal aparte.** El stream SSE empuja un evento `sources` con `Source[]`; `tqChatAdapter` las guarda en `useSourcesStore` keyed por `assistantId`. El `threadHistoryAdapter` re-hidrata el store al abrir un hilo. No mezclar las citas con el content stream del modelo.
- **Spanish prompts.** `apps/api/rag/prompt.py` — keep system prompt in Spanish, keep the TOTAL/PARCIAL/NULA/SENSIBLE protocol, never expose the protocol to the user. Sensitive topics (recalls, litigation, salud) must redirect to official channels.
- **No tests in v1.** Manual smoke per README quickstart.

## Conventions

- Python 3.12, `uv` for deps. Web scraping runs out-of-process via la CLI `webclaw` — no hay deps de scraping en Python.
- Commit format: `tipo(scope): mensaje en español` — `feat`, `fix`, `chore`, `docs`, `refactor`.
- Embeddings vienen de `langchain-community.embeddings.OllamaEmbeddings`; chunking de `langchain-text-splitters`; vector store de `langchain-community.vectorstores.Chroma`. NO añadir más de LangChain sin justificación clara.
- El `integrated-chat/` folder es un experimento aparte — déjalo en paz.
