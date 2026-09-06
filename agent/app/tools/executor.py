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
    """
    Coordinates tool execution.

    Responsibilities:
    - verify that the requested tool exists
    - enforce tool authorization
    - enforce idempotency when an idempotency key is provided
    - delegate execution to the isolated sandbox
    - measure execution duration
    - normalize success and failure into ToolResult
    - preserve failure classification in ToolResult.metadata

    Execution boundary:

        AgentRuntime
             |
             v
        ToolExecutor
             |
             +---- Tool existence check
             |
             +---- Authorization
             |
             +---- Idempotency
             |
             v
          Sandbox
             |
             v
        ToolResult

    Authorization policy:

        explicitly allowed -> continue
        everything else    -> reject

    Idempotency:

        If no idempotency_key is supplied, execution behaves exactly
        as a normal tool execution.

        If an idempotency_key is supplied:
        - completed operations return the stored result
        - one caller owns execution for a new key
        - concurrent callers wait for the owner
        - failed executions release the key so a later attempt
          can execute again
    """

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
        """
        Execute one tool request.

        Policy order:

            1. tool existence
            2. authorization
            3. idempotency
            4. sandbox execution

        Authorization is intentionally performed before idempotency
        so unauthorized requests cannot participate in or benefit
        from the idempotency flow.

        Every execution returns a ToolResult.
        """

        start = time.perf_counter()

        # ---------------------------------------------------------
        # TOOL DISCOVERY
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
        # AUTHORIZATION
        # ---------------------------------------------------------

        if self.authorization is not None:
            if context is None:
                duration = time.perf_counter() - start

                return ToolResult(
                    success=False,
                    output=None,
                    error=(
                        "Execution context is required "
                        "for tool authorization"
                    ),
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
        # IDEMPOTENCY
        # ---------------------------------------------------------

        if (
            idempotency_key is not None
            and self.idempotency_store is not None
        ):
            # First check whether this logical operation has
            # already completed.
            existing = await self.idempotency_store.get(
                idempotency_key,
            )

            if existing is not None:
                return existing.result

            # Atomically claim the operation.
            #
            # Only one concurrent caller can become the owner.
            claimed = await self.idempotency_store.claim(
                idempotency_key,
            )

            if not claimed:
                # Another caller owns the operation.
                #
                # Wait for that caller to finish instead of
                # executing the side effect a second time.
                existing = await self.idempotency_store.wait(
                    idempotency_key,
                )

                return existing.result

        # ---------------------------------------------------------
        # SANDBOX EXECUTION
        # ---------------------------------------------------------

        try:
            output = await self.sandbox.execute(
                name,
                arguments,
            )

        except Exception as exc:
            duration = time.perf_counter() - start

            # The operation did not complete successfully.
            #
            # Release the idempotency claim so a later request
            # using the same logical operation key can retry.
            if (
                idempotency_key is not None
                and self.idempotency_store is not None
            ):
                await self.idempotency_store.release(
                    idempotency_key,
                )

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
        # SUCCESS
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

        # Store the completed result so duplicate requests with
        # the same idempotency key return this result instead of
        # executing the tool again.
        if (
            idempotency_key is not None
            and self.idempotency_store is not None
        ):
            await self.idempotency_store.put(
                IdempotencyRecord(
                    key=idempotency_key,
                    result=result,
                )
            )

        return result
