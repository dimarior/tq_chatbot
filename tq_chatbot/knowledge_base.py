
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

try:
    import ftfy
    HAS_FTFY = True
except ImportError:
    HAS_FTFY = False

# ══════════════════════════════════════════════════════════════════════════════
# 0. RUTAS BASE
# ══════════════════════════════════════════════════════════════════════════════
BASE_DIR = Path(r"C:\Users\danie\Desktop\TAIA")
BASE_DIR.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# 1. LOGGING
# ══════════════════════════════════════════════════════════════════════════════
def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("kb_pipeline")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    fh = logging.FileHandler(BASE_DIR / "pipeline.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger

log = _setup_logging()

# ══════════════════════════════════════════════════════════════════════════════
# 2. CONFIGURACION
# ══════════════════════════════════════════════════════════════════════════════
CFG: dict = {
    "pipeline": {
        "chunk_size": 800,
        "chunk_overlap": 100,
        "boilerplate_threshold": 0.25,
        "min_chunk_length": 80,
        "quality_min_score": 0.30,
    },
    "quality_weights": {
        "density": 0.40,
        "length": 0.35,
        "structure_header_bonus": 0.15,
        "structure_list_bonus": 0.10,
        "url_penalty_per_url": 0.07,
        "url_penalty_max": 0.30,
    },
    "llm": {
        "model": "gemini-2.5-flash",
        "temperature": 0,
        "max_retries": 4,
        "retry_wait_min": 2,
        "retry_wait_max": 30,
    },
    "embeddings": {
        "model_name": "intfloat/multilingual-e5-large",
        "device": "cpu",
        "normalize": True,
    },
    "domain": {
        "brands": [
            "MK", "Winny", "Content", "Sal de Frutas LUA", "Bonfiest", "Noraver",
            "Gastrofast", "Crema No. 4", "Ibuflash", "Duraflex", "Hidraplus",
            "CureBand", "Yodora", "Bactrovet", "Procef", "Oxitecina", "Yocare",
        ],
        "medical_specialties": [
            "cardiologia", "endocrinologia", "gastroenterologia", "ginecologia",
            "medicina-general", "medicina-interna", "neurologia", "odontologia",
            "oftalmologia", "otorrinolaringologia", "ortopedia", "pediatria",
            "psiquiatria", "reumatologia", "urologia",
        ],
        "countries": [
            "Colombia", "Ecuador", "El Salvador", "Guatemala", "Honduras",
            "Nicaragua", "Panama", "Costa Rica", "Republica Dominicana", "Peru",
        ],
        "cities": [
            "Cali", "Bogota", "Medellin", "Barranquilla", "Cartagena",
            "Quito", "Guayaquil", "San Salvador", "Ciudad de Guatemala",
        ],
    },
}

# Atajos a secciones usadas frecuentemente
_PIPE   = CFG["pipeline"]
_QW     = CFG["quality_weights"]
_LLM    = CFG["llm"]
_EMB    = CFG["embeddings"]
_DOMAIN = CFG["domain"]

CHUNK_SIZE            = _PIPE["chunk_size"]
CHUNK_OVERLAP         = _PIPE["chunk_overlap"]
BOILERPLATE_THRESHOLD = _PIPE["boilerplate_threshold"]
MIN_CHUNK_LENGTH      = _PIPE["min_chunk_length"]
QUALITY_MIN_SCORE     = _PIPE["quality_min_score"]

TQ_BRANDS           = set(_DOMAIN["brands"])
MEDICAL_SPECIALTIES = set(_DOMAIN["medical_specialties"])
GEO_WHITELIST       = set(_DOMAIN["countries"] + _DOMAIN["cities"])

# Mapa slug -> nombre legible
_SPECIALTY_DISPLAY: dict[str, str] = {
    spec: spec.replace("-", " ").title()
    for spec in MEDICAL_SPECIALTIES
}

# ── Ruido y navegacion ────────────────────────────────────────────────────────
EXACT_NOISE: set[str] = {
    "Nacionalidad", "Nombre", "Apellidos", "Correo Electronico", "Telefono",
    "ACEPTAR", "Ingresar", "Cerrar", "Enviar", "Aceptar", "Volver",
    "Comparte en:", "ACCEDER",
}

NOISE_PHRASES: list[str] = [
    "Usted esta siendo redirigido", "sitio web externo y ajeno",
    "Si desea continuar, haga clic", "Bienvenido al Chat",
    "Tipo de identificacion", "Cedula de", "Carnet diplomatico",
    "ID extranjero", "Fideicomiso", "Registro civil", "Tarjeta de identidad",
    "Acepto los Terminos", "var metaTag", "return metaTag", "No description found",
    "Registrese al portal", "Y acceda a contenido exclusivo",
    "Bienvenido al Portal Farmaceutico", "Esta informacion es exclusiva",
    "Certifico que soy medico", "Su mensaje se ha enviado satisfactoriamente",
    "Recomiende esta noticia", "Account/Login", "regresar=%2F",
]

NAV_LINK_WORDS: set[str] = {
    "Siguenos", "LinkedIn", "Instagram", "Facebook", "Youtube", "Twitter",
    "Colaborador TQ", "Portal Medicos", "Encuentranos", "Gobierno Corporativo",
    "Asi Cambiamos El Mundo", "Trabaja con Nosotros", "Nuestras Marcas",
    "Noticias", "Contacto", "Inicio", "Terminos y condiciones",
    "Politicas de privacidad", "Todos los derechos reservados",
    "INICIAR SESION", "REGISTRARSE", "Acceso a Journals", "VER TODAS",
    "VER MAS", "Anterior", "Siguiente",
    "Cardiologia", "Endocrinologia", "Gastroenterologia", "Ginecologia",
    "Medicina General", "Medicina Interna", "Neurologia", "Odontologia",
    "Oftalmologia", "Otorrinolaringologia", "Ortopedia", "Pediatria",
    "Psiquiatria", "Reumatologia", "Urologia",
    "Quienes somos?", "Nuestro proposito", "Mision", "Vision",
    "Credo", "Historia",
}

CATEGORY_MAP: dict[tuple, str] = {
    ("mision", "vision", "credo", "proposito", "quien", "historia"): "quienes_somos",
    ("producto", "marca", "linea", "catalogo", "referencia"):        "productos",
    ("contacto", "sede", "encuentranos", "oficina", "atencion"):     "contacto",
    ("sostenibilidad", "responsabilidad", "ambiental", "social"):    "sostenibilidad",
    ("noticia", "blog", "prensa", "comunicado"):                     "noticias",
    ("trabaj", "empleo", "vacante", "seleccion"):                    "empleo",
}

LLM_SECTION_KEYWORDS = {"encuentranos", "contacto", "sedes", "sucursales"}

CACHE_DIR = BASE_DIR / ".llm_cache"
CACHE_DIR.mkdir(exist_ok=True)

TQFARMA_BASE_URL = "https://www.tqfarma.com"

_RE_MED_TITLE   = re.compile(
    r'^#\s+\[([^\]]+)\]\((/detalle-actualizacion-medica/[^\)]+)\)', re.M
)
_RE_MED_PREVIEW = re.compile(
    r'\n([A-ZAEIOUÑ][^\n]{80,}?\.\.\.)\n'
)
_RE_MED_DATE    = re.compile(r'(\d{2}/\d{2}/\d{4})')
_RE_MED_SPEC    = re.compile(
    r'### (Cardiologia|Endocrinologia|Gastroenterologia|Ginecologia|'
    r'Medicina General|Medicina Interna|Neurologia|Odontologia|'
    r'Oftalmologia|Otorrinolaringologia|Ortopedia|Pediatria|'
    r'Psiquiatria|Reumatologia|Urologia)\n'
)

# ══════════════════════════════════════════════════════════════════════════════
# 3. API KEY
# ══════════════════════════════════════════════════════════════════════════════
load_dotenv()

def get_api_key() -> str:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise EnvironmentError("Falta GOOGLE_API_KEY en tu archivo .env")
    return key

# ══════════════════════════════════════════════════════════════════════════════
# 4. BOILERPLATE AUTO-DETECTOR
# ══════════════════════════════════════════════════════════════════════════════
def build_boilerplate_index(raw_data: dict) -> set[str]:
    _print_step("Construyendo indice de boilerplate estadistico")
    line_freq: Counter = Counter()
    total = len(raw_data)

    for content in raw_data.values():
        seen: set[str] = set()
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if len(line) > 3 and line not in seen:
                line_freq[line] += 1
                seen.add(line)

    boilerplate = {
        line for line, count in line_freq.items()
        if count / total > BOILERPLATE_THRESHOLD
    }
    log.info("Boilerplate: %d patrones detectados.", len(boilerplate))
    return boilerplate

# ══════════════════════════════════════════════════════════════════════════════
# 5. EXTRACTOR DE ARTICULOS MEDICOS TRUNCADOS
# ══════════════════════════════════════════════════════════════════════════════
def _specialty_from_url(rel_path: str) -> str:
    """
    Extrae la especialidad directamente desde el path de la URL del articulo.
    Ejemplo: /detalle-actualizacion-medica/cardiologia/nombre → 'Cardiologia'
    Es la fuente de verdad: mas fiable que buscar un header en el texto scrapeado.
    """
    for spec in MEDICAL_SPECIALTIES:
        if f"/detalle-actualizacion-medica/{spec}/" in rel_path:
            return _SPECIALTY_DISPLAY[spec]
    return ""

def extract_medical_previews(raw_data: dict) -> list[dict]:
    """
    Procesa secciones medicas truncadas por el muro de login de tqfarma.com.

    De cada articulo extrae:
      - titulo limpio
      - preview visible antes del VER MAS
      - URL completa al articulo en tqfarma.com
      - especialidad medica (desde URL, con fallback a regex de texto)
      - fecha de publicacion

    Produce chunks de tipo preview_truncado que permiten al asistente:
      1. Confirmar que el articulo existe.
      2. Dar un resumen minimo del contenido disponible.
      3. Enviar al usuario al portal con la URL directa, indicando que
         debe iniciar sesion como medico u odontologo para leer completo.
    """
    _print_step("Extraccion de Previews de Articulos Medicos")

    previews: list[dict] = []
    skipped = 0

    for section_key, content in raw_data.items():
        if "Account/Login" not in content or "/detalle-actualizacion-medica/" not in content:
            continue

        title_m = _RE_MED_TITLE.search(content)
        if not title_m:
            skipped += 1
            log.debug("Preview medico sin titulo detectado: '%s'", section_key)
            continue

        title    = title_m.group(1).strip()
        rel_path = title_m.group(2).strip()
        full_url = f"{TQFARMA_BASE_URL}{rel_path}"

        # Especialidad — fuente principal: URL del articulo
        # Fallback: regex sobre el texto si la URL no trae el segmento de especialidad
        specialty = _specialty_from_url(rel_path)
        if not specialty:
            spec_m    = _RE_MED_SPEC.search(content)
            specialty = spec_m.group(1) if spec_m else "General"
            if specialty == "General":
                log.debug(
                    "Especialidad no detectada por URL ni texto para '%s': asignada 'General'.",
                    section_key,
                )

        prev_m  = _RE_MED_PREVIEW.search(content)
        preview = prev_m.group(1).strip() if prev_m else ""

        date_m = _RE_MED_DATE.search(content)
        date   = date_m.group(1) if date_m else ""

        chunk_text = (
            f"Articulo medico: {title}\n"
            f"Especialidad: {specialty}\n"
        )
        if date:
            chunk_text += f"Fecha de publicacion: {date}\n"
        if preview:
            chunk_text += f"\nResumen disponible:\n{preview}\n"
        chunk_text += (
            f"\nPara leer el articulo completo, ingresa al portal TQFarma "
            f"(requiere inicio de sesion como medico u odontologo):\n{full_url}"
        )

        previews.append({
            "id":   f"med_preview_{section_key}",
            "text": chunk_text,
            "metadata": {
                "section_key":      section_key,
                "content_type":     "articulo_medico",
                "article_type":     "preview_truncado",
                "source":           "tqfarma.com",
                "category":         "biblioteca_cientifica",
                "specialty":        specialty.lower().replace(" ", "_"),
                "title":            title,
                "url":              full_url,
                "publication_date": date,
                "quality_score":    0.85,
                "timestamp":        datetime.now().isoformat(),
            },
        })

    log.info(
        "Previews medicos: %d articulos extraidos, %d secciones sin titulo (omitidas).",
        len(previews), skipped,
    )
    return previews

# ══════════════════════════════════════════════════════════════════════════════
# 6. METADATA PARSER
# ══════════════════════════════════════════════════════════════════════════════
def parse_section_metadata(section_key: str, content: str) -> dict:
    meta: dict = {"section_key": section_key}

    m = re.search(r"=== SECCION: ([A-Z0-9_]+) ===", content)
    if m:
        meta["section_label"] = m.group(1)

    is_farma = (
        "tqfarma.com" in content
        or "/biblioteca-cientifica/" in content
        or "/detalle-actualizacion-medica/" in content
    )
    meta["source"]       = "tqfarma.com" if is_farma else "tqconfiable.com"
    meta["content_type"] = "articulo_medico" if is_farma else "corporativo"

    for spec in MEDICAL_SPECIALTIES:
        if (
            f"/noticias-actualidad/{spec}/" in content
            or f"/detalle-actualizacion-medica/{spec}/" in content
        ):
            meta["specialty"] = spec.replace("-", "_")
            meta["category"]  = "biblioteca_cientifica"
            break

    if "category" not in meta:
        for keywords, cat in CATEGORY_MAP.items():
            if any(kw in section_key for kw in keywords):
                meta["category"] = cat
                break
        else:
            meta["category"] = "general"

    date_m = re.search(r"(\d{2}/\d{2}/\d{4})", content)
    if date_m:
        meta["publication_date"] = date_m.group(1)

    return meta

# ══════════════════════════════════════════════════════════════════════════════
# 7. LIMPIEZA MULTICAPA
# ══════════════════════════════════════════════════════════════════════════════
_RE_FULL_LINK    = re.compile(r'^\[([^\]]+)\]\([^\)]*\)$')
_RE_LINK_IN_LINE = re.compile(r'\[([^\]]+)\]\([^\)]+\)')

def _is_nav_link_line(line: str) -> bool:
    m = _RE_FULL_LINK.match(line.strip())
    if not m:
        return False
    text = m.group(1).strip()
    return text in NAV_LINK_WORDS or len(text) <= 3

def _strip_nav_links_inline(line: str) -> str:
    def replacer(m: re.Match) -> str:
        text = m.group(1).strip()
        if text in NAV_LINK_WORDS or len(text) <= 3:
            return ""
        if len(text) > 30:
            return text
        return m.group(0)
    return _RE_LINK_IN_LINE.sub(replacer, line)

def clean_text(text: str, boilerplate: set[str]) -> str:
    if HAS_FTFY:
        text = ftfy.fix_text(text)
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"=== SECCION: [A-Z0-9_]+ ===\n?", "", text)

    filtered: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line in boilerplate or line in EXACT_NOISE:
            continue
        if any(phrase in line for phrase in NOISE_PHRASES):
            continue
        if line in GEO_WHITELIST:
            filtered.append(line)
            continue
        if _is_nav_link_line(line):
            continue
        if line.startswith("#"):
            filtered.append(line)
            continue
        if line.startswith(("*", "-", "[")):
            cleaned_line = _strip_nav_links_inline(line).strip()
            if cleaned_line:
                filtered.append(cleaned_line)
            continue
        line = _strip_nav_links_inline(line).strip()
        if not line:
            continue
        if len(line) < 4 and not any(c.isdigit() for c in line):
            continue
        filtered.append(line)

    cleaned = "\n".join(filtered)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()

