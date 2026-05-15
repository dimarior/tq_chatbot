"""Nodos del grafo TQ-Asistente.

Cuatro nodos:
  * classify_node — LLM decide structured vs rag (with_structured_output).
  * structured_node — get_structured_data + source sintético.
  * retrieve_node — similarity search sobre Chroma + Source[] reales.
  * generate_node — ChatOllama.astream con el prompt y el historial.

El retrieve_node usa el mismo Chroma del app.state (sin envolver en un
BaseRetriever custom): vector_store.similarity_search_with_score es la API
ya off-the-shelf de LangChain.
"""
from __future__ import annotations

from dataclasses import dataclass

from langchain_community.vectorstores import Chroma
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from apps.api.core.config import Settings
from apps.api.graph.llm import make_chat_llm, make_router_llm
from apps.api.graph.state import ChatState, RouteDecision
from apps.api.rag.corpus_stats import CorpusStats
from apps.api.rag.prompt import SYSTEM_PROMPT, build_user_prompt
from apps.api.schemas import RetrievedChunk, Source
from apps.api.tools.structured_tool import get_structured_data


ROUTER_SYSTEM = (
    "Eres el clasificador del router del agente TQ-Asistente de Tecnoquímicas S.A.\n"
    "Decide entre dos herramientas según la pregunta del usuario:\n"
    "  - 'structured': datos exactos y verificados (teléfono, horario, NIT,\n"
    "    razón social, dirección de sedes, lista de marcas, portal de empleo,\n"
    "    línea ética).\n"
    "  - 'rag': preguntas abiertas sobre historia, productos en detalle,\n"
    "    sostenibilidad, ciencia médica, cultura corporativa, valores, o "
    "    cualquier tema que requiera comprensión del corpus indexado.\n"
    "Responde sólo con la clasificación; no expliques tu decisión."
)

STRUCTURED_RESPONSE_SYSTEM = (
    "Eres TQ-Asistente, el agente oficial de Tecnoquímicas S.A.\n"
    "Responde de forma directa, clara y profesional en español.\n"
    "Presenta la información de forma ordenada. Máximo 4 oraciones."
)

# Source sintético — el frontend lo muestra como una fuente más en el footer.
_STRUCTURED_SOURCE = Source(
    url="datos_estructurados.json",
    title="Datos oficiales TQ (herramienta estructurada)",
    score=1.0,
)


@dataclass
class GraphDeps:
    """Dependencias inyectadas a los nodos.

    LangGraph no inyecta servicios; las exponemos vía closures en build_graph.
    Tener un contenedor explícito mantiene los nodos testeables y declara qué
    necesita cada uno (settings, vector_store, corpus_stats).
    """

    settings: Settings
    vector_store: Chroma
    corpus_stats: CorpusStats


def make_classify_node(deps: GraphDeps):
    router_llm = make_router_llm(deps.settings).with_structured_output(RouteDecision)

    async def classify_node(state: ChatState) -> dict:
        decision: RouteDecision = await router_llm.ainvoke(
            [
                SystemMessage(content=ROUTER_SYSTEM),
                HumanMessage(content=state["question"]),
            ]
        )
        return {"route": decision.route}

    return classify_node


def make_structured_node(deps: GraphDeps):
    async def structured_node(state: ChatState) -> dict:
        data = get_structured_data(state["question"])
        context = (
            f"Información disponible sobre Tecnoquímicas:\n\n{data}\n\n"
            "Responde de forma directa usando la información anterior."
        )
        return {"context": context, "sources": [_STRUCTURED_SOURCE]}

    return structured_node


def _l2_to_similarity(distance: float) -> float:
    return 1.0 / (1.0 + distance)


def make_retrieve_node(deps: GraphDeps):
    async def retrieve_node(state: ChatState) -> dict:
        # Chroma's similarity_search_with_score es síncrono en langchain-community
        # (no expone variante async). El embed de la query bloquea brevemente.
        docs_with_scores = deps.vector_store.similarity_search_with_score(
            state["question"], k=deps.settings.top_k
        )
        chunks: list[RetrievedChunk] = []
        for doc, distance in docs_with_scores:
            meta = doc.metadata or {}
            url = meta.get("url")
            document_id = meta.get("document_id")
            chunk_index = meta.get("chunk_index")
            if not url or document_id is None or chunk_index is None:
                continue
            score = _l2_to_similarity(float(distance))
            if score < deps.settings.min_score:
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

        context = build_user_prompt(
            state["question"],
            chunks,
            deps.settings.max_context_chars,
            corpus_note=deps.corpus_stats.as_prompt_note(),
        )
        sources = [Source(url=c.url, title=c.title, score=c.score) for c in chunks]
        return {"context": context, "sources": sources}

    return retrieve_node


def make_generate_node(deps: GraphDeps):
    async def generate_node(state: ChatState) -> dict:
        # El system prompt difiere entre ramas — RAG carga las reglas pesadas
        # (citas, protocolo TOTAL/PARCIAL/NULA/SENSIBLE); la rama estructurada
        # es más liviana porque la herramienta ya garantizó precisión.
        system = (
            STRUCTURED_RESPONSE_SYSTEM
            if state.get("route") == "structured"
            else SYSTEM_PROMPT
        )
        # `messages` viene del checkpointer; prepend como historial antes del
        # prompt cargado (que ya contiene la pregunta + contexto).
        history = state.get("messages") or []
        # Cada invocación del grafo construye un ChatOllama con la temperatura
        # del turno. ChatOllama es barato de instanciar (configura un cliente
        # HTTP, no carga modelos), así esto NO penaliza performance.
        chat_llm = make_chat_llm(deps.settings)
        prompt_messages = [
            SystemMessage(content=system),
            *history,
            HumanMessage(content=state["context"]),
        ]

        chunks: list[str] = []
        async for chunk in chat_llm.astream(prompt_messages):
            piece = chunk.content if isinstance(chunk.content, str) else ""
            if piece:
                chunks.append(piece)
        full = "".join(chunks)
        # Persistimos el turno completo en el state: add_messages dedupea, así
        # el próximo turno del mismo thread_id ve esta respuesta más la
        # pregunta original.
        return {
            "messages": [
                HumanMessage(content=state["question"]),
                AIMessage(content=full),
            ]
        }

    return generate_node


def route_branch(state: ChatState) -> str:
    """Conditional edge — mapea state['route'] al nodo siguiente."""
    return "structured" if state.get("route") == "structured" else "rag"
