# Arquitectura — TQ-Chatbot

> Documento vivo de decisiones arquitectónicas (ADRs) para el chatbot de Tecnoquímicas.
> Cada ADR sigue el formato: **Decisión / Razón / Alternativas rechazadas**.

## Diagrama de flujo

```
                         ┌──────────────────────────────────────────┐
                         │   scripts/fetch_sitemaps.py  (manual)    │
sitemap.xml  ──httpx──►  │   - parse <loc> tags                     │
(tqconfiable +           │   - fetch HTML (selectolax / Playwright) │  ──► data/raw/<sha1>.json
 tqfarma)                │   - retry con tenacity                   │       {url, text, hash}
                         │   - skip si content_hash sin cambios     │
                         └──────────────────────────────────────────┘

                         ┌──────────────────────────────────────────┐
data/raw/*.json     ──►  │   scripts/ingest_to_rag.py   (manual)    │  ──► PostgreSQL + pgvector
                         │   - chunk (RecursiveCharacterSplitter)   │      documents + chunks
                         │   - embed (Qwen3-Embedding-0.6B)         │      HNSW cosine index
                         │   - upsert idempotente                   │
                         └──────────────────────────────────────────┘

   Browser (bubble) ──HTTP/SSE──► FastAPI ──► RAG retrieve (top-k cosine)
                                          ──► Ollama stream (Qwen3-8B)
                                          ──► SSE tokens + sources back to bubble
```

---

## ADR-1 — Backend: FastAPI + Pydantic v2 + uv

**Decisión.** Usar FastAPI como framework HTTP, Pydantic v2 para schemas, y `uv` como gestor de dependencias.
**Razón.** FastAPI es asíncrono, genera OpenAPI automático, soporta `StreamingResponse` para SSE de tokens en tiempo real, y tiene la mejor ergonomía de Python para APIs JSON. `uv` es ~10× más rápido que pip y reproduce builds vía `uv.lock`.
**Rechazado.** Flask (no async nativo), Django (overkill), Streamlit (era el problema original — UI y backend acoplados).

## ADR-2 — LLM local: Qwen3-8B-Instruct vía Ollama

**Decisión.** Modelo por defecto `qwen3:8b` servido por Ollama, configurable vía `LLM_MODEL`.
**Razón.** Qwen3-8B en cuantización Q4_K_M ocupa ~5 GB y corre a 20–30 tok/s en M1 Pro 16 GB. Tiene fuerte desempeño multilingüe (español es una prioridad del proyecto). Ollama da una API HTTP estable, descarga y caché de modelos automática, y se dockeriza trivialmente.
**Rechazado.** Llama 3.2 3B (más rápido pero peor en español), Phi-3.5 (peor en español todavía), modelos cloud (rompen el principio "todo local").

## ADR-3 — Embeddings: Qwen3-Embedding-0.6B

**Decisión.** Embeddings con Qwen3-Embedding-0.6B, dimensión 1024 (truncatable vía Matryoshka).
**Razón.** Top de MTEB en 2025 entre modelos open-source pequeños, multilingüe nativo (español incluido), misma familia que el LLM (consistencia tokenización), 600 MB de memoria.
**Rechazado.** BGE-M3 (excelente alternativa pero 2.3 GB), Google text-embedding-004 (rompe local), nomic-embed-text (peor en español).

## ADR-4 — Vector store: PostgreSQL 16 + pgvector

**Decisión.** Postgres con extensión `pgvector`, índice HNSW con métrica coseno.
**Razón.** Una sola base de datos para metadata + vectores. HNSW es el ANN estándar moderno con buen recall a baja latencia. Maduro, dockerizado vía imagen oficial `pgvector/pgvector:pg16`, y permite `JOIN`s normales para citar fuentes.
**Rechazado.** Qdrant/Weaviate (servicio extra), Chroma (menos maduro), FAISS local (sin durabilidad).

## ADR-5 — Scraping: httpx + selectolax + Playwright (fallback) + tenacity

**Decisión.** Pipeline en dos niveles — primero httpx async + selectolax para HTML estático; si la extracción es pobre o la página marca señales de SPA (`__NEXT_DATA__`, `data-reactroot`, contenido < 200 caracteres), fallback a Playwright headless. Reintentos con `tenacity` (3 intentos, exp backoff).
**Razón.** `httpx` es async-nativo; `selectolax` es 5–10× más rápido que BeautifulSoup en parsing. Playwright >> Selenium en estabilidad y velocidad para JS-rendered. `tenacity` da retry declarativo.
**Rechazado.** Selenium (lento, frágil), requests (sync), Scrapy (overkill para 2 sitemaps).

