"""Idempotent ingestion: data/raw/*.json → embeddings → Chroma (langchain).

Per-document flow:
  - Buscar en Chroma chunks con `metadata.url == doc.url` y leer su
    `content_hash`. Si coincide con el del archivo, skip.
  - En caso contrario:
        * Borrar los chunks viejos de ese URL en la colección.
        * Trocear, deduplicar y embebir los chunks nuevos.
        * Insertarlos con IDs deterministas (uuid5 sobre url#index) para
          que reingestas posteriores reescriban en lugar de duplicar.

El run es seguro de re-ejecutar: la misma entrada produce la misma colección.

Run:
    uv run python scripts/ingest_to_rag.py [--dry-run] [--only <substring>]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from apps.api.core.config import get_settings


LOG = logging.getLogger("ingest")

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"


# La limpieza fuerte ocurre en fetch_sitemaps.py (webclaw --include /
# --only-main-content). Aquí solo defendemos contra: (1) chunks demasiado
# cortos para aportar contexto y (2) chunks idénticos entre documentos
# (footers o separadores que cualquier extractor deja pasar).
_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
_WS_RE = re.compile(r"\s+")


def _chunk_quality_ok(chunk: str) -> bool:
    s = chunk.strip()
    if len(s) < 80:
        return False
    # Quita imágenes y links anidados/simples; si queda menos de 80 chars de
    # texto plano, el chunk es markdown sin sustancia.
    plain = chunk
    for _ in range(3):
        plain = _IMG_RE.sub("", plain)
        plain = _LINK_RE.sub("", plain)
    if len(_WS_RE.sub(" ", plain).strip()) < 80:
        return False
    return True


def _chunk_hash(chunk: str) -> str:
    return hashlib.sha256(_WS_RE.sub(" ", chunk.strip().lower()).encode()).hexdigest()


def _url_document_id(url: str) -> int:
    """ID estable para `metadata.document_id`, derivado del URL.

    Mantenemos el campo por compatibilidad con `RetrievedChunk` (consume el
    api/schemas). El valor concreto no se usa para joinear nada — Chroma
    ya identifica chunks por su `id` (uuid5).
    """
    return int(hashlib.sha1(url.encode()).hexdigest()[:12], 16)


def _existing_hash(vector_store: Chroma, url: str) -> str | None:
    """Devuelve el content_hash registrado para `url` en Chroma, o None."""
    existing = vector_store.get(where={"url": url}, limit=1, include=["metadatas"])
    metadatas = existing.get("metadatas") or []
    if not metadatas:
        return None
    return metadatas[0].get("content_hash")


def _delete_by_url(vector_store: Chroma, url: str) -> None:
    """Borra todos los chunks de un URL antes de reinsertar la versión nueva."""
    rows = vector_store.get(where={"url": url}, include=[])
    ids = rows.get("ids") or []
    if ids:
        vector_store.delete(ids=ids)


def _ingest_one(
    vector_store: Chroma,
    splitter: RecursiveCharacterTextSplitter,
    doc: dict,
    dry_run: bool,
    seen_hashes: set[str],
) -> tuple[str, int]:
    url = doc["url"]
    content_hash = doc["content_hash"]
    existing_hash = _existing_hash(vector_store, url)

    if existing_hash == content_hash:
        return ("unchanged", 0)

    if dry_run:
        kind = "would-update" if existing_hash else "would-insert"
        return (kind, 0)

    raw_chunks = splitter.split_text(doc["text"])
    # Filtra basura y deduplica contra todo lo visto en la corrida.
    unique_chunks: list[str] = []
    for txt in raw_chunks:
        if not _chunk_quality_ok(txt):
            continue
        h = _chunk_hash(txt)
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        unique_chunks.append(txt)

    if not unique_chunks:
        return ("empty", 0)

    # Limpia los chunks viejos de este URL ANTES de insertar — los IDs
    # uuid5(url#i) son deterministas, así que `add_documents` reescribiría las
    # filas con el mismo i, pero si el doc cambió y ahora tiene MENOS chunks,
    # los sobrantes con índices mayores quedarían huérfanos.
    _delete_by_url(vector_store, url)

    doc_id = _url_document_id(url)
    documents = [
        Document(
            page_content=txt,
            metadata={
                "url": url,
                "title": doc.get("title"),
                "source": doc["source"],
                "content_hash": content_hash,
                "document_id": doc_id,
                "chunk_index": i,
            },
        )
        for i, txt in enumerate(unique_chunks)
    ]
    ids = [str(uuid5(NAMESPACE_URL, f"{url}#{i}")) for i in range(len(unique_chunks))]
    vector_store.add_documents(documents, ids=ids)

    return (("updated" if existing_hash else "inserted"), len(unique_chunks))


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    embedder = OllamaEmbeddings(
        base_url=settings.ollama_host,
        model=settings.embed_model,
    )
    vector_store = Chroma(
        persist_directory=settings.chroma_path,
        embedding_function=embedder,
    )
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", "? ", "! ", " ", ""],
    )

    files = sorted(RAW_DIR.glob("*.json"))
    if args.only:
        files = [f for f in files if args.only in f.read_text("utf-8")]
    if not files:
        LOG.warning("no files in %s — run fetch_sitemaps.py first", RAW_DIR)
        return 1

    counts = {
        "unchanged": 0, "inserted": 0, "updated": 0, "empty": 0,
        "would-insert": 0, "would-update": 0,
    }
    total_chunks = 0
    # Hashes vistos en esta corrida; evita reembedir/insertar el mismo chunk
    # en docs distintos (boilerplate del template, "Lo más leído", etc.).
    seen_hashes: set[str] = set()
    # Pre-carga los hashes ya en Chroma para que reingestas incrementales no
    # rompan idempotencia tras un fetch limpio.
    if not args.dry_run:
        existing = vector_store.get(include=["documents"])
        for content in existing.get("documents") or []:
            seen_hashes.add(_chunk_hash(content))
        if seen_hashes:
            LOG.info("preloaded %d existing chunk hashes for dedupe", len(seen_hashes))

    for fp in files:
        try:
            doc = json.loads(fp.read_text("utf-8"))
        except Exception as e:
            LOG.error("skip %s: %s", fp.name, e)
            continue
        # La llamada al embedder ocurre dentro de add_documents (sync). El
        # cliente HTTP de OllamaEmbeddings es bloqueante, así que ejecutamos
        # _ingest_one en un thread para no bloquear el event loop si el
        # script crece y se le piden cosas en paralelo.
        kind, n = await asyncio.to_thread(
            _ingest_one, vector_store, splitter, doc, args.dry_run, seen_hashes
        )
        counts[kind] = counts.get(kind, 0) + 1
        total_chunks += n
        LOG.info("%-13s %s (%d chunks)", kind, doc["url"], n)

    LOG.info("summary: %s | total_chunks_written=%d", counts, total_chunks)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", help="substring filter on raw file content/url")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
