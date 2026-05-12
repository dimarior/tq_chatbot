# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

RAG chatbot ("TQ-Asistente") about Tecnoquímicas S.A. and tqfarma. Full local stack: FastAPI + Postgres/pgvector + Ollama (Qwen3-8B + Qwen3-Embedding-0.6B). The frontend is a Next.js 15 + React 19 app built on [assistant-ui](https://www.assistant-ui.com/), served separately from the API on port 3000. User-facing copy stays in **Spanish**; identifiers in English.

This is a clean rewrite (2026-05). The previous Streamlit/Gemini pipeline was deleted. See `docs/ARCHITECTURE.md` for the ADRs that define the current design.

## Layout

```
apps/api/        FastAPI service (core/, routers/, rag/, llm/)
                   routers: chat (SSE), health, threads (persistencia de hilos)
frontend/        Next.js + assistant-ui (app/, components/, lib/)
                   lib/tqChatAdapter.ts  → custom ChatModelAdapter parsing SSE
                   lib/threadListAdapter.tsx → RemoteThreadListAdapter + ThreadHistoryAdapter
                   lib/sourcesStore.ts   → Zustand map messageId → Source[]
scripts/         Manual data pipeline: fetch_sitemaps.py, ingest_to_rag.py, reset_rag.py
migrations/      001_init.sql (RAG), 002_conversations.sql (chat history)
data/raw/        Per-URL JSON snapshots from scrape (gitignored)
docs/            ARCHITECTURE.md
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

- **Data pipeline is idempotent.** `fetch_sitemaps.py` invokes the [`webclaw`](https://github.com/0xMassi/webclaw) CLI once per URL inside a `ThreadPoolExecutor` and writes `data/raw/<slug>.json` immediately on completion — only when the SHA-256 of the extracted markdown changes. `ingest_to_rag.py` skips upserts when `documents.content_hash` matches. Re-running both is a no-op. Preserve this property when editing.
- **Embedding dim = 1024.** `chunks.embedding` is `vector(1024)`; matches Qwen3-Embedding-0.6B. Changing the embedding model requires a schema migration and a full reindex.
- **Two embedding backends.** `apps/api/rag/embeddings.py` exposes `OllamaEmbedder` and `SentenceTransformersEmbedder` behind a `Protocol`. Both ingest and retrieval use the same `build_embedder(settings)` factory — when adding logic, work against the protocol.
- **Streaming via SSE.** `POST /api/chat` returns `text/event-stream` with three event types: `sources` (JSON array), `token` (raw text), `done` (plus `error` on failure). The Next.js frontend consumes it inside `lib/tqChatAdapter.ts` via fetch + a manual SSE parser (`lib/sse.ts`). `/api/chat` itself stays single-shot and stateless — persistence is owned by `/api/threads/*`.
- **Chat history persistence.** `conversations` + `messages` tables (migration `002_conversations.sql`). No auth: the thread list is shared globally. The `messages.sources` JSONB column holds the citation chips so they survive reloads — the frontend re-populates `sourcesStore` when hydrating a thread.
- **Spanish prompts.** `apps/api/rag/prompt.py` — keep system prompt in Spanish, keep the TOTAL/PARCIAL/NULA/SENSIBLE protocol, never expose the protocol to the user. Sensitive topics (recalls, litigation, salud) must redirect to official channels.
- **No tests in v1.** Manual smoke per README quickstart.

## Conventions

- Python 3.12, `uv` for deps. `[local-embed]` is the only optional extra (sentence-transformers, heavy). Web scraping runs out-of-process via the webclaw container — no Python scraping deps.
- Commit format: `tipo(scope): mensaje en español` — `feat`, `fix`, `chore`, `docs`, `refactor`.
- Don't reintroduce LangChain beyond `langchain-text-splitters` (only used for chunking).
- The `integrated-chat/` folder is an unrelated experiment — leave it alone.