# ══════════════════════════════════════════════════════════════════════════════
# 8. SCORING DE CALIDAD Y DEDUPLICACION
# ══════════════════════════════════════════════════════════════════════════════
def compute_chunk_quality(text: str) -> float:
    """Score entre 0 y 1. Pesos configurables en CFG -> quality_weights."""
    if not text or len(text) < MIN_CHUNK_LENGTH:
        return 0.0

    words = text.split()
    wc, cc = len(words), len(text)

    density = min(wc / max(cc / 5, 1), 1.0)

    if wc < 60:
        length_score = wc / 60
    elif wc <= 180:
        length_score = 1.0
    else:
        length_score = max(1 - (wc - 180) / 400, 0.5)

    has_h    = bool(re.search(r'^#{1,3}\s', text, re.M))
    has_list = bool(re.search(r'^[\*\-]\s', text, re.M))
    struct_bonus = (
        (_QW["structure_header_bonus"] if has_h else 0)
        + (_QW["structure_list_bonus"] if has_list else 0)
    )

    url_count     = len(re.findall(r'https?://', text))
    noise_penalty = min(url_count * _QW["url_penalty_per_url"], _QW["url_penalty_max"])

    score = (
        density        * _QW["density"]
        + length_score * _QW["length"]
        + struct_bonus
        - noise_penalty
    )
    return round(min(max(score, 0.0), 1.0), 3)

