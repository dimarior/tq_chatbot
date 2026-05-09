from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen3:8b"

    embed_backend: str = "ollama"
    embed_model: str = "qwen3-embedding:0.6b"
    embed_dims: int = 1024
    embed_timeout: int = 120

    database_url: str = "postgresql://tq:tq@localhost:5432/tq"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:8000"

    top_k: int = 6
    chunk_size: int = 600
    chunk_overlap: int = 100
    max_context_chars: int = 6000

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
