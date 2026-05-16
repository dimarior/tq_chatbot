from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen3:8b"
    # Modelo opcional para el nodo `classify` del grafo. Si queda vacío,
    # cae al llm_model. Útil para bajar a qwen3:1.7b y acelerar el routing.
    llm_router_model: str = ""

    embed_model: str = "qwen3-embedding:0.6b"

    # Archivo SQLite donde viven conversations/messages (UI) Y los
    # checkpoints de LangGraph (memoria del grafo). Un solo archivo, dos
    # conjuntos de tablas. Borrar este archivo resetea todo el estado del
    # backend (excepto Chroma, que vive aparte en chroma_path).
    sqlite_path: str = "./tq.db"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:8000,http://localhost:3000"

    top_k: int = 6
    # Score mínimo (0–1, mayor = más similar) para considerar un chunk
    # relevante. El retriever transforma la distancia L2 de Chroma a
    # 1/(1+L2), así que esta escala NO es similitud coseno: hay que
    # recalibrar mirando los scores reales del corpus tras cada reingest.
    # 0.40 es un punto de partida; ajustar según los logs de retrieve().
    min_score: float = 0.40
    chunk_size: int = 600
    chunk_overlap: int = 100
    max_context_chars: int = 6000

    chroma_path: str = "./chroma_db"

    # LangSmith tracing — sólo se activa cuando langsmith_tracing=true Y
    # langsmith_api_key está poblada. Los vars con prefijo LANGSMITH_ son los
    # nombres canónicos que langgraph/langchain leen por sí solos; este
    # Settings los re-exporta a os.environ desde el lifespan para que el
    # cliente de tracing los recoja antes de que se importe cualquier nodo
    # del grafo.
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "tq-chatbot"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def router_model(self) -> str:
        return self.llm_router_model.strip() or self.llm_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
