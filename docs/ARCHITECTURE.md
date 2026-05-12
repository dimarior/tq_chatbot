# Arquitectura — TQ-Chatbot

> Documento vivo de decisiones arquitectónicas (ADRs) para el chatbot de Tecnoquímicas.
> Cada ADR sigue el formato: **Decisión / Razón / Alternativas rechazadas**.

## Diagrama de flujo

```
                         ┌──────────────────────────────────────────┐
                         │   scripts/fetch_sitemaps.py  (manual)    │
sitemap.xml  ──webclaw─► │   - parse <loc> + canonicalize host      │
(tqconfiable +           │   - 1 subprocess `webclaw` por URL       │  ──► data/raw/<sha1>.json
 tqfarma)                │     dentro de ThreadPoolExecutor         │       {url, text(md), hash}
                         │   - escribe disco al completar cada URL  │
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

## ADR-5 — Scraping: webclaw CLI + ThreadPoolExecutor

**Decisión.** `fetch_sitemaps.py` requiere el binario [`webclaw`](https://github.com/0xMassi/webclaw) instalado localmente (`brew install 0xMassi/webclaw/webclaw`). El script lo invoca dos veces:

1. `webclaw <sitemap_url> --raw-html` para descargar el sitemap.xml. (httpx queda bloqueado a nivel TLS por el WAF de tqconfiable; webclaw usa `wreq`+BoringSSL con perfil de Chrome y pasa.)
2. Por cada URL listada, un subprocess `webclaw <url> --format json --browser chrome --timeout 30` dentro de un `ThreadPoolExecutor(max_workers=--concurrency)`. Cada worker escribe `data/raw/<sha1>.json` apenas termina su URL, así el progreso es visible en tiempo real y los datos se preservan incluso si el run se interrumpe.

**Razón.** Tres ventajas concretas sobre las alternativas:
- **Sin browser headless**: webclaw extrae Readability + data-island (`__NEXT_DATA__`, Contentful) en HTML estático. ~10× más rápido que Playwright.
- **TLS fingerprinting**: pasa los WAFs anti-bot que rechazan a httpx en el handshake.
- **Streaming real**: el bucle de Python mete cada URL en el pool y cada worker escribe a disco al instante. Ver `data/raw/` poblándose en vivo da observabilidad y resiliencia.

**Rechazado.**
- **Webclaw en docker (`ghcr.io/0xmassi/webclaw`) en modo batch (`--urls-file`)**: probado y descartado. Webclaw acumula resultados en memoria y no escribe `--output-dir` hasta que termina el batch entero — con 1797 URLs eso son 20+ minutos sin progreso visible y un punto de falla único. Llamar el binario una vez por URL en threads da progreso real al costo de ~50 ms × N de overhead, aceptable.
- **Mantener Playwright/selectolax**: lento, frágil, ~400 MB de browser por máquina.
- **Scrapy/Selenium**: overkill o peor.

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

## ADR-11 — Frontend Next.js + assistant-ui, persistencia de hilos en Postgres

**Decisión.** Reemplazar el widget Alpine.js por un app Next.js 15 (App Router) que usa [assistant-ui](https://www.assistant-ui.com/) como conjunto de primitivos de chat. El frontend corre en su propio puerto (3000); FastAPI se queda sólo con `/api/*`. Persistencia de hilos en Postgres mediante dos tablas nuevas (`conversations`, `messages`) — sin auth, lista de hilos compartida.
**Razón.** El widget Alpine no escala a flujos con historial, sidebar, regeneración o edición de turnos. assistant-ui provee esos primitivos contra un `ChatModelAdapter` y un `RemoteThreadListAdapter` documentados, lo que nos deja conservar el contrato SSE existente (`sources` / `token` / `done` / `error`) y enchufar nuestro propio backend de persistencia. El `ChatModelAdapter` parsea el SSE manualmente; `/api/chat` queda single-shot y stateless — quien persiste son los endpoints `/api/threads/*` que el `ThreadHistoryAdapter` llama por separado. Las citas (`sources`) se almacenan en una columna JSONB sobre `messages` y se re-hidratan en un `Zustand` store keyed por `messageId`, evitando contaminar el stream de contenido del modelo.
**Rechazado.** Mantener el widget (techo bajo); reemplazar el contrato SSE por el data-stream protocol de Vercel (rompe `curl` y desperdicia trabajo existente); mover la persistencia al endpoint de chat (acoplaría streaming con escritura y complicaría reintentos/cancelación).

---

## Fuera de alcance (v1)

- Autenticación, multi-tenancy, rate limiting
- Re-ranking (BM25 / MMR / cross-encoder)
- Tests automatizados (smoke manual por ahora)
- Despliegue productivo (sólo runtime local)

## Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| Tag `qwen3-embedding:0.6b` no existe en Ollama upstream | Fallback configurable: `EMBED_BACKEND=sentence-transformers` usa el modelo HF directo. |
| El usuario debe tener `webclaw` instalado | El script verifica `which webclaw` al inicio y aborta con instrucciones de `brew install` si falta. Una sola instalación por máquina dev (~30 MB). |
| M1 Pro de 8 GB no aguanta Qwen3-8B | README documenta swap a `LLM_MODEL=qwen3:4b` (~3 GB). |
| Versión de assistant-ui cambia entre minor (export `useAui` ↔ `useAssistantApi`, nombres de primitivos) | Pin de versión en `frontend/package.json`. Si una primitiva cambia de nombre al subir minor, ajustar el adapter es la única superficie afectada (no toca backend). |
