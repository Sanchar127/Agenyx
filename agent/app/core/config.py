from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agenyx Agent Runtime"
    environment: str = "development"
    debug: bool = False

    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen2.5:7b"

    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 2

    agent_max_steps: int = 8

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENTYX_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
