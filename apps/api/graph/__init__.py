"""LangGraph orchestration para el agente TQ-Asistente.

Reemplaza el `if needs_structured_tool(...) else retrieve(...)` hand-rolled
por un StateGraph con cuatro nodos (classify / structured / retrieve /
generate) y memoria por hilo vía AsyncPostgresSaver. La superficie pública
es `build_graph(...)`.

Motivación: requisito del profesor de usar herramientas existentes para
monitoreo. LangSmith traza automáticamente cada nodo del grafo y cada
primitivo LangChain dentro de ellos, sin instrumentación manual.
"""
from __future__ import annotations

from apps.api.graph.build import build_graph

__all__ = ["build_graph"]
