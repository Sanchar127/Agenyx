import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


CONFIG_FILE = (
    Path(__file__).resolve().parent.parent
    / "config"
    / "inference.yaml"
)


class ProviderConfig(BaseModel):
    """Configuration for one inference provider."""

    name: str
    type: Literal["openai-compatible"] = "openai-compatible"
    base_url: AnyHttpUrl
    api_key: str = ""

    @field_validator("api_key", mode="before")
    @classmethod
    def expand_api_key_environment_variable(cls, value: str) -> str:
        """Expand ${ENV_VAR} references in provider API keys."""

        if not isinstance(value, str):
            return value

        pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

        def replace(match: re.Match[str]) -> str:
            variable_name = match.group(1)
            variable_value = os.environ.get(variable_name)

            if not variable_value:
                raise ValueError(
                    f"Environment variable '{variable_name}' "
                    "is missing or empty"
                )

            return variable_value

        return pattern.sub(replace, value)


    def normalized_base_url(self) -> str:
        """Return the provider URL without a trailing slash."""
        return str(self.base_url).rstrip("/")


class ModelConfig(BaseModel):
    """Model-to-provider mapping."""

    id: str
    provider: str


class InferenceConfig(BaseModel):
    """Inference provider, model, and failover configuration."""

    default_model: str
    providers: list[ProviderConfig] = Field(default_factory=list)
    models: list[ModelConfig] = Field(default_factory=list)
    failover: dict[str, list[str]] = Field(default_factory=dict)


class RuntimeConfig(BaseModel):
    """Inference runtime configuration."""

    max_retries: int = 2
    request_timeout_seconds: float = 120.0
    max_connections: int = 100
    max_keepalive_connections: int = 20
    max_concurrency: int = 10
    max_failover_attempts: int = 3


class Settings(BaseSettings):
    """Application configuration loaded from YAML and environment."""

    app_name: str = "agenyx-inference"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    log_json: bool = True

    inference: InferenceConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    service_api_key: str = ""

    tenant_model_access: str = (
        "tenant-a=qwen2.5:7b, llama3.2:3b;"
        "tenant-b=llama3.2:3b"
    )

    max_request_body_bytes: int = 1_048_576
    max_messages: int = 100
    max_message_content_chars: int = 100_000
    max_total_message_content_chars: int = 500_000

    otel_service_name: str = "agenyx-inference"
    otel_service_namespace: str = "agenyx"
    otel_exporter_otlp_endpoint: str = (
        "http://agenyx-otel-collector.monitoring.svc.cluster.local:4317"
    )

    model_config = SettingsConfigDict(
        env_prefix="INFERENCE_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Load settings with environment variables overriding YAML."""

        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(
                settings_cls,
                yaml_file=CONFIG_FILE,
                deep_merge=True,
            ),
            dotenv_settings,
            file_secret_settings,
        )

    # -----------------------------------------------------
    # Provider compatibility properties
    # -----------------------------------------------------

    @property
    def providers(self) -> list[str]:
        """Return configured provider names in priority order."""
        return [provider.name for provider in self.inference.providers]

    @property
    def provider_backend_configs(self) -> dict[str, dict[str, str]]:
        return {
            provider.name: {
                "type": provider.type,
                "base_url": provider.normalized_base_url(),
                "api_key": provider.api_key,
            }
            for provider in self.inference.providers
            if provider.enabled
        }

    @property
    def models(self) -> list[tuple[str, str]]:
        """Return model-to-provider mappings."""
        return [
            (model.id, model.provider)
            for model in self.inference.models
        ]

    @property
    def model_failover_providers(self) -> dict[str, tuple[str, ...]]:
        """Return ordered failover providers for each model."""
        return {
            model_id: tuple(providers)
            for model_id, providers in self.inference.failover.items()
        }

    @property
    def default_model(self) -> str:
        return self.inference.default_model

    # -----------------------------------------------------
    # Runtime compatibility properties
    # -----------------------------------------------------

    @property
    def max_retries(self) -> int:
        return self.runtime.max_retries

    @property
    def request_timeout_seconds(self) -> float:
        return self.runtime.request_timeout_seconds

    @property
    def max_connections(self) -> int:
        return self.runtime.max_connections

    @property
    def max_keepalive_connections(self) -> int:
        return self.runtime.max_keepalive_connections

    @property
    def max_concurrency(self) -> int:
        return self.runtime.max_concurrency

    @property
    def max_failover_attempts(self) -> int:
        return self.runtime.max_failover_attempts

    # -----------------------------------------------------
    # Configuration validation
    # -----------------------------------------------------

    def validate_configuration(self) -> None:
        """Validate relationships between providers, models, and routes."""

        provider_names = self.providers

        if not provider_names:
            raise ValueError("At least one inference provider is required")

        if len(provider_names) != len(set(provider_names)):
            raise ValueError("Duplicate inference provider names")

        model_ids = [model_id for model_id, _ in self.models]

        if len(model_ids) != len(set(model_ids)):
            raise ValueError("Duplicate model IDs")

        registered_providers = set(provider_names)
        registered_models = set(model_ids)

        for model_id, provider_name in self.models:
            if provider_name not in registered_providers:
                raise ValueError(
                    f"Model '{model_id}' references unknown provider "
                    f"'{provider_name}'"
                )

        if self.default_model not in registered_models:
            raise ValueError(
                f"Default model '{self.default_model}' is not registered"
            )

        for model_id, providers in self.model_failover_providers.items():
            if model_id not in registered_models:
                raise ValueError(
                    f"Failover route references unknown model '{model_id}'"
                )

            if not providers:
                raise ValueError(
                    f"Failover route for '{model_id}' has no providers"
                )

            unknown = set(providers) - registered_providers
            if unknown:
                raise ValueError(
                    f"Failover route for '{model_id}' references "
                    f"unknown providers: {sorted(unknown)}"
                )

        if self.runtime.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")

        if self.runtime.max_retries < 0:
            raise ValueError("max_retries cannot be negative")

        if self.runtime.max_connections <= 0:
            raise ValueError("max_connections must be positive")

        if self.runtime.max_keepalive_connections <= 0:
            raise ValueError(
                "max_keepalive_connections must be positive"
            )

        if (
            self.runtime.max_keepalive_connections
            > self.runtime.max_connections
        ):
            raise ValueError(
                "max_keepalive_connections cannot exceed max_connections"
            )

    # -----------------------------------------------------
    # Tenant model access
    # -----------------------------------------------------

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

    settings = Settings()
    settings.validate_configuration()
    return settings
