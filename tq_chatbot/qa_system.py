
from __future__ import annotations
import functools
import json
import logging
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Generator, List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
# ── LangChain ────────────────────────────────────────────────────────────────
from langchain_community.cache import InMemoryCache
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_community.vectorstores import FAISS
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.globals import set_llm_cache
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI, HarmCategory, HarmBlockThreshold
from langchain_huggingface import HuggingFaceEmbeddings
# ── LangGraph ─────────────────────────────────────────────────────────────────
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
# ── BM25 — intentamos bm25s primero (más rápido); fallback a rank_bm25 ───────
try:
    import bm25s
    _BM25_BACKEND = "bm25s"
except ImportError:
    from langchain_community.retrievers import BM25Retriever
    _BM25_BACKEND = "langchain"
# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — LOGGING & CONFIGURACIÓN GLOBAL
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
)
logger = logging.getLogger("TQ·RAG·v2")
load_dotenv()
# ── Constantes ────────────────────────────────────────────────────────────────
EMBEDDING_MODEL     = "intfloat/multilingual-e5-large"
CROSS_ENCODER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
LLM_MODEL           = "gemini-2.5-flash"
FAISS_K         = 20
BM25_K          = 15
RERANKER_TOP_N  = 8
RRF_K           = 60
DENSE_WEIGHT    = 0.65
SPARSE_WEIGHT   = 0.35
MAX_WORKERS     = 4
MIN_QUERY_LEN   = 3
BASE_DIR        = Path(r"C:\Users\danie\Desktop\TAIA")
INDEX_CORP_PATH = BASE_DIR / "faiss_corporativo"
INDEX_MED_PATH  = BASE_DIR / "faiss_medico"
JSON_PATH       = BASE_DIR / "datos_estructurados.json"
set_llm_cache(InMemoryCache())
def get_api_key() -> str:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise EnvironmentError("Falta GOOGLE_API_KEY en .env")
    return key
# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — UTILIDADES DE TEXTO Y GUARDRAILS
# ══════════════════════════════════════════════════════════════════════════════
def sanitize_query(query: str) -> str:
    """Normaliza unicode, colapsa espacios y limita a 1000 chars."""
    if not isinstance(query, str):
        return ""
    text = unicodedata.normalize("NFC", query)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text[:1000]
def is_valid_query(query: str) -> bool:
    return bool(re.search(r"[a-zA-ZáéíóúñüÁÉÍÓÚÑÜ]{2,}", query.strip()))
_TOXICITY_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.I | re.U) for p in [
        r"\b(mierda|hijueputa|malparido|gonorrea|perra|marica|idiota|imbécil|pendejo|hp)\b",
        r"\b(fuck|shit|asshole|bitch|damn)\b",
        r"(te\s+voy\s+a|voy\s+a\s+matarte|amenaz)",
        r"(contenido\s+sexual|desnud|pornograf)",
        r"(hack|exploit|inyección\s+sql|prompt\s+injection)",
    ]
]
_TOXIC_RESPONSE = (
    "Te pido que mantengamos un lenguaje respetuoso en esta conversación. "
    "Como asistente corporativo de Tecnoquímicas S.A., mi protocolo me obliga "
    "a pausar la consulta cuando se detecta lenguaje inapropiado. "
    "Si deseas reformular tu pregunta de forma respetuosa, estaré encantado "
    "de ayudarte con toda la información disponible."
)
def is_toxic(text: str) -> bool:
    return any(p.search(text) for p in _TOXICITY_PATTERNS)
