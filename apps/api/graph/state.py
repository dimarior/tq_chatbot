"""Estado del grafo y modelo Pydantic para la decisión del router.

`ChatState` es lo que persiste el checkpointer entre invocaciones del mismo
thread_id. El campo `messages` lleva el historial completo y se acumula
automáticamente vía el reductor `add_messages` — eso da memoria al asistente
sin que el cliente vuelva a mandar history.
"""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from apps.api.schemas import Source


Route = Literal["direct", "structured", "rag"]


class RouteDecision(BaseModel):
    """Salida estructurada del clasificador del router.

    Pydantic + ChatOllama.with_structured_output garantiza que el LLM
    responda exactamente uno de los tres valores. Cualquier otra cosa la
    captura el validador.
    """

    route: Route = Field(
        ...,
        description=(
            "'direct' si la pregunta se puede responder usando sólo la "
            "conversación previa (referencias a turnos anteriores, "
            "aclaraciones) o es una interacción social que no requiere datos "
            "del corpus (saludos, agradecimientos, despedidas). "
            "'structured' si pide un dato concreto y verificado (teléfono, "
            "horario, NIT, dirección, marcas, línea ética, portal de empleo). "
            "'rag' si requiere comprensión semántica del corpus (historia, "
            "productos en detalle, sostenibilidad, ciencia, cultura)."
        ),
    )


class ChatState(TypedDict, total=False):
    # Entrada del turno actual. Lo setea el endpoint antes de invocar el grafo.
    question: str
    # Historial acumulado por el checkpointer. add_messages dedupea por id.
    messages: Annotated[list[BaseMessage], add_messages]
    # Decisión del router para este turno.
    route: Route
    # Fuentes a emitir vía SSE (chunks RAG o source sintético de la herramienta).
    sources: list[Source]
    # Bloque de contexto que se inyecta en el prompt del nodo generate.
    context: str
    # Parámetros por turno provenientes del SettingsPanel del frontend.
    # No se persisten en el checkpoint del próximo turno (se sobreescriben
    # en cada invocación), pero viven en el state para que retrieve_node y
    # generate_node los consuman sin depender de los defaults globales.
    temperature: float
    top_k: int
