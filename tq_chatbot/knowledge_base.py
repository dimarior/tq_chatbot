
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

import yaml
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
# 0. LOGGING
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

    fh = logging.FileHandler("pipeline.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger

log = _setup_logging()

# ══════════════════════════════════════════════════════════════════════════════
# 1. CONFIGURACIÓN EXTERNALIZADA
# ══════════════════════════════════════════════════════════════════════════════
_DEFAULT_CONFIG: dict = {
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
            "Nicaragua", "Panamá", "Costa Rica", "República Dominicana", "Perú",
        ],
        "cities": [
            "Cali", "Bogotá", "Medellín", "Barranquilla", "Cartagena",
            "Quito", "Guayaquil", "San Salvador", "Ciudad de Guatemala",
        ],
    },
}

def load_config(path: str = "config.yaml") -> dict:
    """Carga config.yaml si existe; si no, usa defaults y lo genera para futura edición."""
    cfg_path = Path(path)
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        # Merge superficial: claves de usuario tienen precedencia
        merged = {**_DEFAULT_CONFIG}
        for section, values in user_cfg.items():
            if isinstance(values, dict) and section in merged:
                merged[section] = {**merged[section], **values}
            else:
                merged[section] = values
        log.info("Configuración cargada desde '%s'.", path)
        return merged
    else:
        cfg_path.write_text(yaml.dump(_DEFAULT_CONFIG, allow_unicode=True, sort_keys=False), encoding="utf-8")
        log.warning("No se encontró config.yaml. Generado con valores por defecto.")
        return _DEFAULT_CONFIG

CFG = load_config()

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

TQ_BRANDS          = set(_DOMAIN["brands"])
MEDICAL_SPECIALTIES = set(_DOMAIN["medical_specialties"])
GEO_WHITELIST       = set(_DOMAIN["countries"] + _DOMAIN["cities"])

# ── Ruido y navegación (mantenido en código; raramente cambia) ────────────────
EXACT_NOISE: set[str] = {
    "Nacionalidad", "Nombre", "Apellidos", "Correo Electrónico", "Teléfono",
    "ACEPTAR", "Ingresar", "Cerrar", "Enviar", "Aceptar", "Volver",
    "Comparte en:", "ACCEDER",
}

NOISE_PHRASES: list[str] = [
    "Usted está siendo redirigido", "sitio web externo y ajeno",
    "Si desea continuar, haga clic", "Bienvenido al Chat",
    "Tipo de identificación", "Cédula de", "Carnet diplomático",
    "ID extranjero", "Fideicomiso", "Registro civil", "Tarjeta de identidad",
    "Acepto los Términos", "var metaTag", "return metaTag", "No description found",
    "Regístrese al portal", "Y acceda a contenido exclusivo",
    "Bienvenido al Portal Farmacéutico", "Esta información es exclusiva",
    "Certifico que soy médico", "Su mensaje se ha enviado satisfactoriamente",
    "Recomiende esta noticia", "Account/Login", "regresar=%2F",
]

NAV_LINK_WORDS: set[str] = {
    "Síguenos", "LinkedIn", "Instagram", "Facebook", "Youtube", "Twitter",
    "Colaborador TQ", "Portal Médicos", "Encuéntranos", "Gobierno Corporativo",
    "Así Cambiamos El Mundo", "Trabaja con Nosotros", "Nuestras Marcas",
    "Noticias", "Contacto", "Inicio", "Términos y condiciones",
    "Políticas de privacidad", "Todos los derechos reservados",
    "INICIAR SESIÓN", "REGISTRARSE", "Acceso a Journals", "VER TODAS",
    "VER MÁS", "Anterior", "Siguiente",
    "Cardiología", "Endocrinología", "Gastroenterología", "Ginecología",
    "Medicina General", "Medicina Interna", "Neurología", "Odontología",
    "Oftalmología", "Otorrinolaringología", "Ortopedia", "Pediatría",
    "Psiquiatría", "Reumatología", "Urología",
    "¿Quiénes somos?", "Nuestro propósito", "Misión", "Visión",
    "Credo", "Historia",
}

CATEGORY_MAP: dict[tuple, str] = {
    ("mision", "vision", "credo", "proposito", "quien", "historia"): "quienes_somos",
    ("producto", "marca", "linea", "catalogo", "referencia"):        "productos",
    ("contacto", "sede", "encuentranos", "encuéntranos", "oficina", "atencion"): "contacto",
    ("sostenibilidad", "responsabilidad", "ambiental", "social"):    "sostenibilidad",
    ("noticia", "blog", "prensa", "comunicado"):                      "noticias",
    ("trabaj", "empleo", "vacante", "seleccion"):                     "empleo",
}

