from __future__ import annotations

import asyncpg

from apps.api.rag.embeddings import Embedder
from apps.api.schemas import RetrievedChunk


_SEARCH_SQL = """
SELECT
    c.document_id,
    c.chunk_index,
    c.content,
    d.url,
    d.title,
    1 - (c.embedding <=> $1::vector) AS score
FROM chunks c
JOIN documents d ON d.id = c.document_id
ORDER BY c.embedding <=> $1::vector
LIMIT $2
"""


def _vector_literal(vec: list[float]) -> str:
    # pgvector accepts the textual form '[v1,v2,...]'.
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"


async def retrieve(
    pool: asyncpg.Pool,
    embedder: Embedder,
    query: str,
    k: int = 6,
) -> list[RetrievedChunk]:
    [vec] = await embedder.embed([query])
    lit = _vector_literal(vec)
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SEARCH_SQL, lit, k)
    return [
        RetrievedChunk(
            document_id=r["document_id"],
            chunk_index=r["chunk_index"],
            content=r["content"],
            url=r["url"],
            title=r["title"],
            score=float(r["score"]),
        )
        for r in rows
    ]