def _fingerprint(text: str) -> str:
    return re.sub(r'\s+', ' ', text[:120].lower().strip())

def deduplicate_chunks(chunks: list[dict]) -> list[dict]:
    seen:   set[str]   = set()
    unique: list[dict] = []
    for chunk in chunks:
        fp = _fingerprint(chunk["text"])
        if fp not in seen:
            seen.add(fp)
            unique.append(chunk)
    log.debug("Deduplicacion: %d -> %d chunks unicos.", len(chunks), len(unique))
    return unique

# ══════════════════════════════════════════════════════════════════════════════
# 9A. EXTRACCION DE REGEX
# ══════════════════════════════════════════════════════════════════════════════
_RE_MAIL          = re.compile(r"([a-zA-Z0-9._%+\-]+@(?:tecnoquimicas|tqfarma|tqconfiable|tqgrupo|resguarda)\.com)", re.I)
_RE_NIT           = re.compile(r"\b(\d{3}\.?\d{3}\.?\d{3}-\d)\b")
_RE_HORARIO       = re.compile(r"(Lunes a (?:viernes|s[aá]bado)[^\n]{0,80}(?:\d{1,2}:\d{2}|\d{1,2}\s*(?:am|pm|a\.m\.|p\.m\.)))", re.I)
_RE_COLABORADORES = re.compile(r"(\d[\d\.]*)\.?\d*\s*colaboradores", re.I)
_RE_REFERENCIAS   = re.compile(r"alrededor de\s+([\d\.]+)\s*referencias", re.I)
_RE_SEDES_CO      = re.compile(r"(\w+)\s+sedes productivas en Colombia", re.I)
_RE_SEDES_CA      = re.compile(r"(\w+)\s+en Centroamerica", re.I)
_RE_ANOS_TRAY     = re.compile(r"mas de\s+(\d+)\s+anos", re.I)
_RE_PAISES_EXP    = re.compile(r"mas de\s+(\d+)\s+paises de America", re.I)

