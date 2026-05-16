"""Ensambla el StateGraph y lo compila con el checkpointer."""
from __future__ import annotations

from langchain_community.vectorstores import Chroma
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from apps.api.core.config import Settings
from apps.api.graph.nodes import (
    GraphDeps,
    make_classify_node,
    make_direct_node,
    make_generate_node,
    make_retrieve_node,
    make_structured_node,
    route_branch,
)
from apps.api.graph.state import ChatState
from apps.api.rag.corpus_stats import CorpusStats


def build_graph(
    settings: Settings,
    vector_store: Chroma,
    corpus_stats: CorpusStats,
    checkpointer: BaseCheckpointSaver,
):
    deps = GraphDeps(
        settings=settings,
        vector_store=vector_store,
        corpus_stats=corpus_stats,
    )

    builder = StateGraph(ChatState)
    builder.add_node("classify", make_classify_node(deps))
    builder.add_node("direct", make_direct_node(deps))
    builder.add_node("structured", make_structured_node(deps))
    builder.add_node("retrieve", make_retrieve_node(deps))
    builder.add_node("generate", make_generate_node(deps))

    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        route_branch,
        {"direct": "direct", "structured": "structured", "rag": "retrieve"},
    )
    builder.add_edge("direct", "generate")
    builder.add_edge("structured", "generate")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)

    return builder.compile(checkpointer=checkpointer)
