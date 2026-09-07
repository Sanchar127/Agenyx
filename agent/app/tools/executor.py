from __future__ import annotations

import time
from typing import Any

from app.agent_runtime.authorization import (
    ToolAuthorization,
    ToolAuthorizationError,
)
from app.agent_runtime.domain.context import ExecutionContext
from app.agent_runtime.idempotency import (
    IdempotencyRecord,
    IdempotencyStore,
)
from app.sandbox.client import ToolSandboxClient
from app.tools.registry import ToolRegistry
from app.tools.result import ToolResult


class ToolExecutor:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        sandbox: ToolSandboxClient,
        idempotency_store: IdempotencyStore | None = None,
        authorization: ToolAuthorization | None = None,
    ) -> None:
        self.registry = registry
        self.sandbox = sandbox
        self.idempotency_store = idempotency_store
        self.authorization = authorization

    async def execute(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
        context: ExecutionContext | None = None,
    ) -> ToolResult:
        start = time.perf_counter()

        # ---------------------------------------------------------
        # 1. TOOL DISCOVERY
        # ---------------------------------------------------------
        if not self.registry.has(name):
            duration = time.perf_counter() - start
            return ToolResult(
                success=False,
                output=None,
                error=f"Unknown tool: {name}",
                metadata={
                    "error_type": "unknown_tool",
                    "tool_name": name,
                },
                duration_seconds=duration,
            )

        # ---------------------------------------------------------
        # 2. AUTHORIZATION
        # ---------------------------------------------------------
        if self.authorization is not None:
            if context is None:
                duration = time.perf_counter() - start
                return ToolResult(
                    success=False,
                    output=None,
                    error="Execution context is required for tool authorization",
                    metadata={
                        "error_type": "authorization_context_missing",
                        "tool_name": name,
                    },
                    duration_seconds=duration,
                )

            try:
                await self.authorization.authorize(
                    tool_name=name,
                    context=context,
                )
            except ToolAuthorizationError as exc:
                duration = time.perf_counter() - start
                return ToolResult(
                    success=False,
                    output=None,
                    error=str(exc),
                    metadata={
                        "error_type": "tool_not_authorized",
                        "tool_name": name,
                    },
                    duration_seconds=duration,
                )

        # ---------------------------------------------------------
        # 3. IDEMPOTENCY (RECOVERY CHECK & CLAIM)
        # ---------------------------------------------------------
        if idempotency_key is not None and self.idempotency_store is not None:
            # Check if this operation was already executed prior to recovery/retry
            existing = await self.idempotency_store.get(idempotency_key)
            if existing is not None:
                return existing.result

            # Atomically claim the operation execution
            claimed = await self.idempotency_store.claim(idempotency_key)
            if not claimed:
                # Concurrent worker or replay task owns execution; wait for result
                existing = await self.idempotency_store.wait(idempotency_key)
                if existing is not None:
                    return existing.result

        # ---------------------------------------------------------
        # 4. SANDBOX EXECUTION
        # ---------------------------------------------------------
        try:
            output = await self.sandbox.execute(
                name,
                arguments,
            )
        except Exception as exc:
            duration = time.perf_counter() - start

            # Release idempotency claim so retries can attempt execution again
            if idempotency_key is not None and self.idempotency_store is not None:
                await self.idempotency_store.release(idempotency_key)

            return ToolResult(
                success=False,
                output=None,
                error=str(exc),
                metadata={
                    "error_type": type(exc).__name__,
                    "tool_name": name,
                },
                duration_seconds=duration,
            )

        # ---------------------------------------------------------
        # 5. SUCCESS & IDEMPOTENCY RECORDING
        # ---------------------------------------------------------
        duration = time.perf_counter() - start

        result = ToolResult(
            success=True,
            output=output,
            error=None,
            metadata={
                "tool_name": name,
            },
            duration_seconds=duration,
        )

        # Store completed result so subsequent executions skip sandbox re-runs
        if idempotency_key is not None and self.idempotency_store is not None:
            await self.idempotency_store.put(
                IdempotencyRecord(
                    key=idempotency_key,
                    result=result,
                )
            )

        return result