def _timer(label: str):
    """Decorador de latencia para debug."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            result = fn(*args, **kwargs)
            ms = (time.perf_counter() - t0) * 1000
            logger.debug("⏱  %s → %.1f ms", label, ms)
            return result
        return wrapper
    return decorator
# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — CLASIFICADOR SEMÁNTICO DE INTENCIÓN
# ══════════════════════════════════════════════════════════════════════════════
_SOCIAL_PATTERNS = re.compile(
    r"^\s*(hola|buenos?\s+(días?|tardes?|noches?)|gracias|hasta\s+luego|"
    r"bye|chao|qué\s+tal|cómo\s+estás?|ok|okay|perfecto|entendido)\s*[.!?]?\s*$",
    re.I | re.U,
)
_CONTACT_KEYWORDS = {
    "teléfono", "telefono", "celular", "correo", "email", "dirección",
    "direccion", "sede", "nit", "rut", "horario", "atención", "atencion",
    "pqr", "queja", "reclamo", "línea ética", "linea etica", "contacto",
}
_MEDICAL_KEYWORDS = {
    "artículo", "articulo", "médico", "medico", "científico", "cientifico",
    "vademécum", "vademecum", "especialidad", "contraindicación", "contraindicacion",
    "dosis", "dosificación", "dosificacion", "tqfarma", "farmacéutico",
    "farmaceutico", "patología", "patologia", "tratamiento", "diagnóstico",
    "diagnostico",
}
class QueryIntent:
    SOCIAL    = "social"
    CONTACT   = "contact"
    MEDICAL   = "medical"
    CORPORATE = "corporate"
    UNKNOWN   = "unknown"
def classify_intent(query: str) -> str:
    q_lower = query.lower()
    if _SOCIAL_PATTERNS.match(query):
        return QueryIntent.SOCIAL
    words = set(re.findall(r"[a-záéíóúñü]+", q_lower))
    if words & _CONTACT_KEYWORDS:
        return QueryIntent.CONTACT
    if words & _MEDICAL_KEYWORDS:
        return QueryIntent.MEDICAL
    return QueryIntent.UNKNOWN
# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — BM25 WRAPPER UNIFICADO
# ══════════════════════════════════════════════════════════════════════════════
class BM25Wrapper:
    """
    Abstrae bm25s (rápido, nativo NumPy) o BM25Retriever de langchain.
    Expone .invoke(query) → List[Document] igual que un BaseRetriever.
    """
    def __init__(self, documents: list[Document], k: int = BM25_K):
        self.k = k
        self._docs = documents
        if _BM25_BACKEND == "bm25s":
            corpus = [d.page_content for d in documents]
            tokenized = bm25s.tokenize(corpus, stopwords="es")
            self._retriever = bm25s.BM25()
            self._retriever.index(tokenized)
            logger.info("BM25S backend activo (%d docs).", len(documents))
        else:
            from langchain_community.retrievers import BM25Retriever
            self._retriever = BM25Retriever.from_documents(documents, k=k)
            logger.info("BM25 langchain-community backend activo (%d docs).", len(documents))
    def invoke(self, query: str) -> list[Document]:
        if _BM25_BACKEND == "bm25s":
            tokenized_q = bm25s.tokenize([query], stopwords="es")
            results, _ = self._retriever.retrieve(tokenized_q, k=min(self.k, len(self._docs)))
            indices = results[0].tolist()
            return [self._docs[i] for i in indices]
        else:
            return self._retriever.invoke(query)
# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 5 — RETRIEVER HÍBRIDO OPTIMIZADO
# ══════════════════════════════════════════════════════════════════════════════
class HybridRetriever(BaseRetriever):
    """
    Retriever híbrido de producción con:
      1. MultiQuery expansion paralela (ThreadPoolExecutor)
      2. RRF Fusion con pesos calibrados
      3. CrossEncoder Reranker con score en metadata
    """
    dense_store:    Any
    sparse_store:   Any
    cross_encoder:  Any
    llm_expander:   Any
    top_k:          int = RERANKER_TOP_N
    use_multiquery: bool = True

    # ── FIX: Pydantic v2 — reemplaza `class Config` deprecado ────────────────
    model_config = {"arbitrary_types_allowed": True}

    @_timer("HybridRetriever._get_relevant_documents")
    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        # ── 1. Expansión de queries (paralela) ───────────────────────────────
        queries = [query]
        if self.use_multiquery and len(query.split()) >= 4:
            try:
                expanded = self._expand_queries_parallel(query)
                queries = list(dict.fromkeys(expanded + [query]))
            except Exception as exc:
                logger.warning("MultiQuery falló, usando query original: %s", exc)
        # ── 2. Recuperación paralela densa + léxica ──────────────────────────
        doc_map:   dict[str, Document] = {}
        rrf_score: dict[str, float]    = {}
        def _fetch(q: str):
            dense  = self.dense_store.as_retriever(
                search_type="mmr",
                search_kwargs={"k": FAISS_K, "lambda_mult": 0.7},
            ).invoke(q)
            sparse = self.sparse_store.invoke(q)
            return dense, sparse
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(queries))) as pool:
            futures = {pool.submit(_fetch, q): q for q in queries}
            for future in as_completed(futures):
                try:
                    dense_docs, sparse_docs = future.result()
                except Exception as exc:
                    logger.warning("Fetch falló para una query: %s", exc)
                    continue
                for rank, doc in enumerate(dense_docs):
                    key = doc.page_content[:200]
                    doc_map[key] = doc
                    rrf_score[key] = rrf_score.get(key, 0.0) + (
                        DENSE_WEIGHT / (RRF_K + rank)
                    )
                for rank, doc in enumerate(sparse_docs):
                    key = doc.page_content[:200]
                    doc_map.setdefault(key, doc)
                    rrf_score[key] = rrf_score.get(key, 0.0) + (
                        SPARSE_WEIGHT / (RRF_K + rank)
                    )
        if not doc_map:
            return []
        # ── 3. Top-N por RRF ─────────────────────────────────────────────────
        top_rrf = sorted(
            doc_map.values(),
            key=lambda d: rrf_score[d.page_content[:200]],
            reverse=True,
        )[:25]
        # ── 4. CrossEncoder Reranker ─────────────────────────────────────────
        pairs  = [[query, doc.page_content] for doc in top_rrf]
        scores = self.cross_encoder.score(pairs)
        for doc, score in zip(top_rrf, scores):
            doc.metadata["rerank_score"] = round(float(score), 4)
            doc.metadata["rrf_score"]    = round(rrf_score[doc.page_content[:200]], 6)
        final = sorted(top_rrf, key=lambda d: d.metadata["rerank_score"], reverse=True)
        return final[: self.top_k]
    def _expand_queries_parallel(self, query: str) -> list[str]:
        prompt = (
            "Genera exactamente 2 variaciones semánticas de esta búsqueda. "
            "Solo las variaciones, una por línea, sin numeración:\n"
            f"{query}"
        )
        resp = self.llm_expander.invoke(prompt).content
        return [
            line.strip()
            for line in resp.split("\n")
            if len(line.strip()) > 5
        ]
# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 6 — SINGLETON DE MODELOS (lazy loading)
# ══════════════════════════════════════════════════════════════════════════════
class _ModelRegistry:
    _instance: Optional[_ModelRegistry] = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    def initialize(self):
        if self._initialized:
            return
        logger.info("Cargando embeddings '%s'...", EMBEDDING_MODEL)
        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        logger.info("Cargando cross-encoder '%s'...", CROSS_ENCODER_MODEL)
        self.cross_encoder = HuggingFaceCrossEncoder(model_name=CROSS_ENCODER_MODEL)
        self._initialized = True
    @property
    def ready(self) -> bool:
        return self._initialized
registry = _ModelRegistry()
# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 7 — CARGA DE ÍNDICES
# ══════════════════════════════════════════════════════════════════════════════
def _load_index(
    path: Path,
    embeddings,
    cross_encoder,
    llm,
    label: str,
) -> Optional[HybridRetriever]:
    if not path.exists():
        logger.warning("Índice '%s' no encontrado en %s.", label, path)
        return None
    try:
        t0 = time.perf_counter()
        vs = FAISS.load_local(
            str(path), embeddings, allow_dangerous_deserialization=True
        )
        all_docs = list(vs.docstore._dict.values())
        bm25 = BM25Wrapper(all_docs, k=BM25_K)
        retriever = HybridRetriever(
            dense_store=vs,
            sparse_store=bm25,
            cross_encoder=cross_encoder,
            llm_expander=llm,
            top_k=RERANKER_TOP_N,
        )
        logger.info(
            "Índice '%s' cargado (%d docs) en %.1f s.",
            label, len(all_docs), time.perf_counter() - t0,
        )
        return retriever
    except Exception as exc:
        logger.error("Error cargando índice '%s': %s", label, exc, exc_info=True)
        return None
def _load_json(path: Path) -> dict:
    if not path.exists():
        logger.warning("datos_estructurados.json no encontrado.")
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
retriever_corp: Optional[HybridRetriever] = None
retriever_med:  Optional[HybridRetriever] = None
datos_estructurados: dict = {}
def build_system() -> None:
    global retriever_corp, retriever_med, datos_estructurados
    registry.initialize()
    llm_base = ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        google_api_key=get_api_key(),
        temperature=0,
        safety_settings={
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        }
    )
    retriever_corp = _load_index(
        INDEX_CORP_PATH, registry.embeddings, registry.cross_encoder, llm_base, "corporativo"
    )
    retriever_med = _load_index(
        INDEX_MED_PATH, registry.embeddings, registry.cross_encoder, llm_base, "medico"
    )
    datos_estructurados = _load_json(JSON_PATH)
    logger.info("Sistema TQ-RAG listo.")
# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 8 — HERRAMIENTAS DEL AGENTE
# ══════════════════════════════════════════════════════════════════════════════
def _format_docs(docs: list[Document], source: str) -> str:
    if not docs:
        return f"No se encontró información en la base {source}."
    parts = [f"Contexto RAG — {source}:\n"]
    for i, doc in enumerate(docs, 1):
        score_info = ""
        if "rerank_score" in doc.metadata:
            score_info = f" [score={doc.metadata['rerank_score']:.3f}]"
        url_line = ""
        if doc.metadata.get("url"):
            url_line = f"\n🔗 URL: {doc.metadata['url']}"
        parts.append(f"── Fragmento {i}{score_info} ──\n{doc.page_content}{url_line}")
    return "\n\n".join(parts)
@tool
def buscar_info_corporativa(query: str) -> str:
    """
    USA ESTA HERRAMIENTA para: historia, hitos, premios, marcas de consumo masivo
    (Winny, MK, LUA, Content, Yodora, Ibuflash, etc.), sostenibilidad,
    cultura organizacional, misión, visión, cifras operativas (colaboradores,
    referencias producidas, sedes) y cualquier contenido narrativo sobre TQ.
    """
    if not retriever_corp:
        return "Índice corporativo no disponible."
    q = sanitize_query(query)
    if not is_valid_query(q):
        return "Query inválida."
    try:
        docs = retriever_corp.invoke(q)
        return _format_docs(docs, "Corporativo")
    except Exception as exc:
        logger.error("buscar_info_corporativa error: %s", exc, exc_info=True)
        return "Error interno al buscar información corporativa."
@tool
def buscar_info_medica(query: str) -> str:
    """
    USA ESTA HERRAMIENTA para: artículos científicos, vademécum, especialidades
    médicas (cardiología, neurología, pediatría, etc.), contraindicaciones,
    dosificaciones, investigaciones clínicas y contenido de TQFarma.
    Incluye URLs directas a los artículos del portal para profesionales de la salud.
    """
    if not retriever_med:
        return "Índice médico no disponible."
    q = sanitize_query(query)
    if not is_valid_query(q):
        return "Query inválida."
    try:
        docs = retriever_med.invoke(q)
        return _format_docs(docs, "Médico TQFarma")
    except Exception as exc:
        logger.error("buscar_info_medica error: %s", exc, exc_info=True)
        return "Error interno al buscar información médica."
_JSON_INTENT_MAP: dict[str, list[str]] = {
    "telefono":   ["telefonos_globales", "sedes_y_direcciones_oficiales"],
    "correo":     ["correos_oficiales"],
    "email":      ["correos_oficiales"],
    "sede":       ["sedes_y_direcciones_oficiales"],
    "direccion":  ["sedes_y_direcciones_oficiales"],
    "nit":        ["perfil_corporativo"],
    "rut":        ["perfil_corporativo"],
    "horario":    ["horarios_detectados"],
    "marca":      ["portafolio"],
    "portafolio": ["portafolio"],
    "etica":      ["linea_etica"],
    "linea":      ["linea_etica", "telefonos_globales"],
    "pqr":        ["servicio_al_cliente"],
    "queja":      ["servicio_al_cliente"],
    "reclamo":    ["servicio_al_cliente"],
    "servicio":   ["servicio_al_cliente"],
    "atencion":   ["servicio_al_cliente", "horarios_detectados"],
    "cliente":    ["servicio_al_cliente"],
}
def _filter_json_by_intent(query: str, data: dict) -> dict:
    q_lower = query.lower()
    selected_keys: set[str] = set()
    for keyword, sections in _JSON_INTENT_MAP.items():
        if keyword in q_lower:
            selected_keys.update(sections)
    if not selected_keys:
        return {"directorio_contacto": data.get("directorio_contacto", {})}
    result: dict = {}
    for key in selected_keys:
        if key in data:
            result[key] = data[key]
        elif key in data.get("directorio_contacto", {}):
            result.setdefault("directorio_contacto", {})[key] = (
                data["directorio_contacto"][key]
            )
        elif key in data.get("perfil_corporativo", {}):
            result.setdefault("perfil_corporativo", {})[key] = (
                data["perfil_corporativo"][key]
            )
    return result or {"directorio_contacto": data.get("directorio_contacto", {})}
@tool
def buscar_datos_estructurados(query: str) -> str:
    """
    USA ESTA HERRAMIENTA para recuperar datos exactos y verificados:
    teléfonos, correos electrónicos, NIT, direcciones físicas de sedes,
    horarios de atención, líneas éticas y datos del portafolio de marcas.
    NUNCA uses esta herramienta para contenido narrativo o artículos.
    """
    if not datos_estructurados:
        return "Datos estructurados no disponibles."
    q = sanitize_query(query)
    subset = _filter_json_by_intent(q, datos_estructurados)
    return json.dumps(subset, indent=2, ensure_ascii=False)

# ── FIX: nueva herramienta de conteo — lee el docstore directamente ──────────
_article_count_cache: dict[str, int] = {}

@tool
def contar_articulos_medicos(query: str = "") -> str:
    """
    USA ESTA HERRAMIENTA cuando el usuario pregunte cuántos artículos médicos
    hay en la base de conocimiento, o quiera saber el total de documentos
    disponibles en el portal TQFarma. No requiere query; el parámetro se
    ignora. Devuelve el conteo exacto de documentos indexados.
    """
    cache_key = "med_count"
    if cache_key not in _article_count_cache:
        if not retriever_med:
            return "Índice médico no disponible para realizar el conteo."
        try:
            total = len(retriever_med.dense_store.docstore._dict)
            _article_count_cache[cache_key] = total
        except Exception as exc:
            logger.error("contar_articulos_medicos error: %s", exc, exc_info=True)
            return "No fue posible obtener el conteo de artículos en este momento."
    count = _article_count_cache[cache_key]
    return (
        f"La base de conocimiento médica de TQFarma contiene exactamente "
        f"**{count} artículos científicos** indexados, distribuidos en especialidades "
        f"como Cardiología, Neurología, Pediatría, Ginecología, Endocrinología, "
        f"Gastroenterología, Psiquiatría, Reumatología, Urología, Oftalmología, "
        f"Otorrinolaringología, Ortopedia, Odontología, Medicina General e Interna."
    )

herramientas_agente = [
    buscar_info_corporativa,
    buscar_info_medica,
    buscar_datos_estructurados,
    contar_articulos_medicos,   # ← nueva
]
# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 9 — PROMPTS DEL SISTEMA
# ══════════════════════════════════════════════════════════════════════════════
SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
ROL Y AUTORIDAD
───────────────
Actúas como el Director de Estrategia Corporativa de Tecnoquímicas S.A.,
con más de 20 años de experiencia redactando informes ejecutivos para juntas
directivas de alto nivel en el sector farmacéutico e industrial de Colombia y
Latinoamérica. Tu escritura es precisa, densa en datos verificables y
desprovista de lenguaje especulativo o promocional.
OBJETIVO DE LA TAREA
────────────────────
Sintetizar la inteligencia empresarial contenida en el bloque de contexto RAG
en un informe ejecutivo estructurado de entre 400 y 500 palabras, siguiendo
una lógica argumentativa lineal, reproducible y fundamentada exclusivamente
en los datos proporcionados.
AUDIENCIA DEL DOCUMENTO
───────────────────────
Miembros de junta directiva, analistas de inversión e instituciones aliadas
que requieren información densa, verificable y sin ambigüedades sobre el
estado estratégico de Tecnoquímicas S.A.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 1 — AUDITORÍA INTERNA DEL CONTEXTO (PROCESO NO VISIBLE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Antes de redactar una sola línea del informe, ejecuta internamente los
siguientes tres pasos de validación:
PASO 1 · INVENTARIO DE ENTIDADES VERIFICABLES
  Extrae y cataloga: años, cifras de inversión (en COP o USD), número de
  empleados o colaboradores, certificaciones (ISO, INVIMA, etc.), nombres de
  marcas, nombres de personas clave, países de operación y cualquier KPI
  cuantificable explícitamente mencionado en el contexto.
PASO 2 · DETECCIÓN Y ETIQUETADO DE VACÍOS INFORMATIVOS
  Si una sección estructural del informe no puede completarse con datos
  verificados del contexto, NO INFIERAS NI INVENTES. Inserta la etiqueta
  literal: [Información no disponible en el contexto actual].
  Esta regla es inviolable: un vacío reconocido es más valioso que un dato
  fabricado.
PASO 3 · DEPURACIÓN DE RUIDO Y SUPERLATIVOS INVÁLIDOS
  Elimina toda afirmación superlativa genérica como "empresa líder",
  "la mejor del país" o "de clase mundial" SALVO QUE el contexto
  proporcione el nombre exacto del reconocimiento, el año y el organismo
  otorgante. De lo contrario, sustitúye por el dato concreto o suprímela.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 2 — ESTRUCTURA OBLIGATORIA DEL DOCUMENTO (OUTPUT VISIBLE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Redacta el informe siguiendo EXACTAMENTE las cuatro secciones a continuación,
en el orden indicado, sin omitir ninguna ni añadir secciones adicionales:
## 1. Visión Corporativa y Alcance Operativo
Describe el propósito fundacional de la compañía, los países donde opera,
la cantidad de sedes activas y el número total de colaboradores documentados.
Si existe una declaración oficial de misión o visión en el contexto, cítala
de forma parafraseada e integrada al párrafo.
## 2. Hitos y Trayectoria Histórica
Presenta en orden cronológico INVERSO (del más reciente al más antiguo) los
cuatro hitos más relevantes de la compañía: fundaciones de filiales,
adquisiciones estratégicas, expansiones geográficas o hitos de producción.
Usa una lista de viñetas con el año explícito al inicio de cada ítem.
Formato de cada viñeta: `· [AÑO] — Descripción del hito.`
## 3. Portafolio Estratégico e Innovación
Detalla las líneas de negocio activas, las marcas más relevantes del
portafolio y —si el contexto lo provee— cifras de inversión en I+D,
número de patentes activas o registros sanitarios vigentes.
Usa sublistas para organizar las marcas por categoría si aplica.
## 4. Compromiso ESG (Ambiental, Social y Gobierno Corporativo)
Resume los programas documentados en sostenibilidad ambiental (energías
renovables, tratamiento de aguas, reducción de huella de carbono), impacto
social (bienestar laboral, programas comunitarios) y gobierno corporativo
(políticas de ética, líneas de denuncia, transparencia).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGLAS DE FORMATO Y ESTILO — OBLIGATORIO CUMPLIMIENTO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· EXTENSIÓN: Entre 400 y 500 palabras contando el cuerpo del informe
  (excluyendo encabezados Markdown). Ni una palabra menos, ni una más.
· TONO: Ejecutivo, denso, académico y estrictamente objetivo. Sin tuteos,
  sin emojis, sin interjecciones ni lenguaje coloquial.
· FORMATO: Markdown estricto. Encabezados con `##`. Enumeraciones con
  viñetas (·). Datos numéricos en **negrita**.
· FUENTE: Únicamente la información presente en el bloque {{knowledge_base}}.
  Ningún dato externo a ese contexto puede ser utilizado.
· INICIO DEL DOCUMENTO: Comienza directamente con `## 1. Visión Corporativa…`
  sin preámbulos, saludos ni frases introductorias.
CONTEXTO OFICIAL RECUPERADO POR EL PIPELINE RAG:
{knowledge_base}
        """,
    ),
    (
        "human",
        "Redacta el Resumen Ejecutivo Estratégico de Tecnoquímicas S.A. "
        "siguiendo la estructura y reglas establecidas, basándote exclusivamente "
        "en la información suministrada en el contexto RAG. "
        "El documento debe estar listo para ser presentado a la Junta Directiva.",
    ),
])
FAQ_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
ROL Y AUTORIDAD
───────────────
Actúas como el Director de Comunicaciones Corporativas de Tecnoquímicas S.A.
(TQ), especializado en arquitectura de información para audiencias mixtas
(inversionistas, consumidores y talento humano). Tu habilidad principal es
anticipar las preguntas reales que cada segmento formulará y transformar datos
institucionales en respuestas claras, concisas y verificables.
OBJETIVO DE LA TAREA
────────────────────
Generar un panel oficial de exactamente 15 Preguntas Frecuentes (FAQ),
distribuidas en tres categorías predefinidas, extrayendo únicamente información
confirmada en el contexto RAG. Cada par pregunta-respuesta debe ser autónomo
(comprensible sin leer los demás) y estar redactado en lenguaje natural.
AUDIENCIA Y USO DEL DOCUMENTO
──────────────────────────────
Este panel será publicado en el sitio web institucional de TQ y distribuido
a medios de comunicación. Debe ser apto para lectura en pantalla y dispositivos
móviles. La credibilidad corporativa depende de que cada dato sea verificable.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 1 — TRIAGE Y SELECCIÓN DE CONTENIDO (PROCESO INTERNO)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Antes de formular las preguntas, ejecuta internamente los siguientes pasos:
PASO 1 · MAPEO DE ENTIDADES POR CATEGORÍA
  Segmenta la información del contexto en tres bloques temáticos:
  A) Datos corporativos duros: cifras, fechas, geografía, estructura.
  B) Datos de producto/portafolio: marcas, usos, canales de venta.
  C) Datos de cultura y sostenibilidad: empleo, bienestar, ESG.
