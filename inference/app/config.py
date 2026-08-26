from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration."""

    app_name: str = "agenyx-inference"
    app_version: str = "0.1.0"

    # -----------------------------------------------------
    # Provider configuration
    # -----------------------------------------------------

    # Ordered provider priority for provider-level failover.
    #
    # Example:
    #
    # INFERENCE_PROVIDER_NAMES=ollama-local,openai,groq
    #
    provider_names: str = "ollama-local"

    # -----------------------------------------------------
    # Default model
    # -----------------------------------------------------

    # Used when a client does not explicitly provide "model".
    default_model: str = "qwen2.5:7b"

    # -----------------------------------------------------
    # Default backend
    # -----------------------------------------------------

    backend_base_url: str = (
        "http://localhost:11434/v1"
    )

    backend_api_key: str = "ollama"

    # -----------------------------------------------------
    # HTTP / retry configuration
    # -----------------------------------------------------

    max_retries: int = 2

    request_timeout_seconds: float = 120.0

    max_connections: int = 100

    max_keepalive_connections: int = 20

    # -----------------------------------------------------
    # Failover
    # -----------------------------------------------------

    max_failover_attempts: int = 3

    model_config = SettingsConfigDict(
        env_prefix="INFERENCE_",
        case_sensitive=False,
    )

    @property
    def providers(self) -> list[str]:
        """
        Return configured provider names in priority order.
        """

        return [
            name.strip()
            for name in self.provider_names.split(",")
            if name.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    """
    Return cached application settings.
    """

    return Settings()