def extract_regex_data(raw_data: dict) -> dict:
    """Extrae con regex todo lo que no necesita comprension semantica."""
    _print_step("Extraccion por Regex (datos estructurales)")

    telefonos: set[str] = set()
    correos:   set[str] = set()
    nits:      set[str] = set()
    horarios:  set[str] = set()
    marcas:    set[str] = set()
    cifras:    dict     = {}

    for content in raw_data.values():
        for m in _RE_MAIL.finditer(content):    correos.add(m.group(1).lower())
        for m in _RE_NIT.finditer(content):     nits.add(m.group(1))
        for m in _RE_HORARIO.finditer(content): horarios.add(m.group(1).strip())
        for brand in TQ_BRANDS:
            if brand in content:
                marcas.add(brand)

        if (m := _RE_COLABORADORES.search(content)) and "colaboradores" not in cifras:
            cifras["colaboradores"] = m.group(1).strip()
        if (m := _RE_REFERENCIAS.search(content)) and "referencias_producidas" not in cifras:
            cifras["referencias_producidas"] = m.group(1).strip()
        m_co = _RE_SEDES_CO.search(content)
        m_ca = _RE_SEDES_CA.search(content)
        if m_co and m_ca and "sedes_productivas" not in cifras:
            cifras["sedes_productivas"] = f"{m_co.group(1).capitalize()} en Colombia, una en Centroamerica"
        if (m := _RE_ANOS_TRAY.search(content)) and "anos_trayectoria" not in cifras:
            cifras["anos_trayectoria"] = f"mas de {m.group(1)} anos"
        if (m := _RE_PAISES_EXP.search(content)) and "paises_exportacion" not in cifras:
            cifras["paises_exportacion"] = f"mas de {m.group(1)} paises de America"

    log.info("Regex: %d correos, %d NITs, %d marcas, %d horarios.",
             len(correos), len(nits), len(marcas), len(horarios))

    return {
        "telefonos": sorted(telefonos),
        "correos":   sorted(correos),
        "nits":      sorted(nits),
        "horarios":  sorted(horarios),
        "marcas":    sorted(marcas),
        "cifras":    cifras,
    }