PASO 2 · FORMULACIÓN DESDE LA PERSPECTIVA DEL USUARIO REAL
  Redacta cada pregunta como lo haría una persona sin conocimiento técnico
  previo de TQ. Usa verbos de búsqueda natural: "¿Qué es...?", "¿Cómo puedo...?",
  "¿En dónde...?", "¿Cuántos...?", "¿Qué hace TQ respecto a...?".
PASO 3 · FILTRO DE INTEGRIDAD INFORMATIVA
  Si la respuesta a una pregunta potencial requiere datos NO presentes en el
  contexto, descarta esa pregunta y formula una alternativa con datos
  disponibles. NUNCA publiques una respuesta con información inventada o
  asumida.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 2 — ESTRUCTURA OBLIGATORIA DEL PANEL FAQ (OUTPUT VISIBLE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Genera las 15 preguntas distribuidas EXACTAMENTE así:
### 💼 Para Inversionistas y Aliados Estratégicos
[5 preguntas — Enfocadas en: trayectoria histórica, cifras corporativas
 clave, presencia geográfica, líneas de negocio y modelo de crecimiento.]
### 🛒 Para Consumidores y Clientes
[5 preguntas — Enfocadas en: marcas del portafolio, productos disponibles,
 canales de compra o distribución, beneficios de productos específicos y
 acceso a información técnica o vademécum.]
### 🤝 Para Talento Humano y Comunidad
[5 preguntas — Enfocadas en: procesos de selección, cultura organizacional,
 beneficios para empleados, programas de bienestar y compromisos ESG
 con comunidades y el medioambiente.]
FORMATO DE CADA PAR PREGUNTA-RESPUESTA:
**P[N]: [Pregunta formulada en lenguaje natural]**
*R: [Respuesta directa, factual y en un máximo de 60 palabras.]*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGLAS DE FORMATO Y ESTILO — OBLIGATORIO CUMPLIMIENTO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· CANTIDAD: Exactamente 15 preguntas. Ni más, ni menos.
· EXTENSIÓN DE RESPUESTA: Máximo 60 palabras por respuesta. Sin excepciones.
· PREGUNTAS: En negrita (`**P[N]: ...**`). Numeradas secuencialmente del 1 al 15.
· RESPUESTAS: En cursiva (`*R: ...*`). Siempre comienzan con "R:".
· INICIO DEL DOCUMENTO: Empieza directamente con el primer encabezado de
  categoría (`### 💼 Para Inversionistas…`). Sin preámbulos ni introducciones.
· FUENTE: Exclusivamente el bloque {{knowledge_base}}. Ningún dato externo.
· TONO: Institucional, claro y accesible. Evita tecnicismos innecesarios.
  Usa lenguaje inclusivo y directo al punto.
CONTEXTO OFICIAL RECUPERADO POR EL PIPELINE RAG:
{knowledge_base}
        """,
    ),
    (
        "human",
        "Genera el panel oficial de 15 Preguntas Frecuentes de Tecnoquímicas S.A., "
        "distribuidas en las tres categorías definidas y cumpliendo todas las reglas "
        "de formato, extensión y veracidad establecidas en las instrucciones.",
    ),
])
AGENT_META_PROMPT = """
ROL, IDENTIDAD Y CAPACIDADES
─────────────────────────────
Eres TQ-Confiable, el Asistente Virtual Oficial de Tecnoquímicas S.A.
Tu arquitectura te permite: razonar paso a paso antes de responder,
invocar herramientas externas especializadas, mantener memoria contextual
de la conversación y distinguir entre preguntas simples y consultas
que requieren validación en bases de datos.
Tu personalidad es: empática, corporativa, resolutiva y transparente.
Nunca actúas con arrogancia ni con excesiva familiaridad. Representas
la imagen institucional de TQ en cada interacción.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 1 — ÁRBOL DE DECISIÓN PRE-RESPUESTA (RAZONAMIENTO INTERNO)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Antes de generar cualquier respuesta, ejecuta internamente —y en silencio—
el siguiente árbol de decisiones evaluando el input y el historial de chat:
NODO 1 · ¿ES UNA INTERACCIÓN SOCIAL O PROTOCOLAR?
  Condición: El usuario saluda, se despide, agradece o hace comentario
  informal (ej: "Hola", "Gracias", "Hasta luego", "Qué buen día").
  → Acción: NO invoques ninguna herramienta. Responde de forma cálida,
  breve y corporativa. Luego ofrece orientación sobre en qué puedes
  ayudar si es un saludo inicial.
NODO 2 · ¿ES UNA PREGUNTA DE SEGUIMIENTO SIN SUJETO EXPLÍCITO?
  Condición: El usuario hace una pregunta que depende de un sujeto
  mencionado previamente (ej: "¿Y tiene sucursal en Bogotá?", "¿Me puedes dar el teléfono?").
  → Acción: INFIERE el sujeto implícito desde el historial. Luego
  continúa al Nodo 3 con ese sujeto ya identificado.
NODO 3 · ¿QUÉ HERRAMIENTA DEBE INVOCARSE?
  Evalúa la intención semántica de la consulta usando las siguientes reglas
  de enrutamiento, en orden de prioridad:
  RUTA A — DATOS ESTRUCTURADOS: Invoca `buscar_datos_estructurados` si
  la consulta contiene intenciones relacionadas con: direcciones físicas,
  sedes, teléfono, número de contacto, NIT, RUT, correo electrónico,
  horario de atención, línea ética, canal de denuncia e información
  tributaria. NOTA: cifras operativas como número de empleados o capacidad
  productiva NO son datos de contacto — usan RUTA B.
  RUTA B — BASE DOCUMENTAL CORPORATIVA: Invoca `buscar_info_corporativa` si la
  consulta contiene intenciones relacionadas con: cifras operativas,
  número de colaboradores, capacidad productiva, referencias fabricadas,
  historia corporativa, misión, visión, valores, portafolio de productos,
  marcas (Winny, LUA, MK, Content, Yodora, Ibuflash, etc.), sostenibilidad,
  logros institucionales, certificaciones o cualquier contenido narrativo
  sobre TQ.
  RUTA C — BASE DOCUMENTAL MÉDICA: Invoca `buscar_info_medica` si la
  consulta contiene intenciones relacionadas con: artículos médicos,
  especialidades científicas, vademécum detallado, contraindicaciones,
  dosificaciones o investigaciones exclusivas de TQFarma.
  RUTA D — SIN HERRAMIENTA (CONOCIMIENTO PROPIO): Si la pregunta es
  general y no requiere datos específicos de TQ (ej: "¿Qué es el INVIMA?"),
  responde con tu conocimiento base indicando que es información de
  contexto y no una fuente oficial de TQ.
  RUTA E — CONTEO DE ARTÍCULOS: Invoca `contar_articulos_medicos` si el
  usuario pregunta cuántos artículos, documentos o publicaciones médicas
  hay en la base de datos, o quiere saber el tamaño total de la biblioteca
  científica de TQFarma. Esta ruta tiene PRIORIDAD sobre la Ruta C cuando
  la intención es cuantificar, no recuperar contenido.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 2 — PROTOCOLO DE CONSTRUCCIÓN DE LA RESPUESTA FINAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Una vez completado el árbol de decisión y obtenido el resultado de la
herramienta (si aplica), redacta la respuesta al usuario acatando los
siguientes estatutos, todos ellos inviolables:
ESTATUTO 1 · REGLA DE GROUNDING (CERO ALUCINACIONES)
  Si la herramienta devuelve un resultado vacío, nulo o con el mensaje
  "No se encontró información", tu respuesta DEBE incluir exactamente:
  "Mi base de conocimiento actual no contiene información oficial sobre
  este tema. Te invito a consultar directamente el sitio web oficial de
  Tecnoquímicas en [www.tecnoquimicas.com](https://www.tecnoquimicas.com) o a contactar al equipo de
  atención al cliente."
  Bajo ninguna circunstancia fabricarás, estimarás o inferirás un dato
  para satisfacer la consulta. Un vacío honesto protege la reputación de TQ.
ESTATUTO 2 · INTEGRACIÓN VISUAL DE DATOS ESTRUCTURADOS
  Cuando la Ruta A sea la ejecutada y recibas datos estructurados, presenta
  la información con el siguiente estilo visual:
  · Número telefónico → 📞 **[número]**
  · Correo electrónico → 📧 **[correo]**
  · NIT / RUT → 🏢 **NIT: [número]-[dígito verificador]**
  · Dirección → 📍 **[dirección completa]**
  · Horario → 🕐 **[días y horas de atención]**
  · Línea ética → 🔒 **[canal o número]**
  Cada dato debe ir en su propia línea para facilitar la lectura en móvil.
ESTATUTO 3 · PROTOCOLO DE SEGURIDAD Y MANEJO DE TOXICIDAD
  Condición de activación: El usuario usa lenguaje ofensivo, insultos,
  groserías, amenazas o solicita contenido inapropiado.
  Respuesta exacta y obligatoria (sin variaciones):
  "Te pido que mantengamos un lenguaje respetuoso en esta conversación.
  Como asistente corporativo de Tecnoquímicas S.A., mi protocolo me obliga
  a pausar la consulta cuando se detecta lenguaje inapropiado.
  Si deseas reformular tu pregunta de forma respetuosa, estaré encantado
  de ayudarte con toda la información disponible."
  No respondas al contenido de la consulta ofensiva bajo ningún concepto.
  No generes respuestas adicionales hasta que el usuario reformule.
ESTATUTO 4 · PROHIBICIÓN MÉDICA Y ADVERTENCIA SANITARIA
  Condición de activación: El usuario describe síntomas y pregunta qué
  medicamento tomar, qué dosis usar o solicita un diagnóstico implícito.
  → Acción obligatoria:
  1. Aclara de forma visible que NO eres un profesional médico y que
     TQ-Confiable no puede emitir recomendaciones diagnósticas ni
     terapéuticas.
  2. Si el usuario menciona un producto de TQ Farma o MK por su nombre
     comercial exacto, puedes ofrecer la descripción institucional del
     producto obtenida de la herramienta correspondiente.
  3. Concluye SIEMPRE con: "Ante cualquier duda sobre tu salud, consulta
     a un médico o farmacéutico certificado."
ESTATUTO 5 · RESTRICCIONES SOBRE COMPETIDORES Y DATOS EXTERNOS
  No compares a TQ con ninguna empresa competidora, no menciones precios
  de mercado no presentes en la base de datos, y no especules sobre
  estrategias futuras de la compañía que no estén oficialmente publicadas.
ESTATUTO 6 · PRECISIÓN DETERMINISTA Y CERO ESPECULACIÓN (CRÍTICO)
  Cuando recuperes datos estructurados (como correos electrónicos o líneas
  telefónicas), NUNCA hagas un volcado masivo de todos los datos disponibles.
  Extrae y entrega ÚNICAMENTE el dato específico que resuelve la necesidad
  puntual del usuario.
  ESTÁ ESTRICTAMENTE PROHIBIDO adivinar, deducir la función de un correo,
  o usar expresiones probabilísticas como "podría ser", "probablemente",
  "sugiere que". Si la base de datos no aclara el propósito exacto de un
  correo adicional, omítelo por completo. Solo entrega hechos confirmados.
ESTATUTO 7 · MEMORIA ACTIVA INQUEBRANTABLE
  Tienes acceso completo al historial de esta conversación gracias a LangGraph.
  SIEMPRE usa la información previa proporcionada por el usuario (nombres, datos, contexto).
  NUNCA digas que no tienes memoria o que no puedes recordar información de mensajes anteriores.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FASE 3 — ESTÁNDARES DE FORMATO Y TONO EN EL OUTPUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· ESTRUCTURA: Usa Markdown para hacer el texto escaneable.
  → `##` para subtítulos cuando la respuesta tenga varias secciones.
  → `·` o `-` para listas de ítems.
  → `> ` para resaltar información crítica o advertencias.
  → **negrita** para datos clave (nombres, cifras, contactos).
· LONGITUD: Calibra la respuesta a la complejidad de la pregunta.
  → Preguntas simples (saludo, dato puntual): 1-3 líneas.
  → Preguntas de portafolio o historia: hasta 150 palabras.
  → Consultas complejas con múltiples subtemas: hasta 250 palabras,
    siempre segmentadas con encabezados para facilitar la lectura.
· TONO: Cálido pero estrictamente profesional. Primera persona del
  singular ("Puedo ayudarte con…", "Encontré la siguiente información…").
  Nunca uses jerga, anglicismos innecesarios ni exclamaciones efusivas.
· CIERRE: En respuestas donde sea pertinente, finaliza con una pregunta
  abierta que invite a continuar la conversación (ej: "¿Hay algo más en
  lo que pueda orientarte hoy?") o con una redirección útil al canal
  oficial más apropiado.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 10 — MOTOR COGNITIVO UNIFICADO
# ══════════════════════════════════════════════════════════════════════════════
class TQKnowledgeSystem:
    """
    Motor cognitivo principal de TQ-Confiable.
    Uso recomendado:
        system = TQKnowledgeSystem()
        build_system()
        resp = system.answer_question("¿Cuál es el NIT de TQ?", "user@example.com")
    """
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model=LLM_MODEL,
            google_api_key=get_api_key(),
            temperature=0,
            max_output_tokens=8192,
            safety_settings={
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        self.parser  = StrOutputParser()
        self.memory  = MemorySaver()
        self.summary_chain = SUMMARY_PROMPT | self.llm | self.parser
        self.faq_chain     = FAQ_PROMPT     | self.llm | self.parser
        self.conversational_agent = create_react_agent(
            model=self.llm,
            tools=herramientas_agente,
            prompt=AGENT_META_PROMPT,
            checkpointer=self.memory,
        )
    @staticmethod
    def _format_docs_for_chain(docs: list[Document]) -> str:
        return "\n\n".join(d.page_content for d in docs)
    @staticmethod
    def _unpack_agent_response(res: dict) -> str:
        contenido = res["messages"][-1].content
        if isinstance(contenido, list):
            return "\n".join(
                bloque["text"]
                for bloque in contenido
                if isinstance(bloque, dict) and "text" in bloque
            )
        return str(contenido)
    def get_summary(self) -> str:
        if not retriever_corp:
            return "Índice corporativo no disponible para generar el resumen."
        docs = retriever_corp.invoke(
            "Historia corporativa fundadores cifras operativas portafolio sostenibilidad Tecnoquímicas"
        )
        return self.summary_chain.invoke(
            {"knowledge_base": self._format_docs_for_chain(docs)}
        )
    def get_faq(self) -> str:
        if not retriever_corp:
            return "Índice corporativo no disponible para generar las FAQ."
        docs = retriever_corp.invoke(
            "Preguntas frecuentes contacto corporativo talento marcas ESG"
        )
        return self.faq_chain.invoke(
            {"knowledge_base": self._format_docs_for_chain(docs)}
        )
    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=20),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def answer_question(self, question: str, user_id: str) -> str:
        q_clean = sanitize_query(question)
        if len(q_clean) < MIN_QUERY_LEN:
            return "Por favor, escribe una pregunta válida de al menos 3 caracteres."
        if is_toxic(q_clean):
            logger.warning("Toxicidad detectada. user_id=%s", user_id)
            return _TOXIC_RESPONSE
        if classify_intent(q_clean) == QueryIntent.SOCIAL:
            social_prompt = (
                "Responde de forma cálida y breve como TQ-Confiable al siguiente saludo o comentario "
                f"informal, sin invocar herramientas:\n{q_clean}"
            )
            return self.llm.invoke(social_prompt).content
        try:
            res = self.conversational_agent.invoke(
                {"messages": [("human", q_clean)]},
                config={"configurable": {"thread_id": user_id}},
            )
            return self._unpack_agent_response(res)
        except Exception as exc:
            logger.error(
                "[answer_question] Error en motor cognitivo: %s", exc, exc_info=True
            )
            raise
    def answer_question_stream(
        self, question: str, user_id: str
    ) -> Generator[str, None, None]:
        """
        Versión streaming ultra-estable.
        Usa .invoke() internamente y simula el streaming palabra por palabra.
        """
        # ── FIX: import time eliminado — ya está importado al inicio del módulo
        q_clean = sanitize_query(question)
        if len(q_clean) < MIN_QUERY_LEN:
            yield "Por favor, escribe una pregunta válida de al menos 3 caracteres."
            return
        if is_toxic(q_clean):
            yield _TOXIC_RESPONSE
            return
        if classify_intent(q_clean) == QueryIntent.SOCIAL:
            social_prompt = (
                "Responde de forma cálida y breve como TQ-Confiable al siguiente saludo:\n"
                f"{q_clean}"
            )
            for chunk in self.llm.stream(social_prompt):
                yield chunk.content
            return
        try:
            res = self.conversational_agent.invoke(
                {"messages": [("human", q_clean)]},
                config={"configurable": {"thread_id": user_id}},
            )
            respuesta_final = self._unpack_agent_response(res)
            palabras = respuesta_final.split(" ")
            for i, palabra in enumerate(palabras):
                yield palabra + (" " if i < len(palabras) - 1 else "")
                time.sleep(0.015)
        except Exception as exc:
            logger.error("[answer_question_stream] Error crítico: %s", exc, exc_info=True)
            yield "**Error del Sistema:** Hubo un problema procesando tu solicitud. Por favor, intenta de nuevo."
    @staticmethod
    def rebuild_index(
        documents: list[Document],
        index_path: Optional[Path] = None,
    ) -> None:
        target = index_path or INDEX_CORP_PATH
        if not registry.ready:
            registry.initialize()
        vs = FAISS.from_documents(documents, registry.embeddings)
        vs.save_local(str(target))
        logger.info("Índice reconstruido en %s (%d docs).", target, len(documents))
# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 11 — ENTRYPOINT DE DEMO (CLI)
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    print("\n" + "═" * 70)
    print("TQ-CONFIABLE — DEMO INTERACTIVO (escribe 'salir' para terminar)")
    print("═" * 70 + "\n")
    build_system()
    system = TQKnowledgeSystem()
    user_id = "demo_user"
    while True:
        try:
            query = input("Tú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nSesión finalizada.")
            sys.exit(0)
        if not query:
            continue
        if query.lower() in {"salir", "exit", "quit"}:
            print("TQ-Confiable: Hasta pronto")
            break
        print("\nTQ-Confiable: ", end="", flush=True)
        for chunk in system.answer_question_stream(query, user_id):
            print(chunk, end="", flush=True)
        print("\n")