LLM_SECTION_KEYWORDS = {"encuentranos", "contacto", "sedes", "sucursales"}

# ── Directorios de trabajo ────────────────────────────────────────────────────
CACHE_DIR = Path(".llm_cache")
CACHE_DIR.mkdir(exist_ok=True)

TQFARMA_BASE_URL = "https://www.tqfarma.com"

# Regex para extraer partes clave de artículos médicos truncados por login
_RE_MED_TITLE   = re.compile(
    r'^#\s+\[([^\]]+)\]\((/detalle-actualizacion-medica/[^\)]+)\)', re.M
)
_RE_MED_PREVIEW = re.compile(
    r'\n([A-ZÁÉÍÓÚÑ][^\n]{80,}?\.\.\.)\n'
)
_RE_MED_DATE    = re.compile(r'(\d{2}/\d{2}/\d{4})')
_RE_MED_SPEC    = re.compile(
    r'### (Cardiología|Endocrinología|Gastroenterología|Ginecología|'
    r'Medicina General|Medicina Interna|Neurología|Odontología|'
    r'Oftalmología|Otorrinolaringología|Ortopedia|Pediatría|'
    r'Psiquiatría|Reumatología|Urología)\n'
)

# ══════════════════════════════════════════════════════════════════════════════
# 2. API KEY
# ══════════════════════════════════════════════════════════════════════════════
load_dotenv()

def get_api_key() -> str:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        raise EnvironmentError("Falta GOOGLE_API_KEY en tu archivo .env")
    return key

# ══════════════════════════════════════════════════════════════════════════════
# 3. BOILERPLATE AUTO-DETECTOR
# ══════════════════════════════════════════════════════════════════════════════
def build_boilerplate_index(raw_data: dict) -> set[str]:
    _print_step("🧬", "Construyendo índice de boilerplate estadístico")
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
# 3B. EXTRACTOR DE ARTÍCULOS MÉDICOS TRUNCADOS
# ══════════════════════════════════════════════════════════════════════════════
def extract_medical_previews(raw_data: dict) -> list[dict]:
    """
    Procesa secciones médicas truncadas por el muro de login de tqfarma.com.

    De cada artículo extrae:
      - título limpio
      - preview visible antes del "VER MÁS"
      - URL completa al artículo en tqfarma.com
      - especialidad médica y fecha de publicación

    Produce chunks de tipo 'articulo_medico_preview' que permiten al asistente:
      1. Confirmar que el artículo existe.
      2. Dar un resumen mínimo del contenido disponible.
      3. Enviar al usuario al portal con la URL directa, indicando que
         debe iniciar sesión como médico u odontólogo para leer completo.
    """
    _print_step("Extracción de Previews de Artículos Médicos")

    previews: list[dict] = []
    skipped = 0

    for section_key, content in raw_data.items():
        # Solo secciones médicas con muro de login
        if "Account/Login" not in content or "/detalle-actualizacion-medica/" not in content:
            continue

        # 1. Título y path relativo
        title_m = _RE_MED_TITLE.search(content)
        if not title_m:
            skipped += 1
            log.debug("Preview médico sin título detectado: '%s'", section_key)
            continue

        title    = title_m.group(1).strip()
        rel_path = title_m.group(2).strip()
        full_url = f"{TQFARMA_BASE_URL}{rel_path}"

        # 2. Especialidad
        spec_m    = _RE_MED_SPEC.search(content)
        specialty = spec_m.group(1) if spec_m else "General"

        # 3. Preview — párrafo visible que termina en "..."
        prev_m  = _RE_MED_PREVIEW.search(content)
        preview = prev_m.group(1).strip() if prev_m else ""

        # 4. Fecha de publicación
        date_m = _RE_MED_DATE.search(content)
        date   = date_m.group(1) if date_m else ""

        # 5. Construir texto del chunk
        chunk_text = (
            f"Artículo médico: {title}\n"
            f"Especialidad: {specialty}\n"
        )
        if date:
            chunk_text += f"Fecha de publicación: {date}\n"
        if preview:
            chunk_text += f"\nResumen disponible:\n{preview}\n"
        chunk_text += (
            f"\nPara leer el artículo completo, ingresa al portal TQFarma "
            f"(requiere inicio de sesión como médico u odontólogo):\n{full_url}"
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
        "Previews médicos: %d artículos extraídos, %d secciones sin título (omitidas).",
        len(previews), skipped
    )
    return previews

