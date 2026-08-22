from fastapi import FastAPI

from app.agent_runtime.runtime import AgentRuntime
from app.api.routes import create_router
from app.core.config import get_settings
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.tools.builtin import create_tool_registry
from app.api.errors import agenyx_error_handler
from app.core.errors import AgenyxError

settings = get_settings()


llm = OpenAICompatibleProvider(
    base_url=settings.llm_base_url,
    api_key=settings.llm_api_key,
    model=settings.llm_model,
    timeout=settings.llm_timeout_seconds,
    max_retries=settings.llm_max_retries,
)

tools = create_tool_registry()


runtime = AgentRuntime(
    llm=llm,
    tools=tools,
    max_steps=settings.agent_max_steps,
)


def get_runtime() -> AgentRuntime:
    """Return the configured agent runtime."""
    return runtime


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)
app.add_exception_handler(
    AgenyxError,
    agenyx_error_handler,
)



app.include_router(
    create_router(get_runtime)
)
