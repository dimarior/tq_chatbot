"""Estadísticas agregadas del corpus indexado.

El RAG sólo "ve" los top-k chunks recuperados por similitud — no puede
responder preguntas de conteo ("¿cuántos artículos científicos hay?") porque
son agregadas, no semánticas. Este módulo calcula esos totales con un COUNT
directo para inyectarlos como un hecho en el prompt. Ver apps/api/rag/prompt.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import asyncpg


# Las noticias científicas de tqfarma se reconocen por su path canónico
# (.../biblioteca-cientifica/noticias-actualidad/<especialidad>/<slug>), que el
# fetch garantiza vía _NEWS_PATH_RE en scripts/tqfarma_news.py. Es una señal más
# fiable que el marcador de contenido: este último se pierde en el chunking
# (el bloque boilerplate es idéntico entre docs y el dedup de la ingesta lo
# colapsa), pero la URL sobrevive intacta en la tabla `documents`.
NEWS_URL_REGEX = r"/biblioteca-cientifica/noticias-actualidad/[^/]+/[^/]+"

_NEWS_TOTAL_SQL = "SELECT count(*) FROM documents WHERE url ~ $1"

# La especialidad es el 6º segmento del path canónico.
_NEWS_BY_SPECIALTY_SQL = """
SELECT split_part(url, '/', 6) AS specialty, count(*) AS n
FROM documents
WHERE url ~ $1
GROUP BY specialty
ORDER BY n DESC
"""


def _prettify(slug: str) -> str:
    return slug.replace("-", " ").strip().capitalize()


@dataclass(frozen=True)
class CorpusStats:
    news_total: int
    news_by_specialty: dict[str, int]

    def as_prompt_note(self) -> str:
        """Texto que se inyecta en el bloque <datos_del_corpus> del prompt.

        Cadena vacía cuando no hay noticias indexadas — así el router no inyecta
        un bloque engañoso si el corpus aún no se ha ingestado.
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


async def compute_corpus_stats(pool: asyncpg.Pool) -> CorpusStats:
    async with pool.acquire() as conn:
        total = await conn.fetchval(_NEWS_TOTAL_SQL, NEWS_URL_REGEX) or 0
        rows = await conn.fetch(_NEWS_BY_SPECIALTY_SQL, NEWS_URL_REGEX)
    by_specialty = {r["specialty"]: r["n"] for r in rows if r["specialty"]}
    return CorpusStats(news_total=int(total), news_by_specialty=by_specialty)