# ══════════════════════════════════════════════════════════════════════════════
# 4. METADATA PARSER
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
# 5. LIMPIEZA MULTICAPA
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
# 6. SCORING DE CALIDAD Y DEDUPLICACIÓN
# ══════════════════════════════════════════════════════════════════════════════
def compute_chunk_quality(text: str) -> float:
    """
    Score entre 0 y 1. Pesos configurables en config.yaml → quality_weights.
    Loggea chunks descartados en DEBUG para detectar falsos negativos.
    """
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

    url_count    = len(re.findall(r'https?://', text))
    noise_penalty = min(url_count * _QW["url_penalty_per_url"], _QW["url_penalty_max"])

    score = (
        density     * _QW["density"]
        + length_score * _QW["length"]
        + struct_bonus
        - noise_penalty
    )
    return round(min(max(score, 0.0), 1.0), 3)

def _fingerprint(text: str) -> str:
    return re.sub(r'\s+', ' ', text[:120].lower().strip())

def deduplicate_chunks(chunks: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for chunk in chunks:
        fp = _fingerprint(chunk["text"])
        if fp not in seen:
            seen.add(fp)
            unique.append(chunk)
    log.debug("Deduplicación: %d → %d chunks únicos.", len(chunks) + (len(chunks) - len(unique)), len(unique))
    return unique

# ══════════════════════════════════════════════════════════════════════════════
# 7A. EXTRACCIÓN DE REGEX (separada del LLM)
# ══════════════════════════════════════════════════════════════════════════════
_RE_MAIL          = re.compile(r"([a-zA-Z0-9._%+\-]+@(?:tecnoquimicas|tqfarma|tqconfiable|tqgrupo|resguarda)\.com)", re.I)
_RE_NIT           = re.compile(r"\b(\d{3}\.?\d{3}\.?\d{3}-\d)\b")
_RE_HORARIO       = re.compile( r"(Lunes a (?:viernes|s[aá]bado)[^\n]{0,80}(?:\d{1,2}:\d{2}|\d{1,2}\s*(?:am|pm|a\.m\.|p\.m\.)))", re.I )
_RE_COLABORADORES = re.compile(r"(\d[\d\.]*)\.?\d*\s*colaboradores", re.I)
_RE_REFERENCIAS   = re.compile(r"alrededor de\s+([\d\.]+)\s*referencias", re.I)
_RE_SEDES_CO      = re.compile(r"(\w+)\s+sedes productivas en Colombia", re.I)
_RE_SEDES_CA      = re.compile(r"(\w+)\s+en Centroamérica", re.I)
_RE_ANOS_TRAY     = re.compile(r"más de\s+(\d+)\s+años", re.I)
_RE_PAISES_EXP    = re.compile(r"más de\s+(\d+)\s+países de América", re.I)

def extract_regex_data(raw_data: dict) -> dict:
    """Extrae con regex todo lo que no necesita comprensión semántica."""
    _print_step("🔎", "Extracción por Regex (datos estructurales)")

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
            cifras["sedes_productivas"] = f"{m_co.group(1).capitalize()} en Colombia, una en Centroamérica"
        if (m := _RE_ANOS_TRAY.search(content)) and "anos_trayectoria" not in cifras:
            cifras["anos_trayectoria"] = f"más de {m.group(1)} años"
        if (m := _RE_PAISES_EXP.search(content)) and "paises_exportacion" not in cifras:
            cifras["paises_exportacion"] = f"más de {m.group(1)} países de América"

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
# 7B. EXTRACCIÓN LLM (separada, con caché + reintentos)
# ══════════════════════════════════════════════════════════════════════════════
class SedeTQ(BaseModel):
    nombre_sede:      str       = Field(description="Nombre de la sede, planta o regional.")
    ciudad_o_pais:    str       = Field(description="Ciudad o país. Inferir del contexto si es posible.")
    direccion_exacta: str       = Field(description="Dirección física completa.")
    telefonos:        list[str] = Field(default_factory=list, description="Teléfonos asociados a esta sede.")

class DirectorioCompleto(BaseModel):
    sedes: list[SedeTQ] = Field(description="Lista exhaustiva de sedes encontradas en el texto.")

def _section_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

def _load_cached_result(section_key: str, content: str) -> DirectorioCompleto | None:
    cache_file = CACHE_DIR / f"{section_key}_{_section_hash(content)}.json"
    if cache_file.exists():
        log.debug("Cache hit para sección '%s'.", section_key)
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
Eres un analista de datos experto. Lee el siguiente texto corporativo de Tecnoquímicas
y extrae TODAS las sedes, regionales, plantas, centros de distribución y plataformas mencionadas.
Extrae el nombre, la dirección exacta, la ciudad/país y los teléfonos.
Si un campo no está disponible, usa una cadena vacía.

Texto:
{content}
""".strip()

def extract_llm_sedes(raw_data: dict) -> dict[str, dict]:
    """
    Extrae sedes usando Gemini únicamente en secciones relevantes.
    Usa caché SHA-256 por sección para evitar llamadas redundantes.
    Reintentos automáticos con backoff exponencial si la API falla.
    """
    _print_step("Extracción Semántica de Sedes (LLM + Caché + Reintentos)")
    extractor = _build_llm_extractor()
    sedes_perfectas: dict[str, dict] = {}
    failed_sections: list[str] = []

    relevant = {
        k: v for k, v in raw_data.items()
        if any(kw in k.lower() for kw in LLM_SECTION_KEYWORDS)
    }
    log.info("LLM: %d secciones relevantes para análisis de sedes.", len(relevant))

    for section_key, content in relevant.items():
        cached = _load_cached_result(section_key, content)
        if cached:
            resultado = cached
        else:
            prompt = _PROMPT_TEMPLATE.format(content=content)
            try:
                resultado: DirectorioCompleto = _invoke_llm(extractor, prompt)
                _save_cached_result(section_key, content, resultado)
                log.info("LLM: sección '%s' procesada (%d sedes).", section_key, len(resultado.sedes))
            except Exception as e:
                log.error("LLM: sección '%s' falló tras %d intentos. Error: %s",
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
        Path("llm_failed_sections.json").write_text(
            json.dumps(failed_sections, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return sedes_perfectas

# ══════════════════════════════════════════════════════════════════════════════
# 8. ENSAMBLADO DE DATOS ESTRUCTURADOS Y CONTACTO
# ══════════════════════════════════════════════════════════════════════════════
def extract_contact_special(raw_data: dict) -> dict:
    """Extrae la información especializada de la línea ética y servicio."""
    linea = raw_data.get("linea_etica", "")
    # Extraer emails y teléfonos de línea ética
    emails_etica = re.findall(r"[\w.]+@resguarda\.com", linea)
    tel_wsp = re.search(r"WhatsApp[^\d+]*(\+[\d\s]+)", linea)
    telefonos_etica = re.findall(r":\s*([\d\-]{6,})", linea)
    
    return {
        "email": emails_etica[0] if emails_etica else "",
        "whatsapp": tel_wsp.group(1).strip() if tel_wsp else "",
        "telefonos_por_pais": telefonos_etica,
        "portal": "http://www.resguarda.com/lineaeticatq"
    }

def assemble_structured_data(raw_data: dict, regex_data: dict, sedes: dict[str, dict]) -> dict:
    """Une los resultados de regex, LLM e info especial en el JSON estructurado final."""
    _print_step("Ensamblando datos_estructurados.json")

    nit_list = regex_data["nits"]

    # Enriquecer teléfonos globales con los extraídos de sedes
    all_phones: set[str] = set(regex_data["telefonos"])
    for sede_info in sedes.values():
        all_phones.update(sede_info.get("telefonos", []))

    structured = {
        "meta": {
            "pipeline":         "Knowledge Base ETL — Optimizado con Caché + Reintentos",
            "fecha_generacion": datetime.now().isoformat(),
            "config_snapshot":  {
                "chunk_size":    CHUNK_SIZE,
                "chunk_overlap": CHUNK_OVERLAP,
                "llm_model":     _LLM["model"],
                "embed_model":   _EMB["model_name"],
            },
        },
        "perfil_corporativo": {
            "razon_social":          "Tecnoquímicas S.A.",
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
                "correo": "serviciosalconsumidor@tecnoquimicas.com",
                "canal": "PQRS — Preguntas, Eventos Adversos, Reclamos, Sugerencias"
            }
        },
    }

    Path("datos_estructurados.json").write_text(
        json.dumps(structured, ensure_ascii=False, indent=4), encoding="utf-8"
    )
    log.info("'datos_estructurados.json' generado.")
    return structured

# ══════════════════════════════════════════════════════════════════════════════
# 9. CHUNKING VECTORIAL CON METADATA ENRIQUECIDA
# ══════════════════════════════════════════════════════════════════════════════
def process_to_chunks(
    raw_data: dict,
    boilerplate: set[str],
    medical_previews: list[dict],
) -> list[dict]:
    """
    Genera todos los chunks del pipeline:
      - Chunks corporativos y de artículos médicos completos (flujo normal).
      - Chunks de previews médicos truncados (ya extraídos y formateados).
    Los previews se inyectan directamente sin pasar por splitter ni scoring,
    ya que son chunks estructurados de tamaño controlado y calidad garantizada.
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

    # IDs de secciones médicas truncadas para no procesarlas dos veces
    preview_keys: set[str] = {p["metadata"]["section_key"] for p in medical_previews}

    for section_key, content in raw_data.items():
        # Las secciones con preview ya tienen su chunk dedicado — saltarlas
        # del flujo normal para no mezclar nav-noise con contenido útil
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
                    "Chunk descartado [score=%.3f] sección='%s' idx=%d | preview='%s'",
                    quality, section_key, i, text[:80].replace("\n", " ")
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

    # Inyectar previews médicos ya estructurados
    all_chunks.extend(medical_previews)
    log.info(
        "Previews médicos inyectados: %d chunks.",
        len(medical_previews)
    )

    all_chunks = deduplicate_chunks(all_chunks)
    log.info(
        "Chunking total: %d chunks finales (%d descartados por calidad).",
        len(all_chunks), discarded_count
    )

    Path("chunks.json").write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return all_chunks

# ══════════════════════════════════════════════════════════════════════════════
# 10. VECTORIZACIÓN DIVIDIDA + INDEX MANIFEST
# ══════════════════════════════════════════════════════════════════════════════
def build_faiss_index(chunks: list[dict]) -> None:
    _print_step("Vectorización — Índices FAISS Divididos")

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
        "generated_at":  datetime.now().isoformat(),
        "embed_model":   _EMB["model_name"],
        "indices":       {},
    }

    for index_name, group in index_groups.items():
        if not group:
            log.warning("Índice '%s': sin chunks, se omite.", index_name)
            continue

        docs = [Document(page_content=c["text"], metadata=c["metadata"]) for c in group]
        vs   = FAISS.from_documents(docs, embeddings)
        vs.save_local(f"faiss_{index_name}")

        specialties = sorted({
            c["metadata"].get("specialty", "")
            for c in group if c["metadata"].get("specialty")
        })

        preview_count = sum(
            1 for c in group
            if c["metadata"].get("article_type") == "preview_truncado"
        )
        manifest["indices"][index_name] = {
            "path":                  f"faiss_{index_name}",
            "content_type":          group[0]["metadata"]["content_type"],
            "chunk_count":           len(docs),
            "preview_chunks":        preview_count,
            "specialties":           specialties,
            "description":           (
                "Contenido corporativo: quiénes somos, productos, contacto, sostenibilidad."
                if index_name == "corporativo"
                else (
                    f"Artículos médicos y biblioteca científica por especialidad. "
                    f"Incluye {preview_count} previews con URL directa al portal TQFarma."
                )
            ),
        }
        log.info("Índice 'faiss_%s' guardado (%d fragmentos).", index_name, len(docs))

    Path("index_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=4), encoding="utf-8"
    )
    log.info(" 'index_manifest.json' generado para routing RAG.")

