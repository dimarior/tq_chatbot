# TQ-Chatbot

Chatbot RAG sobre Tecnoquímicas S.A. — backend en FastAPI, modelo local Qwen3-8B vía Ollama, vector store en Postgres + pgvector, y un widget de burbuja flotante en cualquier landing.

> **Estado:** Reescritura completa desde cero (mayo 2026). El proyecto anterior (Streamlit + inyección de KB en prompt) fue reemplazado.

## Objetivos

1. **RAG real**: vector search con HNSW + cosine sobre chunks embebidos, citando fuentes en cada respuesta.
2. **100 % local**: LLM, embeddings y BD corren en la máquina del desarrollador (M1 Pro 16 GB target).
3. **Reproducible**: `docker compose up` levanta todo. Sin "funciona en mi máquina".
4. **Pipeline manual e idempotente**: dos scripts (`fetch_sitemaps.py`, `ingest_to_rag.py`) se ejecutan a mano, pueden re-correrse sin efectos secundarios.
5. **Frontend ligero**: una página dummy con un bubble en bottom-right que abre el chat — sin React, sin build step.

## Stack

| Capa | Tecnología |
|---|---|
| Runtime | Python 3.12, `uv` |
| API | FastAPI + Pydantic v2 + asyncpg |
| LLM | Qwen3-8B-Instruct vía Ollama |
| Embeddings | Qwen3-Embedding-0.6B (1024 dim) |
| Vector DB | PostgreSQL 16 + pgvector (HNSW, cosine) |
| Scraping | httpx + selectolax + Playwright (fallback) + tenacity |
| Chunking | LangChain `RecursiveCharacterTextSplitter` |
| Frontend | HTML estático + Tailwind (Play CDN) + Alpine.js + HTMX (SSE) |
| Streaming | SSE (Server-Sent Events) |
| Infra | docker-compose |

Detalles y razones en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Prerrequisitos

- Docker Desktop con ≥ 8 GB asignados (recomendado 12 GB)
- ~10 GB de disco libre para modelos
- Python 3.12 + `uv` (sólo para correr los scripts de fetch/ingest desde host)

## Quickstart

```bash
# 1. Configurar entorno
cp .env.example .env

# 2. Levantar stack (postgres + ollama + api). Primer arranque descarga modelos (~6 GB).
docker compose up -d
docker compose logs -f ollama-init   # esperar a que termine de pullear modelos

# 3. Scrapear sitios (idempotente — re-ejecutable)
uv sync --extra scrape
uv run playwright install chromium
uv run python scripts/fetch_sitemaps.py --site all

# 4. Indexar al RAG (idempotente)
uv run python scripts/ingest_to_rag.py

# 5. Abrir el chat
open http://localhost:8000
```

## Comandos útiles

```bash
# Re-fetch forzado (ignora content_hash existente)
uv run python scripts/fetch_sitemaps.py --site all --force

# Sólo un sitio
uv run python scripts/fetch_sitemaps.py --site tqfarma

# Ingesta dry-run (cuenta cambios sin escribir)
uv run python scripts/ingest_to_rag.py --dry-run

# Reset total del RAG
uv run python scripts/reset_rag.py

# Health check
curl http://localhost:8000/api/health
```

## Estructura

```
.
├── apps/api/              # FastAPI app
│   ├── core/              # config + db pool
│   ├── routers/           # /api/chat (SSE), /api/health
│   ├── rag/               # embeddings, retriever, prompt
│   └── llm/               # Ollama client
├── frontend/              # landing + bubble widget (servido por FastAPI)
├── scripts/               # fetch_sitemaps.py, ingest_to_rag.py, reset_rag.py
├── migrations/            # 001_init.sql (auto-aplicado por postgres init)
├── data/                  # raw + processed (gitignored)
├── docs/ARCHITECTURE.md   # decisiones (ADRs)
├── docker-compose.yml
└── pyproject.toml
```

## Variables de entorno

Ver `.env.example`. Las más importantes:

| Variable | Default | Notas |
|---|---|---|
| `LLM_MODEL` | `qwen3:8b` | Cambiar a `qwen3:4b` si tienes < 12 GB de RAM. |
| `EMBED_MODEL` | `qwen3-embedding:0.6b` | Si Ollama no tiene el tag, usar `EMBED_BACKEND=sentence-transformers`. |
| `EMBED_DIMS` | `1024` | Debe coincidir con el modelo. Cambiar requiere reset del RAG. |
| `TOP_K` | `6` | Chunks recuperados por consulta. |
| `OLLAMA_HOST` | `http://ollama:11434` | Dentro de Docker. Para correr scripts desde host: `http://localhost:11434`. |
| `DATABASE_URL` | `postgresql://tq:tq@postgres:5432/tq` | Idem — usar `localhost` desde host. |

## Contribuir

Convención de commits: `tipo(scope): mensaje en español` (`feat`, `fix`, `chore`, `docs`, `refactor`).

Idioma: todo el contenido user-facing (prompts, UI, mensajes de error) está en **español**. Los identificadores de código siguen en inglés.
