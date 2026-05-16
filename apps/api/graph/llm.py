"""Factories para los ChatOllama usados por el grafo.

Dos personalidades:
  * `make_chat_llm`: streaming de respuesta final con la afinación que ya
    usaba OllamaClient (num_ctx=8192, reasoning=False). La temperatura se
    pasa por turno desde el SettingsPanel del frontend.
  * `make_router_llm`: clasificador determinista (temperature=0) que devuelve
    un RouteDecision vía with_structured_output.

`reasoning=False` es el equivalente del `think:False` que usaba OllamaClient
— desactiva los tokens internos de Qwen3 que rompían el streaming SSE.
"""
from __future__ import annotations

from langchain_ollama import ChatOllama

from apps.api.core.config import Settings


def make_chat_llm(settings: Settings, temperature: float = 0.2) -> ChatOllama:
    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_host,
        temperature=temperature,
        num_ctx=8192,
        reasoning=False,
    )


def make_router_llm(settings: Settings) -> ChatOllama:
    return ChatOllama(
        model=settings.router_model,
        base_url=settings.ollama_host,
        temperature=0.0,
        num_ctx=2048,
        reasoning=False,
    )