## ADR-6 — Chunking: RecursiveCharacterTextSplitter (~600 / 100)

**Decisión.** `langchain_text_splitters.RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)` con separadores conscientes de párrafos.
**Razón.** Bien comprendido, predecible, conserva semántica de párrafo. Tamaño ~600 tokens deja margen para 6 chunks + prompt + respuesta dentro de la ventana de 8 K de Qwen3.
**Rechazado.** Token-based con `tiktoken` (Qwen no usa BPE de OpenAI), splitting semántico con embeddings (overhead sin ganancia clara para v1).

## ADR-7 — Frontend: Static HTML + Tailwind + Alpine.js + HTMX (SSE)

**Decisión.** Página estática servida por FastAPI. Tailwind vía Play CDN (v1), Alpine.js para estado del bubble (abierto/cerrado, mensajes), HTMX con extensión `sse` para streamear tokens.
**Razón.** Sin build step. Total JS ≈ 25 KB. Alpine maneja interactividad declarativamente; HTMX gestiona el SSE con `sse-swap`. Tailwind da diseño profesional sin CSS custom.
**Rechazado.** React/Vue (build step, runtime pesado), vanilla JS puro (más boilerplate para estado), Streamlit (acoplamiento original).

## ADR-8 — Streaming: Server-Sent Events

**Decisión.** SSE (`text/event-stream`) para enviar tokens del LLM al browser.
**Razón.** Más simple que WebSockets para flujo unidireccional servidor→cliente. `EventSource` es nativo en navegadores. `StreamingResponse` de FastAPI lo soporta directamente. HTMX tiene extensión oficial `htmx-ext-sse`.
**Rechazado.** WebSockets (bidireccional innecesario), polling (latencia, costo).

## ADR-9 — Idempotencia por `content_hash`

**Decisión.** SHA-256 del texto normalizado de cada página se guarda en `documents.content_hash`. La ingesta compara hash → si coincide, salta; si difiere, borra chunks viejos y re-inserta dentro de una transacción.
**Razón.** Determinístico, sin estado externo, no requiere migraciones para re-correr. Permite re-ejecutar `fetch_sitemaps.py` y `ingest_to_rag.py` cuantas veces se quiera sin duplicar ni corromper datos.
**Rechazado.** Truncate-and-rebuild (lento y descarta histórico), timestamps `last-modified` del servidor (poco confiables en tqfarma/tqconfiable).

## ADR-10 — Containerización: docker-compose

**Decisión.** `docker-compose.yml` con tres servicios principales (`postgres`, `ollama`, `api`) y un servicio one-shot `ollama-init` que descarga modelos al primer arranque. Frontend servido como estáticos por FastAPI.
**Razón.** Un solo comando `docker compose up` levanta el stack completo. Volúmenes persistentes para datos de Postgres y modelos de Ollama. Reproducible en cualquier máquina con Docker Desktop.
**Rechazado.** Kubernetes (overkill), instalación nativa (no reproducible), múltiples docker-compose (fragmentación innecesaria).

---

## Fuera de alcance (v1)

- Autenticación, multi-tenancy, rate limiting
- Persistencia de historial de chat (estado en memoria del cliente)
- Re-ranking (BM25 / MMR / cross-encoder)
- Tests automatizados (smoke manual por ahora)
- Despliegue productivo (sólo runtime local)

## Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| Tag `qwen3-embedding:0.6b` no existe en Ollama upstream | Fallback configurable: `EMBED_BACKEND=sentence-transformers` usa el modelo HF directo. |
| Playwright pesa ~400 MB en imagen Docker | Sólo se requiere para el script de fetch — no se incluye en `Dockerfile.api`. Se ejecuta en host. |
| M1 Pro de 8 GB no aguanta Qwen3-8B | README documenta swap a `LLM_MODEL=qwen3:4b` (~3 GB). |
| Tailwind Play CDN tiene latencia de primer paint | Aceptable para v1 demo; ruta de upgrade documentada (build de CSS local). |
