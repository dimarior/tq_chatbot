# Arquitectura — TQ-Chatbot

> Documento vivo de decisiones arquitectónicas (ADRs) para el chatbot de Tecnoquímicas.
> Cada ADR sigue el formato: **Decisión / Razón / Alternativas rechazadas**.
> Algunas decisiones tempranas fueron **superadas** durante la reescritura de mayo 2026
> (pgvector → Chroma, Postgres → SQLite, prompt linear → LangGraph, Alpine.js → Next.js,
> docker-compose → procesos del host). Las ADRs originales se conservan para trazabilidad;
> las que fueron reemplazadas están marcadas **[SUPERADA por ADR-NN]**.

## Diagrama de flujo (estado actual)

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
data/raw/*.json     ──►  │   scripts/ingest_to_rag.py   (manual)    │  ──► Chroma persistente
                         │   - chunk (RecursiveCharacterSplitter)   │      ./chroma_db/
                         │   - embed (Qwen3-Embedding-0.6B)         │      L2 distance
                         │   - upsert por uuid5(url+idx)            │
                         │   - skip si content_hash sin cambios     │
                         └──────────────────────────────────────────┘

   Browser (Next.js)
        │
        │  HTTP/SSE
        ▼
   FastAPI  POST /api/chat
        │
        ▼
   LangGraph StateGraph  ◄──── AsyncSqliteSaver  ──►  ./tq.db (checkpoints + writes)
        │
        ├─► classify_node    (ChatOllama.with_structured_output → 'direct' | 'structured' | 'rag')
        │
        ├─► direct_node      (sin retrieval, sin tool)
        ├─► structured_node  (datos_estructurados.json + source sintético)
        └─► retrieve_node    (Chroma.similarity_search_with_score → L2 → 1/(1+L2))
              │
              ▼
        generate_node        (ChatOllama.astream → tokens)
              │
              ▼
        SSE: sources + tokens + done   ──►  Frontend

   FastAPI  /api/threads/*  ◄──── aiosqlite ──►  ./tq.db (conversations + messages)
        ▲
        └── Frontend persiste turnos + citas (canal independiente del checkpointer)

   LangSmith (opcional) ◄──── env vars LANGSMITH_* ──── traza cada nodo + cada
                                                       primitivo LangChain automáticamente
```

---

## ADR-1 — Backend: FastAPI + Pydantic v2 + uv

**Decisión.** Usar FastAPI como framework HTTP, Pydantic v2 para schemas, y `uv` como gestor de dependencias.
**Razón.** FastAPI es asíncrono, genera OpenAPI automático, soporta `StreamingResponse` para SSE de tokens en tiempo real, y tiene la mejor ergonomía de Python para APIs JSON. `uv` es ~10× más rápido que pip y reproduce builds vía `uv.lock`.
**Rechazado.** Flask (no async nativo), Django (overkill), Streamlit (era el problema original — UI y backend acoplados).

## ADR-2 — LLM local: Qwen3-8B-Instruct vía Ollama

**Decisión.** Modelo por defecto `qwen3:8b` servido por Ollama, configurable vía `LLM_MODEL`. En la reescritura LangGraph (ADR-14) se accede vía `langchain_ollama.ChatOllama`; el cliente raw `apps/api/llm/ollama_client.py` queda sólo para la generación de títulos.
**Razón.** Qwen3-8B en cuantización Q4_K_M ocupa ~5 GB y corre a 20–30 tok/s en M1 Pro 16 GB. Tiene fuerte desempeño multilingüe (español es una prioridad del proyecto). Ollama da una API HTTP estable, descarga y caché de modelos automática, y `ChatOllama.with_structured_output` permite usar el mismo motor para el router.
**Rechazado.** Llama 3.2 3B (más rápido pero peor en español), Phi-3.5 (peor en español todavía), modelos cloud (rompen el principio "todo local").

## ADR-3 — Embeddings: Qwen3-Embedding-0.6B

**Decisión.** Embeddings con Qwen3-Embedding-0.6B, dimensión 1024 (truncatable vía Matryoshka). Acceso desde el grafo vía `langchain_community.OllamaEmbeddings`.
**Razón.** Top de MTEB en 2025 entre modelos open-source pequeños, multilingüe nativo (español incluido), misma familia que el LLM (consistencia tokenización), 600 MB de memoria.
**Rechazado.** BGE-M3 (excelente alternativa pero 2.3 GB), Google text-embedding-004 (rompe local), nomic-embed-text (peor en español).

## ADR-4 — Vector store: PostgreSQL 16 + pgvector  **[SUPERADA por ADR-12]**

**Decisión original.** Postgres con extensión `pgvector`, índice HNSW con métrica coseno.
**Razón original.** Una sola base de datos para metadata + vectores. HNSW es el ANN estándar moderno con buen recall a baja latencia. Maduro, dockerizado vía imagen oficial `pgvector/pgvector:pg16`, y permite `JOIN`s normales para citar fuentes.
**Rechazado en su momento.** Qdrant/Weaviate (servicio extra), Chroma (menos maduro), FAISS local (sin durabilidad).
**Por qué se reemplazó.** Mantener un Postgres dockerizado solo para vectores se volvió desproporcionado al tamaño del corpus (≈ unos cientos de chunks). Chroma local (ADR-12) elimina el contenedor y la migración SQL, a cambio de aceptar L2 en vez de coseno nativo.

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

## ADR-7 — Frontend: Static HTML + Tailwind + Alpine.js + HTMX (SSE)  **[SUPERADA por ADR-11]**

**Decisión original.** Página estática servida por FastAPI. Tailwind vía Play CDN (v1), Alpine.js para estado del bubble (abierto/cerrado, mensajes), HTMX con extensión `sse` para streamear tokens.
**Razón original.** Sin build step. Total JS ≈ 25 KB. Alpine maneja interactividad declarativamente; HTMX gestiona el SSE con `sse-swap`. Tailwind da diseño profesional sin CSS custom.
**Rechazado en su momento.** React/Vue (build step, runtime pesado), vanilla JS puro (más boilerplate para estado), Streamlit (acoplamiento original).
**Por qué se reemplazó.** El widget Alpine no soportaba sidebar de hilos, hidratación, regeneración ni edición de turnos. Se reemplazó por Next.js + assistant-ui (ADR-11) reusando el mismo contrato SSE.

## ADR-8 — Streaming: Server-Sent Events

**Decisión.** SSE (`text/event-stream`) para enviar tokens del LLM al browser. El contrato son tres eventos (`sources`, `token`, `done`, más `error` ante fallo). `chat_v2.py` traduce los eventos de `graph.astream(stream_mode=["updates", "messages"])` a este contrato; filtra los `AIMessageChunk` del nodo `generate` (los `HumanMessage`/`AIMessage` completos que también emite el reductor `add_messages` se descartan para evitar duplicación).
**Razón.** Más simple que WebSockets para flujo unidireccional servidor→cliente. `EventSource` es nativo en navegadores. `StreamingResponse` de FastAPI lo soporta directamente. El frontend (`lib/tqChatAdapter.ts`) parsea el stream con un mini-parser SSE manual, sin depender del data-stream protocol de Vercel.
**Rechazado.** WebSockets (bidireccional innecesario), polling (latencia, costo), el data-stream protocol de Vercel (rompe `curl` y desperdicia trabajo existente).

## ADR-9 — Idempotencia por `content_hash`

**Decisión.** SHA-256 del texto normalizado de cada página se guarda en metadata del chunk (`content_hash`). La ingesta compara hash → si coincide, salta; si difiere, borra los chunks viejos del mismo `url` y re-inserta. Los IDs de chunk son deterministas: `uuid5(NAMESPACE_URL, "<url>#<idx>")`.
**Razón.** Determinístico, sin estado externo, no requiere migraciones para re-correr. Permite re-ejecutar `fetch_sitemaps.py` y `ingest_to_rag.py` cuantas veces se quiera sin duplicar ni corromper datos. El uso de `uuid5` por URL+índice hace el upsert seguro en Chroma sin necesidad de transacciones.
**Rechazado.** Truncate-and-rebuild (lento y descarta histórico), timestamps `last-modified` del servidor (poco confiables en tqfarma/tqconfiable).

## ADR-10 — Containerización: docker-compose  **[SUPERADA por ADR-13]**

**Decisión original.** `docker-compose.yml` con tres servicios principales (`postgres`, `ollama`, `api`) y un servicio one-shot `ollama-init` que descarga modelos al primer arranque. Frontend servido como estáticos por FastAPI.
**Razón original.** Un solo comando `docker compose up` levanta el stack completo. Volúmenes persistentes para datos de Postgres y modelos de Ollama. Reproducible en cualquier máquina con Docker Desktop.
**Rechazado en su momento.** Kubernetes (overkill), instalación nativa (no reproducible), múltiples docker-compose (fragmentación innecesaria).
**Por qué se reemplazó.** Al migrar a Chroma (ADR-12) y SQLite (ADR-13) ya no quedaba ningún servicio que requiriera contenedor — Ollama corre nativo en el host (mejor desempeño en Apple Silicon), Chroma es un directorio y SQLite es un archivo. El docker-compose y el Dockerfile se eliminaron; el desarrollo arranca con `make backend` y `make frontend`.

## ADR-11 — Frontend Next.js + assistant-ui, persistencia de hilos en SQLite

**Decisión.** Reemplazar el widget Alpine.js por un app Next.js 15 (App Router) que usa [assistant-ui](https://www.assistant-ui.com/) como conjunto de primitivos de chat. El frontend corre en su propio puerto (3000); FastAPI se queda sólo con `/api/*`. Persistencia de hilos en SQLite mediante dos tablas (`conversations`, `messages`) — sin auth, lista de hilos compartida. _Originalmente la persistencia se diseñó sobre Postgres; con ADR-13 se movió al mismo archivo `tq.db` que usa el checkpointer del grafo._
**Razón.** El widget Alpine no escala a flujos con historial, sidebar, regeneración o edición de turnos. assistant-ui provee esos primitivos contra un `ChatModelAdapter` y un `RemoteThreadListAdapter` documentados, lo que nos deja conservar el contrato SSE existente (`sources` / `token` / `done` / `error`) y enchufar nuestro propio backend de persistencia. El `ChatModelAdapter` parsea el SSE manualmente; `/api/chat` queda single-shot y stateless — quien persiste son los endpoints `/api/threads/*` que el `ThreadHistoryAdapter` llama por separado. Las citas (`sources`) se almacenan en una columna JSON sobre `messages` y se re-hidratan en un `Zustand` store keyed por `messageId`, evitando contaminar el stream de contenido del modelo.
**Rechazado.** Mantener el widget (techo bajo); reemplazar el contrato SSE por el data-stream protocol de Vercel (rompe `curl` y desperdicia trabajo existente); mover la persistencia al endpoint de chat (acoplaría streaming con escritura y complicaría reintentos/cancelación).

---

## ADR-12 — Vector store: Chroma persistente local

**Decisión.** Reemplazar PostgreSQL + pgvector por **Chroma** (`langchain_community.vectorstores.Chroma`) con `persist_directory=./chroma_db`. La métrica es la default de Chroma (L2) y la transformamos a similitud con `1/(1+L2)` antes de filtrar por `min_score`. La ingesta usa `vector_store.add_documents(..., ids=[uuid5(NAMESPACE_URL, f"{url}#{i}")])` para upserts deterministas; el reindex de un documento borra antes con `vector_store.delete(where={"url": url})`.
**Razón.** El corpus son cientos de chunks, no millones — no requiere un Postgres dedicado. Chroma local elimina el contenedor, la migración SQL y la conexión asyncpg. El `1/(1+L2)` mapea bien la noción de "más alto = más relevante" aunque no sea coseno nativo. Es la opción que permitió eliminar Docker del proyecto (ADR-13).
**Rechazado.** Mantener pgvector (overkill para el tamaño del corpus, ata el proyecto a docker-compose), Qdrant/Weaviate (otro servicio extra), FAISS in-memory (sin durabilidad). Cambiar Chroma a métrica coseno explícita: se evaluó pero el default funciona y cambiar implicaría reingestar y recalibrar `MIN_SCORE` otra vez.
**Costos asumidos.** El umbral `MIN_SCORE` ya no es comparable con la calibración anterior basada en coseno — se setea actualmente en `0.40` y debe recalibrarse si se cambia el modelo de embedding. Documentado en variables de entorno del README.

## ADR-13 — Persistencia consolidada en SQLite (un solo archivo)

**Decisión.** Un único archivo `./tq.db` (SQLite con WAL + `foreign_keys=ON`) contiene **dos capas independientes**:
- `conversations` + `messages` (la vista persistente para la UI). Las maneja `apps/api/core/db.py` (`Database` + `aiosqlite`) y el router `apps/api/routers/threads.py`. UUIDs viajan como TEXT, booleanos como INTEGER, timestamps como ISO 8601 TEXT.
- `checkpoints` + `writes` + `checkpoint_migrations` (el state del grafo). Las crea `AsyncSqliteSaver` (de `langgraph-checkpoint-sqlite`) al llamar `await checkpointer.setup()` en el lifespan. Se accede con una conexión `aiosqlite` separada compartida durante la vida del proceso.

**Razón.** Eliminamos completamente Postgres. La conversación persistente para el frontend y la memoria por hilo del grafo (necesaria para que el router decida 'direct' en follow-ups) viven en el mismo archivo: backup trivial (`cp tq.db backup.db`), reset trivial (`rm tq.db tq.db-wal tq.db-shm`), cero dependencias externas. WAL mode permite que el checkpointer y `threads.py` lean/escriban concurrentemente sin lock contention.
**Rechazado.** Postgres mantenido sólo para esto (overkill, requiere docker o instalación nativa), dos archivos SQLite separados (más complicado de respaldar/limpiar, sin ganancia), almacenar el state del grafo en memoria (se pierde al reiniciar el backend → el router perdería el contexto del hilo).
**Costos asumidos.** SQLite no soporta escritura concurrente real, pero WAL + un único proceso uvicorn lo hacen suficiente para desarrollo local. Si en el futuro hay despliegue multi-worker, esta ADR se reemplazaría volviendo a Postgres + `AsyncPostgresSaver`.

## ADR-14 — Orquestación con LangGraph + router LLM de 3 vías

**Decisión.** El flujo del agente vive en un `StateGraph` de [LangGraph](https://langchain-ai.github.io/langgraph/) con cinco nodos (`classify`, `direct`, `structured`, `retrieve`, `generate`) y una conditional edge tras `classify`. El estado (`ChatState`) es un `TypedDict` con `messages: Annotated[list[BaseMessage], add_messages]` — el reductor `add_messages` acumula el historial automáticamente. El router (`classify_node`) usa `ChatOllama.with_structured_output(RouteDecision)` (Pydantic con `route: Literal["direct", "structured", "rag"]`) sobre los últimos 6 mensajes + la pregunta nueva.
**Razón.** La instrucción del docente para esta entrega fue **"usar las herramientas que ya existen, no inventar"**. LangGraph estandariza orquestación (state, edges condicionales, streaming dual `updates`+`messages`) y se integra de serie con LangSmith (ADR-15) y con el checkpointer SQLite (ADR-13). El router LLM de 3 vías corrige un problema observado del diseño binario inicial: cada turno disparaba Chroma o el JSON, incluso para follow-ups que se respondían con el historial. La ruta `direct` es la mejora clave — sin retrieval, sin tool, sin chips, respuesta sale del historial cargado por el checkpointer.
**Rechazado.** Cadena lineal hecha a mano (perdíamos el branching limpio, el streaming dual y la integración LangSmith), routing por keywords (`needs_structured_tool`) — se eliminó porque el LLM clasifica mejor los grises ("¿y cómo se relaciona eso con Dolex?" no matchea keywords pero requiere RAG); seguir con dos rutas únicamente (alto desperdicio de tokens en follow-ups conversacionales).
**Costos asumidos.** Añade `langgraph`, `langgraph-checkpoint-sqlite` y `langchain-ollama` como dependencias. El clasificador hace una llamada extra al LLM por turno (~150–400 ms) — mitigable usando `LLM_ROUTER_MODEL=qwen3:1.7b` si llega a ser el cuello de botella.

## ADR-15 — Monitoreo: LangSmith vía variables de entorno

**Decisión.** El tracing del agente se hace con [LangSmith](https://smith.langchain.com). El lifespan de `apps/api/main.py` exporta `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` y `LANGSMITH_ENDPOINT` a `os.environ` **antes** de importar `langgraph`. No hay código de instrumentación: cada nodo del grafo, cada llamada a `ChatOllama` y cada `similarity_search` en Chroma se trazan automáticamente.
**Razón.** Misma instrucción del docente que en ADR-14: usar lo ya existente. LangSmith es el servicio nativo del ecosistema LangChain/LangGraph y reconoce los nombres de los nodos del `StateGraph` sin configuración adicional. Cuando `LANGSMITH_TRACING=false` (o falta la API key), no se envía nada al servicio externo — útil para desarrollo offline o demos sin red.
**Rechazado.** Logs estructurados a stdout + parser externo (más trabajo, menos contexto por traza), OpenTelemetry + Tempo/Jaeger (setup desproporcionado para una entrega académica), instrumentar a mano con callbacks de LangChain (re-implementar lo que LangSmith ya hace).
**Costos asumidos.** Dependencia de un SaaS externo (gratis hasta cierto volumen). Si en el futuro hace falta autohospedaje, `LANGSMITH_ENDPOINT` apunta a una instancia self-hosted sin tocar código.

---

## Fuera de alcance (v1)

- Autenticación, multi-tenancy, rate limiting
- Re-ranking (BM25 / MMR / cross-encoder)
- Tests automatizados (smoke manual por ahora)
- Despliegue productivo (sólo runtime local)
- Despliegue multi-worker (SQLite + `AsyncSqliteSaver` asumen un único proceso uvicorn)

## Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| Tag `qwen3-embedding:0.6b` no existe en Ollama upstream | Fallback configurable: `EMBED_BACKEND=sentence-transformers` usa el modelo HF directo. |
| El usuario debe tener `webclaw` instalado | El script verifica `which webclaw` al inicio y aborta con instrucciones de `brew install` si falta. Una sola instalación por máquina dev (~30 MB). |
| M1 Pro de 8 GB no aguanta Qwen3-8B | README documenta swap a `LLM_MODEL=qwen3:4b` (~3 GB). |
| Versión de assistant-ui cambia entre minor (export `useAui` ↔ `useAssistantApi`, nombres de primitivos) | Pin de versión en `frontend/package.json`. Si una primitiva cambia de nombre al subir minor, ajustar el adapter es la única superficie afectada (no toca backend). |
| `MIN_SCORE = 0.40` está calibrado para `1/(1+L2)` con Qwen3-Embedding-0.6B sobre el corpus actual. Reingestar o cambiar embedding lo invalida. | Documentado en README. La recalibración es manual: bajar el umbral hasta que `rag` empiece a devolver chips estables otra vez. |
| Stale Docker containers del docker-compose previo pueden chocar con uvicorn en `:8000` | El README pide `docker stop <nombre>` antes del primer `make backend`. |
| El router LLM clasifica mal (`rag` cuando debió ser `direct`, por ej.) | `classify_node` loguea cada decisión (`router → <route> | history=N msgs | q=...`). Las pruebas de validación del README cubren los casos típicos. Si se nota deriva, ajustar `ROUTER_SYSTEM` en `apps/api/graph/nodes.py`. |
