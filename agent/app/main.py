from __future__ import annotations

from fastapi import FastAPI

from app.agent_runtime.runtime import AgentRuntime
from app.api.errors import agenyx_error_handler
from app.api.routes import create_router
from app.core.config import get_settings
from app.core.errors import AgenyxError
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.sandbox.client import ToolSandboxClient
from app.tools.builtin import create_tool_registry

from contextlib import asynccontextmanager
settings = get_settings()


llm = OpenAICompatibleProvider(
    base_url=settings.llm_base_url,
    api_key=settings.llm_api_key,
    model=settings.llm_model,
    timeout=settings.llm_timeout_seconds,
    max_retries=settings.llm_max_retries,
)


tools = create_tool_registry()


sandbox = ToolSandboxClient(
    base_url=settings.sandbox_base_url,
    timeout_seconds=settings.sandbox_timeout_seconds,
)


runtime = AgentRuntime(
    llm=llm,
    tools=tools,
    max_steps=settings.agent_max_steps,
    sandbox=sandbox,
)


def get_runtime() -> AgentRuntime:
    """Return the configured agent runtime."""

    return runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

    await llm.close()
    await sandbox.close()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)


app.add_exception_handler(
    AgenyxError,
    agenyx_error_handler,
)


app.include_router(
    create_router(get_runtime),
)
