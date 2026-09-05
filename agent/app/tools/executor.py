
from __future__ import annotations

import time
from typing import Any

from app.sandbox.client import ToolSandboxClient
from app.tools.registry import ToolRegistry
from app.tools.result import ToolResult


class ToolExecutor:
    """
    Coordinates tool execution.

    Responsibilities:
    - verify that the requested tool exists
    - delegate execution to the isolated sandbox
    - measure execution duration
    - normalize success and failure into ToolResult
    - preserve failure classification in ToolResult.metadata

    The AgentRuntime does not need to know whether a tool is
    implemented in Python, executed remotely, or isolated inside
    the sandbox.

    Execution boundary:

        AgentRuntime
             |
             v
        ToolExecutor
             |
             +---- Tool existence check
             |
             v
          Sandbox
             |
             v
        ToolResult

    Failure classification:

        unknown tool
            -> error_type = "unknown_tool"

        sandbox/infrastructure failure
            -> error_type = exception class name

        successful execution
            -> no error_type
    """

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        sandbox: ToolSandboxClient,
    ) -> None:
        self.registry = registry
        self.sandbox = sandbox

    async def execute(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """
        Execute one tool request.

        Every execution returns a ToolResult.

        The executor deliberately does not leak sandbox exceptions
        to the AgentRuntime. Instead, failures are normalized into
        ToolResult while preserving enough metadata for the runtime
        to classify the failure correctly.
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
        # SANDBOX EXECUTION
        # ---------------------------------------------------------

        try:
            output = await self.sandbox.execute(
                name,
                arguments,
            )

        except Exception as exc:
            duration = time.perf_counter() - start

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

        return ToolResult(
            success=True,
            output=output,
            error=None,
            metadata={
                "tool_name": name,
            },
            duration_seconds=duration,
        )
