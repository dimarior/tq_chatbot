"""Nodos del grafo TQ-Asistente.

Cinco nodos:
  * classify_node — LLM decide direct vs structured vs rag, tomando en cuenta
    el historial reciente del hilo (no sólo la pregunta actual).
  * direct_node — sin recuperación, sin herramienta; el LLM responde desde
    el historial. Para follow-ups, aclaraciones y conversación social.
  * structured_node — get_structured_data + source sintético.
  * retrieve_node — similarity search sobre Chroma + Source[] reales.
  * generate_node — ChatOllama.astream con el system prompt apropiado al ruta.

El retrieve_node usa la misma transformación 1/(1+L2) que ya documentaba
apps/api/rag/retriever.py, sólo que inline (acceso directo al vector_store
del app.state evita un nivel de indirección).
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
    "Eres el clasificador del router del agente TQ-Asistente de Tecnoquímicas "
    "S.A.\n\n"
    "Debajo está el historial reciente de la conversación (puede estar vacío "
    "en el primer turno) seguido de la NUEVA pregunta del usuario al final. "
    "Decide cuál herramienta disparar para responder esa NUEVA pregunta:\n\n"
    "- 'direct': la respuesta se puede dar SÓLO desde la conversación previa "
    "(referencia a turnos anteriores como '¿y por qué?', 'explícame eso', "
    "'¿cuál fue el segundo punto?'), O es una interacción social que no "
    "requiere datos del corpus (saludos, agradecimientos, despedidas, "
    "preguntas meta).\n"
    "- 'structured': la NUEVA pregunta pide un dato exacto y verificado "
    "(teléfono, horario, NIT, dirección de sedes, lista de marcas, línea "
    "ética, portal de empleo).\n"
    "- 'rag': la NUEVA pregunta requiere comprensión semántica del corpus "
    "(historia de la empresa, productos en detalle, ciencia médica, "
    "sostenibilidad, cultura corporativa).\n\n"
    "Responde con la clasificación; no expliques tu decisión."
)

# Cuántos mensajes recientes se le pasan al router. Acotamos para no inflar
# el context window del clasificador en hilos largos — la decisión 'direct'
# usualmente depende del último intercambio, no de toda la historia.
_ROUTER_HISTORY_WINDOW = 6

STRUCTURED_RESPONSE_SYSTEM = (
    "Eres TQ-Asistente, el agente oficial de Tecnoquímicas S.A.\n"
    "Responde de forma directa, clara y profesional en español.\n"
    "Presenta la información de forma ordenada. Máximo 4 oraciones."
)

DIRECT_SYSTEM = (
    "Eres TQ-Asistente, el agente oficial de Tecnoquímicas S.A.\n"
    "El usuario te hace una pregunta que se puede responder usando sólo la "
    "conversación previa (clarificación, referencia a turnos anteriores) o "
    "una interacción social (saludo, agradecimiento, despedida).\n"
    "Responde en español, breve y directo. NO inventes datos sobre "
    "Tecnoquímicas si no aparecieron en la conversación — si la pregunta "
    "requiere información que no tenés, pedile al usuario que reformule."
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
        # Pasamos el historial reciente al router para que pueda decidir
        # 'direct' cuando la pregunta refiere a turnos anteriores.
        history = state.get("messages") or []
        recent = history[-_ROUTER_HISTORY_WINDOW:]
        decision: RouteDecision = await router_llm.ainvoke(
            [
                SystemMessage(content=ROUTER_SYSTEM),
                *recent,
                HumanMessage(content=state["question"]),
            ]
        )
        return {"route": decision.route}

    return classify_node


def make_direct_node(deps: GraphDeps):
    async def direct_node(state: ChatState) -> dict:
        # No retrieval, no herramienta. El LLM contesta con la historia que
        # ya tiene en state["messages"] (cargada por el checkpointer).
        # `context` se setea a la pregunta cruda para que generate_node la use
        # como HumanMessage final, sin envolverla en bloques de contexto.
        return {"context": state["question"], "sources": []}

    return direct_node


def make_structured_node(deps: GraphDeps):
    async def structured_node(state: ChatState) -> dict:
        data = get_structured_data(state["question"])
        context = (
            f"Información disponible sobre Tecnoquímicas:\n\n{data}\n\n"
            f"Pregunta del usuario: {state['question']}\n\n"
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


def _system_for_route(route: str | None) -> str:
    if route == "structured":
        return STRUCTURED_RESPONSE_SYSTEM
    if route == "direct":
        return DIRECT_SYSTEM
    # RAG es el default — carga las reglas pesadas (citas, protocolo
    # TOTAL/PARCIAL/NULA/SENSIBLE) porque la respuesta sale del corpus.
    return SYSTEM_PROMPT


def make_generate_node(deps: GraphDeps):
    async def generate_node(state: ChatState) -> dict:
        system = _system_for_route(state.get("route"))
        # `messages` viene del checkpointer; prepend como historial antes
        # del HumanMessage cargado (`context` ya incluye la pregunta o un
        # bloque que la engloba).
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
    route = state.get("route")
    if route == "structured":
        return "structured"
    if route == "direct":
        return "direct"
    return "rag"
