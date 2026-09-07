from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # -------------------------------------------------------------
    # Crash Recovery & Startup Check
    #
    # Scan for stale/orphaned executions interrupted by an unexpected
    # application crash or process restart before handling traffic.
    # -------------------------------------------------------------
    async with AsyncSessionFactory() as db_session:
        try:
            detector = RestartDetector(
                db_session=db_session,
                stale_threshold_seconds=getattr(settings, "stale_threshold_seconds", 300),
            )
            # If scan_and_flag_orphaned_executions is synchronous, call directly;
            # if async, await detector.scan_and_flag_orphaned_executions()
            flagged = detector.scan_and_flag_orphaned_executions()
            if flagged:
                logger.info(
                    "Crash recovery check completed. Flagged %d orphaned execution(s): %s",
                    len(flagged),
                    flagged,
                )
        except Exception:
            logger.exception("Failed to run crash recovery scan during startup.")

    yield

    # Cleanup open HTTP sessions on shutdown
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