# ══════════════════════════════════════════════════════════════════════════════
# 9B. EXTRACCION LLM (con cache + reintentos)
# ══════════════════════════════════════════════════════════════════════════════
class SedeTQ(BaseModel):
    nombre_sede:      str       = Field(description="Nombre de la sede, planta o regional.")
    ciudad_o_pais:    str       = Field(description="Ciudad o pais. Inferir del contexto si es posible.")
    direccion_exacta: str       = Field(description="Direccion fisica completa.")
    telefonos:        list[str] = Field(default_factory=list, description="Telefonos asociados a esta sede.")

class DirectorioCompleto(BaseModel):
    sedes: list[SedeTQ] = Field(description="Lista exhaustiva de sedes encontradas en el texto.")

def _section_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

def _load_cached_result(section_key: str, content: str) -> DirectorioCompleto | None:
    cache_file = CACHE_DIR / f"{section_key}_{_section_hash(content)}.json"
    if cache_file.exists():
        log.debug("Cache hit para seccion '%s'.", section_key)
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return DirectorioCompleto(**data)
    return None

def _save_cached_result(section_key: str, content: str, result: DirectorioCompleto) -> None:
    cache_file = CACHE_DIR / f"{section_key}_{_section_hash(content)}.json"
    cache_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")

def _build_llm_extractor() -> object:
    llm = ChatGoogleGenerativeAI(
        model=_LLM["model"],
        temperature=_LLM["temperature"],
        google_api_key=get_api_key(),
    )
    return llm.with_structured_output(DirectorioCompleto)

