from __future__ import annotations

from apps.api.schemas import RetrievedChunk
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from apps.api.rag.langchain_retriever import retrieve as langchain_retrieve


async def retrieve(
    vector_store: Chroma,
    ollama_embedder: OllamaEmbeddings,
    query: str,
    k: int = 6,
    min_score: float = 0.50,
) -> list[RetrievedChunk]:
    return await langchain_retrieve(vector_store, ollama_embedder, query, k, min_score)
