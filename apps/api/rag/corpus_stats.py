"""Estadísticas agregadas del corpus indexado.

El RAG sólo "ve" los top-k chunks recuperados por similitud — no puede
responder preguntas de conteo ("¿cuántos artículos científicos hay?") porque
son agregadas, no semánticas. Este módulo calcula esos totales recorriendo
la metadata de la colección Chroma y los inyecta como un hecho en el prompt
(ver apps/api/rag/prompt.py).

Se computa una sola vez al arranque del API (`compute_corpus_stats` en
lifespan) y se cachea en `app.state.corpus_stats` hasta el siguiente
reinicio.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_community.vectorstores import Chroma


# Las noticias científicas de tqfarma se reconocen por su path canónico
# (.../biblioteca-cientifica/noticias-actualidad/<especialidad>/<slug>), que
# el fetch garantiza vía _NEWS_PATH_RE en scripts/tqfarma_news.py. El path
# sobrevive intacto en la metadata de cada chunk.
_NEWS_URL_RE = re.compile(r"/biblioteca-cientifica/noticias-actualidad/([^/]+)/[^/]+")


def _prettify(slug: str) -> str:
    return slug.replace("-", " ").strip().capitalize()


@dataclass(frozen=True)
class CorpusStats:
    news_total: int
    news_by_specialty: dict[str, int]

    def as_prompt_note(self) -> str:
        """Texto que se inyecta en el bloque <datos_del_corpus> del prompt.

        Cadena vacía cuando no hay noticias indexadas — así el router no
        inyecta un bloque engañoso si el corpus aún no se ha ingestado.
        """
        if self.news_total <= 0:
            return ""
        note = (
            f"La biblioteca científica de tqfarma indexada en esta base de "
            f"conocimiento contiene {self.news_total} resúmenes de noticias y "
            f"artículos científicos"
        )
        if self.news_by_specialty:
            partes = ", ".join(
                f"{_prettify(s)} ({n})" for s, n in self.news_by_specialty.items()
            )
            note += (
                f", distribuidos en {len(self.news_by_specialty)} especialidades "
                f"médicas: {partes}"
            )
        return note + "."


def compute_corpus_stats(vector_store: Chroma) -> CorpusStats:
    """Cuenta URLs únicas de noticias por especialidad en la colección."""
    rows = vector_store.get(include=["metadatas"])
    metadatas = rows.get("metadatas") or []
    # Un documento se puede haber dividido en muchos chunks; dedup por URL.
    seen_urls: set[str] = set()
    by_specialty: dict[str, int] = {}
    for md in metadatas:
        url = (md or {}).get("url")
        if not url or url in seen_urls:
            continue
        match = _NEWS_URL_RE.search(url)
        if not match:
            continue
        seen_urls.add(url)
        specialty = match.group(1)
        by_specialty[specialty] = by_specialty.get(specialty, 0) + 1
    # Orden estable: especialidades con más artículos primero.
    by_specialty = dict(
        sorted(by_specialty.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    return CorpusStats(news_total=len(seen_urls), news_by_specialty=by_specialty)
