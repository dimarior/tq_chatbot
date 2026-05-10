# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project

RAG chatbot ("TQ-Asistente") about Tecnoquímicas S.A. and tqfarma. Full local stack: FastAPI + Postgres/pgvector + Ollama (Qwen3-8B + Qwen3-Embedding-0.6B). Lightweight static frontend with a chat-bubble widget (Alpine.js + Tailwind via CDN). User-facing copy stays in **Spanish**; identifiers in English.

This is a clean rewrite (2026-05). The previous Streamlit/Gemini pipeline was deleted. See `docs/ARCHITECTURE.md` for the 10 ADRs that define the current design.

## Layout

```
apps/api/        FastAPI service (core/, routers/, rag/, llm/)
frontend/        Static landing + bubble widget
scripts/         Manual data pipeline: fetch_sitemaps.py, ingest_to_rag.py, reset_rag.py
migrations/      001_init.sql (auto-applied by postgres init container)
data/raw/        Per-URL JSON snapshots from scrape (gitignored)
docs/            ARCHITECTURE.md
```

The API path `apps.api.main:app` is the entry point. Scripts import from `apps.api.*`; run them from the repo root.

## Commands

```bash
docker compose up -d
docker compose logs -f ollama-init   # wait for model pulls on first boot

brew install 0xMassi/webclaw/webclaw   # one-time, only on dev machines that fetch
uv sync
uv run python scripts/fetch_sitemaps.py --site all   # idempotent: skips if hash unchanged. Requires `webclaw` on PATH.
uv run python scripts/ingest_to_rag.py               # idempotent: per-doc transactional upsert
```

Health: `curl http://localhost:8000/api/health`. UI: `http://localhost:8000/`.

## Architectural rules

- **Data pipeline is idempotent.** `fetch_sitemaps.py` invokes the [`webclaw`](https://github.com/0xMassi/webclaw) CLI once per URL inside a `ThreadPoolExecutor` and writes `data/raw/<slug>.json` immediately on completion — only when the SHA-256 of the extracted markdown changes. `ingest_to_rag.py` skips upserts when `documents.content_hash` matches. Re-running both is a no-op. Preserve this property when editing.
- **Embedding dim = 1024.** `chunks.embedding` is `vector(1024)`; matches Qwen3-Embedding-0.6B. Changing the embedding model requires a schema migration and a full reindex.
- **Two embedding backends.** `apps/api/rag/embeddings.py` exposes `OllamaEmbedder` and `SentenceTransformersEmbedder` behind a `Protocol`. Both ingest and retrieval use the same `build_embedder(settings)` factory — when adding logic, work against the protocol.
- **Streaming via SSE.** `POST /api/chat` returns `text/event-stream` with three event types: `sources` (JSON array), `token` (raw text), `done`. The widget consumes via fetch + ReadableStream (not HTMX SSE — POST + stream doesn't fit the GET-subscription model).
- **Spanish prompts.** `apps/api/rag/prompt.py` — keep system prompt in Spanish, keep the TOTAL/PARCIAL/NULA/SENSIBLE protocol, never expose the protocol to the user. Sensitive topics (recalls, litigation, salud) must redirect to official channels.
- **No tests in v1.** Manual smoke per README quickstart.

## Conventions

- Python 3.12, `uv` for deps. `[local-embed]` is the only optional extra (sentence-transformers, heavy). Web scraping runs out-of-process via the webclaw container — no Python scraping deps.
- Commit format: `tipo(scope): mensaje en español` — `feat`, `fix`, `chore`, `docs`, `refactor`.
- Don't reintroduce LangChain beyond `langchain-text-splitters` (only used for chunking).
- The `integrated-chat/` folder is an unrelated experiment — leave it alone.
