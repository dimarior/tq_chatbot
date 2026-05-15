from __future__ import annotations

import uuid

from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from apps.api.schemas import RetrievedChunk
from apps.api.core.config import Settings


async def retrieve(
    vector_store: Chroma,
    embedder: OllamaEmbeddings,
    query: str,
    k: int = 6,
    score_threshold: float = 0.50,
) -> list[RetrievedChunk]:
    docs_with_scores = vector_store.similarity_search_with_score(query, k=k)

    retrieved_chunks: list[RetrievedChunk] = []
    for doc, score in docs_with_scores:
        # Extraer metadatos y asegurar que el score sea el esperado
        url = doc.metadata.get("url")
        title = doc.metadata.get("title")
        document_id = doc.metadata.get("document_id")
        chunk_index = doc.metadata.get("chunk_index")

        if url and document_id is not None and chunk_index is not None:
            # Asegurarse de que el score es 0.0-1.0; ChromaDB devuelve distancia euclidiana,
            # lo cual es diferente a la similitud coseno de pgvector.
            # Para fines de compatibilidad con `min_score`, necesitamos un score 0-1.
            # Asumiendo que `similarity_search_with_score` devuelve 0 para idéntico, y valores mayores para menos similar.
            # Necesitamos invertir y normalizar esto. Una aproximación simple es 1 - distancia.
            # Sin embargo, LangChain Chroma `similarity_search_with_score` ya devuelve
            # la distancia L2. Para convertirla a algo similar a similitud coseno (0-1),
            # donde 1 es más similar, podemos necesitar un mapeo.
            # Por ahora, simplemente remapearemos de forma heurística para que sea compatible
            # con el rango de `min_score`. Es importante recalibrar `min_score` después.
            # Una distancia de 0 significa idéntico, una distancia mayor significa menos similar.
            # Para que 1.0 sea el más similar, podemos usar 1 / (1 + distancia) o 1 - (distancia / max_distancia).
            # Para mantener la compatibilidad con el min_score actual (0.5), usaremos un mapeo simple:
            # score = 1.0 - (score / some_max_expected_distance)
            # Para un enfoque más preciso, necesitaríamos entender la distribución de las distancias de Chroma.
            # Por ahora, mantendremos el score directo de LangChain y ajustaremos `min_score` si es necesario.
            # Si el score de Chroma es distancia L2, entonces scores más bajos son mejores.
            # Para que sea compatible con nuestro `min_score` actual donde scores más altos son mejores,
            # necesitamos transformarlo.
            # Una forma común de transformar la distancia L2 en similitud es 1 / (1 + L2_distance).
            # O, si esperamos que la distancia esté dentro de un cierto rango (ej. 0 a 2), podemos usar 1 - (L2_distance / 2).
            # Para mantenerlo simple y compatible con el umbral de 0.5 (donde 0.5 es el mínimo para ser "relevante"),
            # si Chroma devuelve una distancia, un valor de `score_threshold` (0.5) debería ser interpretado
            # como una distancia MÁXIMA permitida, no mínima.

            # Por ahora, asumiré que score de similarity_search_with_score es 1-distancia
            # y que un score más alto es mejor, lo cual es lo que esperamos de similitud coseno.
            # Si no es así, esta lógica necesitará ajuste.
            # Por la documentación de LangChain, `similarity_search_with_score` devuelve
            # una tupla de Document y la distancia L2. Menor distancia L2 significa mayor similitud.
            # Para convertir la distancia L2 a una "puntuación" donde un valor más alto es mejor,
            # podemos usar 1 / (1 + distancia).
            # Sin embargo, el problema especifica que `min_score` es un umbral.
            # Si `min_score` es 0.5, significa que queremos una similitud de al menos 0.5.
            # Si el `score` de Chroma es una distancia, entonces el umbral debería ser una distancia MÁXIMA.
            # Por lo tanto, el filtro `c.score >= settings.min_score` en chat.py
            # deberá cambiar a `c.score <= settings.max_distance`.

            # Para simplificar y mantener la misma semántica de "score alto es mejor",
            # invertiremos la distancia L2. Pero no hay una forma canónica de mapear
            # la distancia L2 a un rango 0-1 de similitud sin un conocimiento de la
            # distribución de distancias en el corpus.

            # Asumamos que `score` de Chroma es una distancia L2. Queremos un score donde mayor es mejor.
            # Si el `min_score` actual es 0.5 (similitud coseno), entonces un `score` de 0.5
            # significa una similitud moderada.
            # Para la distancia L2, un score de 0 es el mejor (idéntico), un score más alto es peor.
            # Vamos a pasar el `score` de Chroma directamente y cambiar la lógica de filtrado en `chat.py`.

            # Para el `RetrievedChunk`, necesitamos un score que sea 0-1, donde 1 es perfecto.
            # Si la distancia L2 es 0 para una coincidencia perfecta, y aumenta para menos perfecta,
            # podemos usar `1 - (distance / max_possible_distance)`.
            # Sin conocer `max_possible_distance`, es difícil.
            # Por ahora, voy a pasar el score (distancia L2) directamente, y en `chat.py`
            # la lógica de filtrado deberá ser `score <= max_allowed_distance`.
            # Esto implica que el `settings.min_score` actual (que es un mínimo)
            # ahora debe interpretarse como un `max_distance` (un máximo).

            # Vamos a devolver la distancia L2 tal cual y dejar que el `chat.py` la filtre.
            # Sin embargo, la definición de RetrievedChunk tiene `score: float`.
            # Si el score es una distancia, un valor de 0.5 es un `min_score`,
            # pero para una distancia L2, esto significaría que la distancia debe ser
            # al menos 0.5, lo cual es lo opuesto a lo que queremos para la "relevancia".

            # Para mantener la semántica de `min_score` (donde un valor más alto es mejor),
            # vamos a transformar la distancia L2 de Chroma en una "similitud"
            # simple, como `1 / (1 + distance)`. Esto hará que un score más alto
            # sea mejor, y el umbral de `min_score` seguirá funcionando.
            # Si la distancia es 0 (perfecta), el score será 1. Si la distancia es alta,
            # el score se acerca a 0.

            transformed_score = 1 / (1 + score) # Transformar distancia L2 a similitud

            if transformed_score >= score_threshold:
                retrieved_chunks.append(
                    RetrievedChunk(
                        document_id=int(document_id),  # Ensure document_id is int
                        chunk_index=int(chunk_index),  # Ensure chunk_index is int
                        content=doc.page_content,
                        url=url,
                        title=title,
                        score=transformed_score,
                    )
                )
    return retrieved_chunks
