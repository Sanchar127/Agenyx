from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app.agent_runtime.persistence.service import (
    PostgreSQLExecutionPersistence,
)
from app.agent_runtime.planner import Planner
from app.agent_runtime.recovery.restart_detector import RestartDetector
from app.agent_runtime.runtime import AgentRuntime
from app.api.errors import agenyx_error_handler
from app.api.routes import create_router
from app.core.config import get_settings
from app.core.errors import AgenyxError
from app.db.session import AsyncSessionFactory
from app.inference.client import InferenceClient
from app.mcp_gateway.auth import BearerTokenMiddleware
from app.mcp_gateway.routing import MCPRootPathMiddleware
from app.router.client import SemanticRouterClient
from app.sandbox.client import ToolSandboxClient
from app.tools.builtin import create_tool_registry

logger = logging.getLogger(__name__)

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

planner = Planner(
    tools=tools,
)

sandbox = ToolSandboxClient(
    base_url=settings.sandbox_base_url,
    timeout_seconds=settings.sandbox_timeout_seconds,
)

# -------------------------------------------------------------
# Durable execution persistence.
#
# The application wires the concrete PostgreSQL implementation
# into the Runtime through the ExecutionPersistence protocol.
#
# AgentRuntime itself does not know about PostgreSQL or
# SQLAlchemy.
# -------------------------------------------------------------

persistence = PostgreSQLExecutionPersistence(
    AsyncSessionFactory,
)

runtime = AgentRuntime(
    router=router_client,
    inference=inference_client,
    planner=planner,
    tools=tools,
    max_steps=settings.agent_max_steps,
    sandbox=sandbox,
    persistence=persistence,
)


def get_runtime() -> AgentRuntime:
    """Return the configured agent runtime."""
    return runtime


# The MCP server shares FastAPI's listener; it does not bind another port.
mcp_server = MCPServer(
    name="agenyx-mcp-gateway",
    version="0.1.0",
)

mcp_app = mcp_server.streamable_http_app(
    streamable_http_path="/",
    json_response=True,
    stateless_http=True,
    max_request_body_size=1024 * 1024,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            host.strip()
            for host in settings.mcp_gateway_allowed_hosts.split(",")
            if host.strip()
        ],
        allowed_origins=[
            origin.strip()
            for origin in settings.mcp_gateway_allowed_origins.split(",")
            if origin.strip()
        ],
    ),
)

mcp_app.add_middleware(
    BearerTokenMiddleware,
    token=settings.mcp_gateway_token or "",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Authentication must be configured before accepting any traffic.
    if not settings.mcp_gateway_token:
        raise RuntimeError(
            "AGENEYX_MCP_GATEWAY_TOKEN must be set to enable the MCP gateway."
        )

    try:
        # The MCP session manager is created lazily by streamable_http_app().
        # Start it within the host application's lifespan.
        async with mcp_server.session_manager.run():
            # Crash recovery: mark executions orphaned by a previous crash.
            async with AsyncSessionFactory() as db_session:
                try:
                    detector = RestartDetector(
                        db_session=db_session,
                        stale_threshold_seconds=getattr(
                            settings,
                            "stale_threshold_seconds",
                            300,
                        ),
                    )
                    flagged = detector.scan_and_flag_orphaned_executions()
                    if flagged:
                        logger.info(
                            "Crash recovery check completed. Flagged %d "
                            "orphaned execution(s): %s",
                            len(flagged),
                            flagged,
                        )
                except Exception:
                    logger.exception(
                        "Failed to run crash recovery scan during startup."
                    )

            yield
    finally:
        # Preserve existing HTTP-client cleanup even if startup or shutdown
        # raises after entering the lifespan.
        await router_client.close()
        await inference_client.close()
        await sandbox.close()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    MCPRootPathMiddleware,
    mcp_app=mcp_app,
)

app.add_exception_handler(
    AgenyxError,
    agenyx_error_handler,
)

app.include_router(
    create_router(get_runtime),
)

# Mount after the existing API routes so their paths retain precedence.
# The MCP sub-application handles "/" internally, exposed externally as /mcp.
app.mount("/mcp", mcp_app, name="mcp")
