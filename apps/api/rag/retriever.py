"""Retrieval sobre Chroma con filtro de similitud.

Chroma's `similarity_search_with_score` devuelve distancia L2 (cero = idéntico,
crece con disimilitud). La transformamos a un score 0–1 donde 1 es perfecto
vía `1 / (1 + L2)` para mantener la semántica de `min_score >= umbral` que
ya usan el filtro de chips de fuentes y el prompt builder. Esa transformación
no es la similitud coseno real — al cambiar de embedding o reingestar, hay
que recalibrar `settings.min_score` mirando los scores reales que produce el
corpus (ver health endpoint / logs).
"""
from __future__ import annotations

from langchain_community.vectorstores import Chroma

from apps.api.schemas import RetrievedChunk


def _l2_to_similarity(distance: float) -> float:
    """L2 distance → score 0-1 (1 = idéntico, → 0 a medida que crece)."""
    return 1.0 / (1.0 + distance)


async def retrieve(
    vector_store: Chroma,
    query: str,
    k: int = 6,
    min_score: float = 0.50,
) -> list[RetrievedChunk]:
    """Top-k chunks por similitud, filtrados por min_score.

    Nota: `similarity_search_with_score` es síncrono en langchain-community;
    se llama directo (la llamada HTTP a Ollama por el embed de la query es
    bloqueante pero rápida — el cliente Chroma no expone variante async).
    """
    docs_with_scores = vector_store.similarity_search_with_score(query, k=k)

    chunks: list[RetrievedChunk] = []
    for doc, distance in docs_with_scores:
        meta = doc.metadata or {}
        url = meta.get("url")
        document_id = meta.get("document_id")
        chunk_index = meta.get("chunk_index")
        if not url or document_id is None or chunk_index is None:
            continue

        score = _l2_to_similarity(float(distance))
        if score < min_score:
            continue

        chunks.append(
            RetrievedChunk(
                document_id=int(document_id),
                chunk_index=int(chunk_index),
                content=doc.page_content,
                url=url,
                title=meta.get("title"),
                score=score,
            )
        )
    return chunks
