from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent_runtime.runtime import AgentRuntime
from app.api.errors import agenyx_error_handler
from app.api.routes import create_router
from app.core.config import get_settings
from app.core.errors import AgenyxError
from app.inference.client import InferenceClient
from app.router.client import SemanticRouterClient
from app.sandbox.client import ToolSandboxClient
from app.tools.builtin import create_tool_registry

settings = get_settings()

router_client = SemanticRouterClient(
    base_url=settings.router_base_url,
    timeout=settings.router_timeout_seconds,
)

inference_client = InferenceClient(
    base_url=settings.inference_base_url,
    timeout=settings.inference_timeout_seconds,
)

tools = create_tool_registry()

sandbox = ToolSandboxClient(
    base_url=settings.sandbox_base_url,
    timeout_seconds=settings.sandbox_timeout_seconds,
)

runtime = AgentRuntime(
    router=router_client,
    inference=inference_client,
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

    await router_client.close()
    await inference_client.close()
    await sandbox.close()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)


app.add_exception_handler(
    AgenyxError,
    agenyx_error_handler,
)


app.include_router(
    create_router(get_runtime),
)