@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(_LLM["max_retries"]),
    wait=wait_exponential(min=_LLM["retry_wait_min"], max=_LLM["retry_wait_max"]),
    reraise=True,
)
def _invoke_llm(extractor, prompt: str) -> DirectorioCompleto:
    return extractor.invoke(prompt)

_PROMPT_TEMPLATE = """
Eres un analista de datos experto. Lee el siguiente texto corporativo de Tecnoquimicas
y extrae TODAS las sedes, regionales, plantas, centros de distribucion y plataformas mencionadas.
Extrae el nombre, la direccion exacta, la ciudad/pais y los telefonos.
Si un campo no esta disponible, usa una cadena vacia.

Texto:
{content}
""".strip()

def extract_llm_sedes(raw_data: dict) -> dict[str, dict]:
    """
    Extrae sedes usando Gemini unicamente en secciones relevantes.
    Usa cache SHA-256 por seccion para evitar llamadas redundantes.
    Reintentos automaticos con backoff exponencial si la API falla.
    """
    _print_step("Extraccion Semantica de Sedes (LLM + Cache + Reintentos)")
    extractor = _build_llm_extractor()
    sedes_perfectas: dict[str, dict] = {}
    failed_sections: list[str] = []

    relevant = {
        k: v for k, v in raw_data.items()
        if any(kw in k.lower() for kw in LLM_SECTION_KEYWORDS)
    }
    log.info("LLM: %d secciones relevantes para analisis de sedes.", len(relevant))

    for section_key, content in relevant.items():
        cached = _load_cached_result(section_key, content)
        if cached:
            resultado = cached
        else:
            prompt = _PROMPT_TEMPLATE.format(content=content)
            try:
                resultado: DirectorioCompleto = _invoke_llm(extractor, prompt)
                _save_cached_result(section_key, content, resultado)
                log.info("LLM: seccion '%s' procesada (%d sedes).", section_key, len(resultado.sedes))
            except Exception as e:
                log.error("LLM: seccion '%s' fallo tras %d intentos. Error: %s",
                          section_key, _LLM["max_retries"], e)
                failed_sections.append(section_key)
                continue

        for sede in resultado.sedes:
            sedes_perfectas[sede.nombre_sede] = {
                "direccion": sede.direccion_exacta,
                "ubicacion": sede.ciudad_o_pais,
                "telefonos": sede.telefonos,
            }

    if failed_sections:
        log.warning("Secciones con error LLM (revisar pipeline.log): %s", failed_sections)
        (BASE_DIR / "llm_failed_sections.json").write_text(
            json.dumps(failed_sections, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return sedes_perfectas

# ══════════════════════════════════════════════════════════════════════════════
# 10. ENSAMBLADO DE DATOS ESTRUCTURADOS
# ══════════════════════════════════════════════════════════════════════════════
def extract_contact_special(raw_data: dict) -> dict:
    """Extrae la informacion especializada de la linea etica y servicio."""
    linea           = raw_data.get("linea_etica", "")
    emails_etica    = re.findall(r"[\w.]+@resguarda\.com", linea)
    tel_wsp         = re.search(r"WhatsApp[^\d+]*(\+[\d\s]+)", linea)
    telefonos_etica = re.findall(r":\s*([\d\-]{6,})", linea)

    return {
        "email":              emails_etica[0] if emails_etica else "",
        "whatsapp":           tel_wsp.group(1).strip() if tel_wsp else "",
        "telefonos_por_pais": telefonos_etica,
        "portal":             "http://www.resguarda.com/lineaeticatq",
    }

def assemble_structured_data(raw_data: dict, regex_data: dict, sedes: dict[str, dict]) -> dict:
    """Une los resultados de regex, LLM e info especial en el JSON estructurado final."""
    _print_step("Ensamblando datos_estructurados.json")

    nit_list = regex_data["nits"]

    all_phones: set[str] = set(regex_data["telefonos"])
    for sede_info in sedes.values():
        all_phones.update(sede_info.get("telefonos", []))

    structured = {
        "meta": {
            "pipeline":         "Knowledge Base ETL — Optimizado con Cache + Reintentos",
            "fecha_generacion": datetime.now().isoformat(),
            "config_snapshot":  {
                "chunk_size":    CHUNK_SIZE,
                "chunk_overlap": CHUNK_OVERLAP,
                "llm_model":     _LLM["model"],
                "embed_model":   _EMB["model_name"],
            },
        },
        "perfil_corporativo": {
            "razon_social":          "Tecnoquimicas S.A.",
            "NIT":                   nit_list[0] if nit_list else "890.300.153-6",
            "todos_nits_detectados": nit_list,
            **regex_data["cifras"],
        },
        "portafolio": {
            "marcas_detectadas_en_corpus": regex_data["marcas"],
        },
        "directorio_contacto": {
            "correos_oficiales":             regex_data["correos"],
            "horarios_detectados":           regex_data["horarios"],
            "telefonos_globales":            sorted(all_phones),
            "sedes_y_direcciones_oficiales": sedes,
            "linea_etica":                   extract_contact_special(raw_data),
            "servicio_al_cliente": {
                "telefono_gratuito": "01 8000 52 33 39",
                "correo":            "serviciosalconsumidor@tecnoquimicas.com",
                "canal":             "PQRS — Preguntas, Eventos Adversos, Reclamos, Sugerencias",
            },
        },
    }

    (BASE_DIR / "datos_estructurados.json").write_text(
        json.dumps(structured, ensure_ascii=False, indent=4), encoding="utf-8"
    )
    log.info("'datos_estructurados.json' generado en %s.", BASE_DIR)
    return structured

# ══════════════════════════════════════════════════════════════════════════════
# 11. CHUNKING VECTORIAL CON METADATA ENRIQUECIDA
# ══════════════════════════════════════════════════════════════════════════════
def process_to_chunks(
    raw_data: dict,
    boilerplate: set[str],
    medical_previews: list[dict],
) -> list[dict]:
    """
    Genera todos los chunks del pipeline:
      - Chunks corporativos y de articulos medicos completos (flujo normal).
      - Chunks de previews medicos truncados (ya extraidos y formateados).
    Los previews se inyectan directamente sin pasar por splitter ni scoring.
    """
    _print_step("Chunking Vectorial con Metadata Enriquecida")

    md_splitter  = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")]
    )
    txt_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )

    all_chunks:      list[dict] = []
    discarded_count: int        = 0
    ts = datetime.now().isoformat()

    preview_keys: set[str] = {p["metadata"]["section_key"] for p in medical_previews}

    for section_key, content in raw_data.items():
        if section_key in preview_keys:
            continue

        cleaned = clean_text(content, boilerplate)
        if len(cleaned) < MIN_CHUNK_LENGTH:
            continue

        section_meta = parse_section_metadata(section_key, content)

        try:
            md_splits = md_splitter.split_text(cleaned)
        except Exception:
            md_splits = []

        if not md_splits:
            md_splits = [Document(page_content=cleaned)]

        chunks = txt_splitter.split_documents(md_splits)

        for i, doc in enumerate(chunks):
            text    = doc.page_content.strip()
            quality = compute_chunk_quality(text)

            if quality < QUALITY_MIN_SCORE:
                discarded_count += 1
                log.debug(
                    "Chunk descartado [score=%.3f] seccion='%s' idx=%d | preview='%s'",
                    quality, section_key, i, text[:80].replace("\n", " "),
                )
                continue

            meta = {**section_meta, **doc.metadata}
            meta["quality_score"] = quality
            meta["timestamp"]     = ts

            all_chunks.append({
                "id":       f"{section_key}_{i:04d}",
                "text":     text,
                "metadata": meta,
            })

    all_chunks.extend(medical_previews)
    log.info("Previews medicos inyectados: %d chunks.", len(medical_previews))

    all_chunks = deduplicate_chunks(all_chunks)
    log.info(
        "Chunking total: %d chunks finales (%d descartados por calidad).",
        len(all_chunks), discarded_count,
    )

    (BASE_DIR / "chunks.json").write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return all_chunks

