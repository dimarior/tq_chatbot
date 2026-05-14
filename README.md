# TQ-Chatbot

Chatbot RAG sobre Tecnoquímicas S.A. — backend en FastAPI, modelo local Qwen3-8B vía Ollama, vector store en Postgres + pgvector, y un widget de burbuja flotante en cualquier landing.

> **Estado:** Reescritura completa desde cero (mayo 2026). El proyecto anterior (Streamlit + inyección de KB en prompt) fue reemplazado.

## Objetivos

1. **RAG real**: vector search con HNSW + cosine sobre chunks embebidos, citando fuentes en cada respuesta.
2. **100 % local**: LLM, embeddings y BD corren en la máquina del desarrollador (M1 Pro 16 GB target).
3. **Reproducible**: `docker compose up` levanta todo. Sin "funciona en mi máquina".
4. **Pipeline manual e idempotente**: dos scripts (`fetch_sitemaps.py`, `ingest_to_rag.py`) se ejecutan a mano, pueden re-correrse sin efectos secundarios.
5. **Agente con router**: el sistema decide en cada turno entre herramienta RAG o herramienta de datos estructurados segun la naturaleza de la pregunta.

## Stack

| Capa | Tecnología |
|---|---|
| Runtime | Python 3.12, `uv` |
| API | FastAPI + Pydantic v2 + asyncpg |
| LLM | Qwen3-8B-Instruct vía Ollama |
| Embeddings | Qwen3-Embedding-0.6B (1024 dim) |
| Vector DB | PostgreSQL 16 + pgvector (HNSW, cosine) |
| Scraping | [webclaw](https://github.com/0xMassi/webclaw) (Rust CLI) - `brew install` |
| Chunking | LangChain `RecursiveCharacterTextSplitter` |
| Frontend | Next.js 15 (App Router) + React 19 + [assistant-ui](https://www.assistant-ui.com/) + Tailwind 3 |
| Streaming | SSE (Server-Sent Events) - parser custom dentro del `ChatModelAdapter` |
| Persistencia de chat | Postgres (`conversations`, `messages`) - hilos compartidos sin auth |
| Herramienta estructurada | `datos_estructurados.json` + `structured_tool.py` |
| Router / Agente | `needs_structured_tool()` en `chat_v2.py` |
| Infra | docker-compose |

Detalles y razones en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Prerrequisitos

- Docker Desktop con >= 8 GB asignados (recomendado 12 GB)
- ~10 GB de disco libre para modelos
- Python 3.12 + `uv` (sólo para correr los scripts de fetch/ingest desde host)
- [`webclaw`](https://github.com/0xMassi/webclaw) en el PATH para el script de scraping:
  ```bash
  brew install 0xMassi/webclaw/webclaw
  ```

## Quickstart

```bash
# 1. Configurar entorno
cp .env.example .env

# 2. Levantar stack (postgres + api). Primer arranque crea las tablas (incluye conversations/messages).
docker compose up -d

# 3. Scrapear sitios (idempotente - re-ejecutable). Requiere `webclaw` instalado.
uv sync
uv run python scripts/fetch_sitemaps.py --site all

# 4. Indexar al RAG (idempotente)
uv run python scripts/ingest_to_rag.py

# 5. Levantar el frontend (Next.js + assistant-ui)
cd frontend
cp .env.local.example .env.local        # apunta a http://localhost:8000
pnpm install
pnpm dev                                # http://localhost:3000

# 6. Abrir el chat
open http://localhost:3000
```

> El API queda en `http://localhost:8000` (FastAPI, sólo `/api/*`). El frontend
> consume `NEXT_PUBLIC_API_BASE`. CORS ya permite ambos orígenes en dev.

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
+-- apps/api/              FastAPI app
|   +-- core/              config + db pool
|   +-- routers/           /api/chat (SSE), /api/health, /api/threads (persistencia)
|   |   +-- chat_v2.py     endpoint con router agente
|   +-- rag/               embeddings, retriever, prompt
|   +-- llm/               Ollama client
|   +-- tools/             herramienta de datos estructurados
|   +-- datos_estructurados.json   datos exactos de TQ
+-- frontend/              Next.js + assistant-ui
|   +-- app/               layout + page (sidebar + chat)
|   +-- components/        ThreadList, Thread, Composer, Messages, SourcesFooter
|   +-- lib/               tqChatAdapter, threadListAdapter, sourcesStore, sse, api
+-- scripts/               fetch_sitemaps.py, ingest_to_rag.py, reset_rag.py
+-- migrations/            001_init.sql, 002_conversations.sql (auto-aplicados)
+-- data/                  raw + processed (gitignored)
+-- docs/ARCHITECTURE.md   decisiones (ADRs)
+-- docker-compose.yml
+-- pyproject.toml
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
| `DATABASE_URL` | `postgresql://tq:tq@postgres:5432/tq` | Idem - usar `localhost` desde host. |

## Herramienta de Datos Estructurados

El archivo `apps/api/datos_estructurados.json` contiene datos exactos y verificados de Tecnoquimicas: telefono, horario, NIT, sedes, marcas y lineas de negocio.

La funcion `get_structured_data(question)` en `apps/api/tools/structured_tool.py` recupera el dato preciso segun la intencion de la pregunta. A diferencia del RAG, esta herramienta es determinista y no usa embeddings ni base vectorial.

| Pregunta | Herramienta | Respuesta |
|---|---|---|
| Cual es el telefono de atencion? | Estructurada | 01 8000 912 808 |
| Cual es el horario? | Estructurada | Lun-Vie 7am-7pm, Sab 8am-1pm |
| Cual es el NIT? | Estructurada | 890.300.279-7 |
| Donde estan las sedes? | Estructurada | Cra 28 #1-50, Acopi-Yumbo |
| Cual es la historia de TQ? | RAG (pgvector) | Respuesta desde documentos |
| Que programas de sostenibilidad tiene? | RAG (pgvector) | Respuesta desde documentos |

## Router del Agente

El endpoint `apps/api/routers/chat_v2.py` implementa el agente enrutador. En cada turno, la funcion `needs_structured_tool(question)` analiza la pregunta por palabras clave y decide la ruta:

```
Pregunta del usuario
        |
        v
needs_structured_tool()
        |
   SI (telefono, horario,     NO (historia, productos,
   NIT, sede, marcas...)      cultura, innovacion...)
        |                            |
        v                            v
Herramienta estructurada        RAG pgvector
(datos_estructurados.json)      (top-k coseno)
        |                            |
        +------------+---------------+
                     |
                     v
              Qwen3-8B (Ollama)
              genera respuesta
                     |
                     v
           PostgreSQL (memoria)
```

## Pruebas de Validación del Agente

| Tipo | Pregunta | Herramienta esperada |
|---|---|---|
| RAG | Cual es la historia de Tecnoquímicas? | RAG (pgvector) |
| Memoria | Y cuando fue eso? (tras respuesta previa) | RAG con historial |
| Herramienta estructurada | Cual es el teléfono de servicio al cliente? | datos_estructurados.json |
| Enrutamiento | Cual es el horario? / Que productos tienen? | Estructurada / RAG |

## Integrantes

- Daniel Felipe Zamora
- Diego Mauricio Ortiz
- Jacob González
- Jairo Andrés Pérez Hurtatis

Maestría en Inteligencia Artificial y Ciencia de Datos
Universidad Autónoma de Occidente - UAO
Profesor: Jan Polanco Velasco

## Contribuir

Convención de commits: `tipo(scope): mensaje en español` (`feat`, `fix`, `chore`, `docs`, `refactor`).

Idioma: todo el contenido user-facing (prompts, UI, mensajes de error) está en **español**. Los identificadores de código siguen en inglés.
