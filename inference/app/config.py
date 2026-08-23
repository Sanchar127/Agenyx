from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "agenyx-inference"
    app_version: str = "0.1.0"

    backend_base_url: str = "http://localhost:11434/v1"

    backend_api_key: str = "ollama"
    max_retries: int = 2
    request_timeout_seconds: float = 120.0

    max_connections: int = 100
    max_keepalive_connections: int = 20

    model: str = "qwen2.5:7b"

    model_config = SettingsConfigDict(
        env_prefix="INFERENCE_",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