# ══════════════════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════════════════
def _print_step(icon: str, title: str) -> None:
    log.info("%s  %s", icon, title)
    print("  " + "─" * 64)

# ══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    W = 70
    print("\n" + "═" * W)
    print("KNOWLEDGE BASE PIPELINE — OPTIMIZADO")
    print("═" * W + "\n")

    kb_path = Path("raw_data.json")
    if not kb_path.exists():
        log.error("No se encontró 'raw_data.json'. Ejecuta 'scraper.py' primero.")
        raise SystemExit(1)

    with open(kb_path, encoding="utf-8") as f:
        raw: dict = json.load(f)

    # Paso 1 — Boilerplate
    boilerplate = build_boilerplate_index(raw)

    # Paso 2 — Extraer previews de artículos médicos truncados
    medical_previews = extract_medical_previews(raw)

    # Paso 3 — Extracción regex (independiente del LLM)
    regex_data = extract_regex_data(raw)

    # Paso 4 — Extracción LLM con caché + reintentos (solo secciones de contacto)
    sedes = extract_llm_sedes(raw)

    # Paso 5 — Ensamblar JSON estructurado
    assemble_structured_data(raw, regex_data, sedes)

    # Paso 6 — Chunking (corporativo normal + previews médicos inyectados)
    chunks = process_to_chunks(raw, boilerplate, medical_previews)

    # Paso 7 — Vectorización + manifest
    build_faiss_index(chunks)

    print("\n" + "═" * W)
    log.info("PIPELINE COMPLETADO. Revisa pipeline.log para detalles.")
    print("═" * W + "\n")
