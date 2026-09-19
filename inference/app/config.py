from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration."""

    app_name: str = "agenyx-inference"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    log_json: bool = True

    # -----------------------------------------------------
    # Provider configuration
    # -----------------------------------------------------

    # Comma-separated provider names in priority order.
    #
    # Example:
    #
    # INFERENCE_PROVIDER_NAMES=ollama-local,vllm-local,openai
    #
    provider_names: str = "ollama-local"

    # -----------------------------------------------------
    # Model configuration
    # -----------------------------------------------------

    # Comma-separated model-to-provider mappings.
    #
    # Format:
    #
    # model_id=provider_name
    #
    # Example:
    #
    # INFERENCE_MODEL_DEFINITIONS=qwen2.5:7b=ollama-local,llama3.2:3b=ollama-local
    #
    model_definitions: str = (
        "qwen2.5:7b=ollama-local,"
        "llama3.2:3b=ollama-local"
    )

    # Used when a client does not explicitly provide "model".
    default_model: str = "qwen2.5:7b"

    # -----------------------------------------------------
    # Provider backend defaults
    # -----------------------------------------------------

    # Default OpenAI-compatible backend configuration.
    #
    # Currently shared by configured providers.
    # Per-provider backend configuration will be introduced
    # separately.
    backend_base_url: str = "http://localhost:11434/v1"

    backend_api_key: str = "ollama"

    service_api_key: str = ""
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

    # -----------------------------------------------------
    # OpenTelemetry
    # -----------------------------------------------------

    otel_service_name: str = "agenyx-inference"

    otel_service_namespace: str = "agenyx"

    otel_exporter_otlp_endpoint: str = (
        "http://agenyx-otel-collector.monitoring.svc.cluster.local:4317"
    )

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

    @property
    def models(self) -> list[tuple[str, str]]:
        """
        Return configured model-to-provider mappings.

        Each mapping has the form:

            (model_id, provider_name)
        """

        models: list[tuple[str, str]] = []

        for definition in self.model_definitions.split(","):
            definition = definition.strip()

            if not definition:
                continue

            model_id, separator, provider_name = definition.partition("=")

            if not separator:
                raise ValueError(
                    "Invalid model definition "
                    f"'{definition}'; expected 'model_id=provider_name'"
                )

            model_id = model_id.strip()
            provider_name = provider_name.strip()

            if not model_id:
                raise ValueError(
                    "Model definition contains an empty model_id"
                )

            if not provider_name:
                raise ValueError(
                    "Model definition contains an empty provider_name"
                )

            models.append(
                (model_id, provider_name)
            )

        return models


@lru_cache
def get_settings() -> Settings:
    """
    Return cached application settings.
    """

    return Settings()
