"""Idempotent ingestion: data/raw/*.json → embeddings → Postgres+pgvector.

Per-document flow:
  - Look up `documents.url`. If row exists with the same `content_hash`, skip.
  - Otherwise, in a single transaction:
        * UPSERT documents row.
        * DELETE FROM chunks WHERE document_id = ?.
        * Split text → embed → bulk-INSERT new chunks.

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
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
from langchain_text_splitters import RecursiveCharacterTextSplitter

from apps.api.core.config import get_settings
from apps.api.rag.embeddings import build_embedder


LOG = logging.getLogger("ingest")

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"


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


async def _ingest_one(
    conn: asyncpg.Connection,
    embedder,
    splitter: RecursiveCharacterTextSplitter,
    doc: dict,
    dry_run: bool,
    seen_hashes: set[str],
) -> tuple[str, int]:
    url = doc["url"]
    existing_hash = await conn.fetchval("SELECT content_hash FROM documents WHERE url=$1", url)

    if existing_hash == doc["content_hash"]:
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

    embeddings = await embedder.embed(unique_chunks)

    async with conn.transaction():
        doc_id = await conn.fetchval(
            """
            INSERT INTO documents (url, source, title, content_hash, fetched_at, last_indexed_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (url) DO UPDATE
                SET source          = EXCLUDED.source,
                    title           = EXCLUDED.title,
                    content_hash    = EXCLUDED.content_hash,
                    fetched_at      = EXCLUDED.fetched_at,
                    last_indexed_at = EXCLUDED.last_indexed_at
            RETURNING id
            """,
            url,
            doc["source"],
            doc.get("title"),
            doc["content_hash"],
            datetime.fromisoformat(doc["fetched_at"]),
            datetime.now(timezone.utc),
        )
        await conn.execute("DELETE FROM chunks WHERE document_id=$1", doc_id)

        for i, (txt, vec) in enumerate(zip(unique_chunks, embeddings)):
            await conn.execute(
                """
                INSERT INTO chunks (document_id, chunk_index, content, embedding, metadata)
                VALUES ($1, $2, $3, $4::vector, $5::jsonb)
                """,
                doc_id,
                i,
                txt,
                _vector_literal(vec),
                json.dumps({"source": doc["source"]}),
            )

    return (("updated" if existing_hash else "inserted"), len(unique_chunks))


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    embedder = build_embedder(settings)
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

    conn = await asyncpg.connect(settings.database_url)
    try:
        counts = {"unchanged": 0, "inserted": 0, "updated": 0, "empty": 0,
                  "would-insert": 0, "would-update": 0}
        total_chunks = 0
        # Hashes vistos en esta corrida; evita reembedir/insertar el mismo chunk
        # en docs distintos (boilerplate del template, "Lo más leído", etc.).
        seen_hashes: set[str] = set()
        # Pre-carga hashes ya en BD para que reingestas incrementales no rompan
        # idempotencia con la versión limpia.
        if not args.dry_run:
            rows = await conn.fetch("SELECT content FROM chunks")
            for r in rows:
                seen_hashes.add(_chunk_hash(r["content"]))
            if seen_hashes:
                LOG.info("preloaded %d existing chunk hashes for dedupe", len(seen_hashes))

        for fp in files:
            try:
                doc = json.loads(fp.read_text("utf-8"))
            except Exception as e:
                LOG.error("skip %s: %s", fp.name, e)
                continue
            kind, n = await _ingest_one(conn, embedder, splitter, doc, args.dry_run, seen_hashes)
            counts[kind] = counts.get(kind, 0) + 1
            total_chunks += n
            LOG.info("%-13s %s (%d chunks)", kind, doc["url"], n)

        LOG.info("summary: %s | total_chunks_written=%d", counts, total_chunks)
        return 0
    finally:
        await embedder.aclose()
        await conn.close()


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
