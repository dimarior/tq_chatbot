"""Migra el conocimiento corporativo de TQ a la memoria de 6 capas de OpenFang.

Dos canales de inyección (Módulo 3, Ruta B — "Migración del Conocimiento"):

  1. Structured KV Store  ← apps/api/datos_estructurados.json
     Vía REST soportada:  PUT /api/memory/agents/{id}/kv/{key}
     Datos exactos y verificados (contacto, NIT, sedes, marcas, empleo...).

  2. Vector / semantic store  ← data/raw/*.json (corpus limpio de TQ + tqfarma)
     Inserción directa en la tabla `memories` del SQLite de OpenFang
     (~/.openfang/data/openfang.db). OpenFang NO expone un endpoint REST de
     ingesta masiva al vector store; su recall por defecto hace match de texto
     (LIKE) sobre `content` (con re-ranking coseno sólo si hay embedding de
     consulta, que OpenFang genera con su embebedor interno all-MiniLM). Por eso
     insertamos content + metadata SIN embedding propio: el recall LIKE del
     agente los encuentra, y no introducimos un espacio vectorial incompatible.

Idempotente: por cada URL se comparan content_hash; si no cambió, se salta. Los
IDs de los chunks son uuid5(url#i) → reinsertar reescribe en vez de duplicar.

Requisitos: el daemon de OpenFang debe estar corriendo (`openfang start`) y el
agente `tq-asistente` debe existir (este script lo crea si falta, vía REST).

Uso (desde la raíz del repo):
    uv run python scripts/migrate_to_openfang.py [--dry-run] [--agent tq-asistente]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter

from apps.api.core.config import get_settings

LOG = logging.getLogger("migrate_openfang")

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
STRUCTURED_JSON = ROOT / "apps" / "api" / "datos_estructurados.json"

OPENFANG_URL = os.environ.get("OPENFANG_URL", "http://127.0.0.1:4200").rstrip("/")
OPENFANG_DB = Path(
    os.environ.get("OPENFANG_DB", "~/.openfang/data/openfang.db")
).expanduser()
AGENT_MANIFEST = ROOT / "openfang" / "agents" / "tq-asistente" / "agent.toml"

SCOPE = "corporate_knowledge"
# MemorySource::System serializado (openfang-memory/src/semantic.rs). Si no
# parsea, el recall de OpenFang hace fallback a System de todos modos.
DEFAULT_SOURCE = json.dumps("System")
DEFAULT_CONFIDENCE = 1.0

# Columnas de la tabla `memories` (openfang-memory/src/semantic.rs). Las
# validamos antes de insertar como defensa contra cambios de esquema pre-1.0.
MEMORIES_COLUMNS = {
    "id", "agent_id", "content", "source", "scope", "confidence",
    "metadata", "created_at", "accessed_at", "access_count", "deleted", "embedding",
}
_INSERT_SQL = (
    "INSERT OR REPLACE INTO memories "
    "(id, agent_id, content, source, scope, confidence, metadata, "
    " created_at, accessed_at, access_count, deleted, embedding) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
)

_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
_WS_RE = re.compile(r"\s+")
_SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", " ", ""]


def _chunk_quality_ok(chunk: str) -> bool:
    """Descarta chunks demasiado cortos o que son sólo markdown sin sustancia."""
    if len(chunk.strip()) < 80:
        return False
    plain = chunk
    for _ in range(3):
        plain = _IMG_RE.sub("", plain)
        plain = _LINK_RE.sub("", plain)
    return len(_WS_RE.sub(" ", plain).strip()) >= 80


def _chunk_hash(chunk: str) -> str:
    return hashlib.sha256(_WS_RE.sub(" ", chunk.strip().lower()).encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _memory_row(mem_id: str, agent_id: str, content: str, metadata: dict, now: str) -> tuple:
    return (
        mem_id, agent_id, content, DEFAULT_SOURCE, SCOPE, DEFAULT_CONFIDENCE,
        json.dumps(metadata, ensure_ascii=False), now, now, 0, 0, None,
    )


def load_url_hashes(conn: sqlite3.Connection) -> dict[str, str]:
    """Pre-carga {url: content_hash} de todo el corpus en UNA consulta, en vez
    de un SELECT por documento (evita ~1.4k escaneos de la tabla)."""
    cur = conn.execute(
        "SELECT json_extract(metadata, '$.url'), json_extract(metadata, '$.content_hash') "
        "FROM memories WHERE scope = ?",
        (SCOPE,),
    )
    return {url: h for url, h in cur.fetchall() if url}


def delete_url(conn: sqlite3.Connection, url: str) -> None:
    conn.execute(
        "DELETE FROM memories WHERE scope = ? AND json_extract(metadata, '$.url') = ?",
        (SCOPE, url),
    )


# ── Adaptador de memoria de OpenFang (puerto de ingesta) ──────────────────────
class OpenFangMemoryClient:
    """Encapsula las dos vías de escritura a la memoria de OpenFang: KV vía REST
    y vector vía SQLite directo. Aísla a los callers del detalle de transporte."""

    def __init__(self, base_url: str, db_path: Path, timeout: float = 30.0):
        self.base_url = base_url
        self.db_path = db_path
        self._http = httpx.Client(base_url=base_url, timeout=timeout)

    # -- Agente --------------------------------------------------------------
    def ensure_agent(self, name: str, manifest_path: Path) -> str:
        """Devuelve el id del agente `name`; lo crea desde el manifest si falta."""
        r = self._http.get("/api/agents")
        r.raise_for_status()
        for a in r.json():
            if a.get("name") == name:
                LOG.info("agente '%s' ya existe (id=%s)", name, a["id"])
                return a["id"]
        if not manifest_path.exists():
            raise FileNotFoundError(f"no encuentro el manifest del agente: {manifest_path}")
        LOG.info("agente '%s' no existe — creándolo desde %s", name, manifest_path.name)
        resp = self._http.post(
            "/api/agents",
            json={"manifest_toml": manifest_path.read_text("utf-8")},
        )
        resp.raise_for_status()
        agent_id = resp.json()["agent_id"]
        LOG.info("agente '%s' creado (id=%s)", name, agent_id)
        return agent_id

    # -- KV store (REST) -----------------------------------------------------
    def kv_set(self, agent_id: str, key: str, value) -> None:
        r = self._http.put(
            f"/api/memory/agents/{agent_id}/kv/{key}", json={"value": value}
        )
        r.raise_for_status()

    # -- Vector store (SQLite directo) ---------------------------------------
    @contextmanager
    def connection(self):
        """Conexión a la BD de memoria de OpenFang; commitea al salir sin error."""
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"no existe la BD de memoria de OpenFang: {self.db_path}\n"
                "Arranca el daemon primero: `openfang start`."
            )
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA busy_timeout=5000;")
        cols = {row[1] for row in conn.execute("PRAGMA table_info(memories)")}
        if not MEMORIES_COLUMNS.issubset(cols):
            conn.close()
            raise RuntimeError(
                "la tabla `memories` no tiene el esquema esperado "
                f"(faltan: {MEMORIES_COLUMNS - cols}). El esquema de OpenFang "
                "pudo cambiar (pre-1.0); revisa openfang-memory/src/semantic.rs."
            )
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def close(self) -> None:
        self._http.close()


# ── KV: datos estructurados → KV store ────────────────────────────────────────
def seed_structured_kv(client: OpenFangMemoryClient, agent_id: str, data: dict, dry_run: bool) -> int:
    kv = {
        "identidad": data["empresa"],
        "contacto": data["contacto"],
        "sedes": data["sedes"],
        "marcas": data["marcas"],
        "lineas_negocio": data["lineas_negocio"],
        "sostenibilidad": data.get("sostenibilidad", {}),
        "empleo": data["empleo"],
    }
    for key, value in kv.items():
        if dry_run:
            LOG.info("would-set kv[%s]", key)
            continue
        client.kv_set(agent_id, key, value)
        LOG.info("kv[%s] set", key)
    return len(kv)


def _fact_sentences(data: dict) -> list[tuple[str, str]]:
    """Frases de hechos en lenguaje natural (clave → texto). Se insertan en el
    vector store para que `memory_recall` (match de texto) las encuentre — más
    robusto que depender de que el modelo adivine la clave exacta de `kv_get`."""
    e, c = data["empresa"], data["contacto"]
    sedes = "; ".join(
        f"{s['ciudad']} ({s['departamento']})" + (f": {s['direccion']}" if s.get("direccion") else "")
        for s in data["sedes"].values()
    )
    return [
        ("contacto", f"Contacto de Tecnoquímicas (TQ Confiable): Línea de Servicio al Cliente {c['telefono_cliente']}. Línea Ética {c['linea_etica']} (24/7). Correo {c['email_cliente']}. Horario de atención: {c['horario_atencion']}. Sitio web {c['sitio_web']}, portal médico {c['portal_medico']}."),
        ("identidad", f"Tecnoquímicas S.A. (nombre comercial TQ Confiable). NIT {e['nit']}. Fundada en {e['fundacion']} (originalmente {e['nombre_original']}), con {e['anos_trayectoria']} años de trayectoria, {e['colaboradores']} colaboradores y presencia en {e['paises_presencia']} países."),
        ("sedes", f"Sedes de Tecnoquímicas: {sedes}. La sede principal y planta de manufactura está en Cali, Valle del Cauca."),
        ("marcas", f"Marcas de Tecnoquímicas: {', '.join(data['marcas'])}."),
        ("lineas_negocio", f"Líneas de negocio de Tecnoquímicas: {'; '.join(data['lineas_negocio'])}."),
        ("empleo", f"Empleo en Tecnoquímicas: portal de ofertas {data['empleo']['portal_ofertas']}. Programa para universitarios: {data['empleo']['programa_universitarios']}. Beneficios: {data['empleo']['programa_beneficios']}."),
    ]


def seed_facts(conn, agent_id: str, data: dict, dry_run: bool) -> int:
    """Inserta las frases de hechos en la tabla `memories` (vector store)."""
    facts = _fact_sentences(data)
    if dry_run:
        LOG.info("would-seed %d frases de hechos al vector store", len(facts))
        return len(facts)
    now = _now()
    rows = [
        _memory_row(
            str(uuid5(NAMESPACE_URL, f"tq://facts/{key}")),
            agent_id,
            text,
            {"url": f"tq://facts/{key}", "title": f"Dato verificado: {key}",
             "source": "datos_estructurados", "kind": "fact"},
            now,
        )
        for key, text in facts
    ]
    conn.executemany(_INSERT_SQL, rows)
    LOG.info("vector store: %d frases de hechos sembradas", len(facts))
    return len(facts)


# ── Vector: data/raw/*.json → tabla memories ──────────────────────────────────
def ingest_corpus(conn, agent_id: str, url_hashes: dict[str, str], dry_run: bool) -> dict:
    files = sorted(RAW_DIR.glob("*.json"))
    if not files:
        LOG.warning("no hay archivos en %s — corre scripts/fetch_sitemaps.py primero", RAW_DIR)
        return {}
    settings = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=_SEPARATORS,
    )
    counts = {"unchanged": 0, "inserted": 0, "updated": 0, "empty": 0, "skipped": 0}
    total_chunks = 0
    seen_chunk_hashes: set[str] = set()  # dedup de boilerplate compartido entre docs
    now = _now()

    for fp in files:
        try:
            doc = json.loads(fp.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            LOG.error("skip %s: %s", fp.name, e)
            counts["skipped"] += 1
            continue
        url, content_hash = doc["url"], doc["content_hash"]

        existing = url_hashes.get(url)
        if existing == content_hash:
            counts["unchanged"] += 1
            continue

        chunks: list[str] = []
        for txt in splitter.split_text(doc["text"]):
            if not _chunk_quality_ok(txt):
                continue
            h = _chunk_hash(txt)
            if h in seen_chunk_hashes:
                continue
            seen_chunk_hashes.add(h)
            chunks.append(txt)

        if not chunks:
            counts["empty"] += 1
            continue

        if dry_run:
            counts["updated" if existing else "inserted"] += 1
            total_chunks += len(chunks)
            continue

        # Borra los chunks viejos del URL: si el doc encogió, los índices
        # sobrantes (uuid5 url#i) quedarían huérfanos al reinsertar.
        delete_url(conn, url)
        rows = [
            _memory_row(
                str(uuid5(NAMESPACE_URL, f"{url}#{i}")),
                agent_id,
                txt,
                {"url": url, "title": doc.get("title"), "source": doc.get("source"),
                 "content_hash": content_hash, "chunk_index": i},
                now,
            )
            for i, txt in enumerate(chunks)
        ]
        conn.executemany(_INSERT_SQL, rows)
        counts["updated" if existing else "inserted"] += 1
        total_chunks += len(chunks)
        LOG.info("%-9s %s (%d chunks)", "updated" if existing else "inserted", url, len(chunks))

    counts["total_chunks"] = total_chunks
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="no escribe nada")
    parser.add_argument("--agent", default="tq-asistente", help="nombre del agente destino")
    parser.add_argument("--skip-kv", action="store_true", help="omite el seeding del KV store")
    parser.add_argument("--skip-corpus", action="store_true", help="omite el corpus vectorial")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = OpenFangMemoryClient(OPENFANG_URL, OPENFANG_DB)
    try:
        data = json.loads(STRUCTURED_JSON.read_text("utf-8"))
        agent_id = client.ensure_agent(args.agent, AGENT_MANIFEST)

        if not args.skip_kv:
            LOG.info("KV store: %d claves sembradas", seed_structured_kv(client, agent_id, data, args.dry_run))

        if args.dry_run:
            if not args.skip_kv:
                seed_facts(None, agent_id, data, dry_run=True)
            if not args.skip_corpus:
                LOG.info("Vector store: %s", ingest_corpus(None, agent_id, {}, dry_run=True))
        else:
            with client.connection() as conn:
                if not args.skip_kv:
                    seed_facts(conn, agent_id, data, dry_run=False)
                if not args.skip_corpus:
                    url_hashes = load_url_hashes(conn)
                    LOG.info("Vector store: %s", ingest_corpus(conn, agent_id, url_hashes, dry_run=False))
    except httpx.HTTPError as e:
        LOG.error("error de API de OpenFang: %s", e)
        LOG.error("¿está corriendo el daemon? -> `openfang start`")
        return 1
    except (FileNotFoundError, RuntimeError) as e:
        LOG.error("%s", e)
        return 1
    finally:
        client.close()
    LOG.info("migración completada%s", " (dry-run)" if args.dry_run else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