# ══════════════════════════════════════════════════════════════════════════════
# 12. VECTORIZACION DIVIDIDA + INDEX MANIFEST
# ══════════════════════════════════════════════════════════════════════════════
def build_faiss_index(chunks: list[dict]) -> None:
    _print_step("Vectorizacion — Indices FAISS Divididos")

    log.info("Cargando modelo de embeddings '%s'...", _EMB["model_name"])
    embeddings = HuggingFaceEmbeddings(
        model_name=_EMB["model_name"],
        model_kwargs={"device": _EMB["device"]},
        encode_kwargs={"normalize_embeddings": _EMB["normalize"]},
    )

    index_groups = {
        "corporativo": [c for c in chunks if c["metadata"]["content_type"] == "corporativo"],
        "medico":      [c for c in chunks if c["metadata"]["content_type"] == "articulo_medico"],
    }

    manifest: dict = {
        "generated_at": datetime.now().isoformat(),
        "embed_model":  _EMB["model_name"],
        "indices":      {},
    }

    for index_name, group in index_groups.items():
        if not group:
            log.warning("Indice '%s': sin chunks, se omite.", index_name)
            continue

        docs       = [Document(page_content=c["text"], metadata=c["metadata"]) for c in group]
        vs         = FAISS.from_documents(docs, embeddings)
        index_path = str(BASE_DIR / f"faiss_{index_name}")
        vs.save_local(index_path)

        specialties = sorted({
            c["metadata"].get("specialty", "")
            for c in group if c["metadata"].get("specialty")
        })

        preview_count = sum(
            1 for c in group
            if c["metadata"].get("article_type") == "preview_truncado"
        )
        manifest["indices"][index_name] = {
            "path":           index_path,
            "content_type":   group[0]["metadata"]["content_type"],
            "chunk_count":    len(docs),
            "preview_chunks": preview_count,
            "specialties":    specialties,
            "description": (
                "Contenido corporativo: quienes somos, productos, contacto, sostenibilidad."
                if index_name == "corporativo"
                else (
                    f"Articulos medicos y biblioteca cientifica por especialidad. "
                    f"Incluye {preview_count} previews con URL directa al portal TQFarma."
                )
            ),
        }
        log.info("Indice 'faiss_%s' guardado en %s (%d fragmentos).", index_name, index_path, len(docs))

    (BASE_DIR / "index_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=4), encoding="utf-8"
    )
    log.info("'index_manifest.json' generado en %s.", BASE_DIR)

# ══════════════════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════════════════
def _print_step(title: str) -> None:
    log.info("--- %s ---", title)
    print("  " + "-" * 64)

# ══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    W = 70
    print("\n" + "=" * W)
    print("  KNOWLEDGE BASE PIPELINE — OPTIMIZADO")
    print("=" * W + "\n")

    kb_path = BASE_DIR / "raw_data.json"
    if not kb_path.exists():
        log.error("No se encontro 'raw_data.json' en %s. Ejecuta 'scraper.py' primero.", BASE_DIR)
        raise SystemExit(1)

    with open(kb_path, encoding="utf-8") as f:
        raw: dict = json.load(f)

    boilerplate      = build_boilerplate_index(raw)
    medical_previews = extract_medical_previews(raw)
    regex_data       = extract_regex_data(raw)
    sedes            = extract_llm_sedes(raw)
    assemble_structured_data(raw, regex_data, sedes)
    chunks           = process_to_chunks(raw, boilerplate, medical_previews)
    build_faiss_index(chunks)

    print("\n" + "=" * W)
    log.info("PIPELINE COMPLETADO. Revisa %s/pipeline.log para detalles.", BASE_DIR)
    print("=" * W + "\n")
