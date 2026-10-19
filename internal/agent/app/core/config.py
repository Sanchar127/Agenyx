from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agenyx Agent"
    environment: str = "development"
    debug: bool = False

    # Semantic Router
    router_base_url: str = "http://router:8005"
    router_timeout_seconds: float = 10.0

    # Inference Service
    inference_base_url: str = "http://inference:8004"
    inference_timeout_seconds: float = 120.0

    # Agent
    agent_max_steps: int = 8

    # Sandbox
    sandbox_base_url: str = "http://sandbox:9000"
    sandbox_timeout_seconds: float = 10.0

    # Database
    database_url: str = (
        "postgresql+asyncpg://agenyx:agenyx_dev_password"
        "@postgres:5432/agenyx"
    )

    # Authentication
    jwt_secret: str = "development-only-secret"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "agenyx"
    jwt_audience: str = "agenyx-api"

    # Embedded MCP gateway. These aliases intentionally use the recipe's
    # AGENEYX_ prefix rather than the existing AGENTYX_ settings prefix.
    mcp_gateway_token: str | None = Field(
        default=None,
        validation_alias="AGENEYX_MCP_GATEWAY_TOKEN",
    )
    mcp_gateway_allowed_hosts: str = Field(
        default="localhost:*,127.0.0.1:*,agent:8000",
        validation_alias="AGENEYX_MCP_ALLOWED_HOSTS",
    )
    mcp_gateway_allowed_origins: str = Field(
        default="",
        validation_alias="AGENEYX_MCP_ALLOWED_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENTYX_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
