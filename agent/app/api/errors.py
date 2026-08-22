from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import (
    AgentMaxStepsError,
    AgentProtocolError,
    LLMConnectionError,
    LLMTimeoutError,
    ToolError,
)


async def agenyx_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:

    if isinstance(exc, LLMTimeoutError):
        status_code = 504
        error_code = "LLM_TIMEOUT"

    elif isinstance(exc, LLMConnectionError):
        status_code = 503
        error_code = "LLM_UNAVAILABLE"

    elif isinstance(exc, AgentMaxStepsError):
        status_code = 500
        error_code = "AGENT_MAX_STEPS"

    elif isinstance(exc, AgentProtocolError):
        status_code = 502
        error_code = "AGENT_PROTOCOL_ERROR"

    elif isinstance(exc, ToolError):
        status_code = 502
        error_code = "TOOL_ERROR"

    else:
        status_code = 500
        error_code = "INTERNAL_ERROR"

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": error_code,
                "message": str(exc),
            }
        },
    )
