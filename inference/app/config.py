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

    # Per-provider backend configuration.
    #
    # Format:
    #
    # provider_name=base_url|api_key
    #
    # Multiple providers are separated by commas.
    #
    # Example:
    #
    # ollama-local=http://localhost:11434/v1|ollama,
    # vllm-local=http://localhost:8001/v1|
    #
    provider_backends: str = (
        "ollama-local=http://localhost:11434/v1|ollama"
    )

    # Model-specific provider failover routes.
    #
    # Format:
    #
    # model_id=provider1,provider2
    #
    model_failover_routes: str = ""

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

    # max_inference_concurrency: int = 10

    max_concurrency: int = 10
    # -----------------------------------------------------
    # Failover
    # -----------------------------------------------------

    max_failover_attempts: int = 3

    # -----------------------------------------------------
    # Tenant model access
    # -----------------------------------------------------

    tenant_model_access: str = (
        "tenant-a=qwen2.5:7b, llama3.2:3b;"
        "tenant-b=llama3.2:3b"
    )

    # -----------------------------------------------------
    # Request validation / limits
    # -----------------------------------------------------

    max_request_body_bytes: int = 1_048_576

    max_messages: int = 100

    max_message_content_chars: int = 100_000

    max_total_message_content_chars: int = 500_000

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
        """Return configured provider names in priority order."""

        return [
            name.strip()
            for name in self.provider_names.split(",")
            if name.strip()
        ]

    @property
    def provider_backend_configs(self) -> dict[str, dict[str, str]]:
        """
        Return backend configuration for each provider.

        Format:

            provider_name=base_url|api_key
        """

        configs: dict[str, dict[str, str]] = {}

        for definition in self.provider_backends.split(","):
            definition = definition.strip()

            if not definition:
                continue

            provider_name, separator, backend = definition.partition("=")

            if not separator:
                raise ValueError(
                    "Invalid provider backend definition "
                    f"'{definition}'; "
                    "expected 'provider_name=base_url|api_key'"
                )

            provider_name = provider_name.strip()

            if not provider_name:
                raise ValueError(
                    "Provider backend definition contains "
                    "an empty provider_name"
                )

            base_url, separator, api_key = backend.partition("|")

            if not separator:
                raise ValueError(
                    "Invalid provider backend definition "
                    f"'{definition}'; "
                    "expected 'provider_name=base_url|api_key'"
                )

            base_url = base_url.strip()
            api_key = api_key.strip()

            if not base_url:
                raise ValueError(
                    "Provider backend definition contains "
                    "an empty base_url"
                )

            configs[provider_name] = {
                "base_url": base_url,
                "api_key": api_key,
            }

        return configs

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

    @property
    def model_failover_providers(self) -> dict[str, tuple[str, ...]]:
        """
        Return the ordered provider failover route for each model.

        Format:

            model_id=provider1,provider2
        """

        routes: dict[str, tuple[str, ...]] = {}

        for definition in self.model_failover_routes.split(";"):
            definition = definition.strip()

            if not definition:
                continue

            model_id, separator, providers = definition.partition("=")

            if not separator:
                raise ValueError(
                    "Invalid model failover definition "
                    f"'{definition}'; "
                    "expected 'model_id=provider1,provider2'"
                )

            model_id = model_id.strip()

            if not model_id:
                raise ValueError(
                    "Model failover definition contains "
                    "an empty model_id"
                )

            provider_names = tuple(
                provider.strip()
                for provider in providers.split(",")
                if provider.strip()
            )

            if not provider_names:
                raise ValueError(
                    f"Model '{model_id}' has no providers"
                )

            routes[model_id] = provider_names

        return routes

    @property
    def tenant_models(self) -> dict[str, frozenset[str]]:
        """Return the models each tenant is allowed to use."""

        access: dict[str, frozenset[str]] = {}

        for definition in self.tenant_model_access.split(";"):
            definition = definition.strip()

            if not definition:
                continue

            tenant_id, separator, models = definition.partition("=")

            if not separator:
                raise ValueError(
                    "Invalid tenant model definition "
                    f"'{definition}'; expected 'tenant_id=model1|model2'"
                )

            tenant_id = tenant_id.strip()

            if not tenant_id:
                raise ValueError(
                    "Tenant definition contains an empty tenant_id"
                )

            model_ids = {
                model.strip()
                for model in models.split(",")
                if model.strip()
            }

            if not model_ids:
                raise ValueError(
                    f"Tenant '{tenant_id}' has no authorized models"
                )

            access[tenant_id] = frozenset(model_ids)

        return access


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
