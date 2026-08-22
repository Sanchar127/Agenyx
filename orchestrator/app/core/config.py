
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Orchestrator service configuration."""

    app_name: str = "Agenyx Orchestrator"
    app_version: str = "0.1.0"

    valkey_url: str = Field(
        default="redis://valkey:6379/0",
        validation_alias="AGENTYX_VALKEY_URL",
    )

    task_stream: str = Field(
        default="agenyx:tasks",
        validation_alias="AGENTYX_TASK_STREAM",
    )

    consumer_group: str = Field(
        default="agenyx-workers",
        validation_alias="AGENTYX_CONSUMER_GROUP",
    )

    execution_ttl_seconds: int = Field(
        default=3600,
        validation_alias="AGENTYX_EXECUTION_TTL_SECONDS",
        ge=60,
    )

    max_attempts: int = Field(
        default=4,
        validation_alias="AGENTYX_MAX_ATTEMPTS",
        ge=1,
        le=20,
        description=(
            "Maximum number of worker attempts before "
            "dead-lettering."
        ),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
