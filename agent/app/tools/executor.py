from __future__ import annotations

import time
from typing import Any

from app.tools.registry import ToolRegistry
from app.tools.result import ToolResult
from app.sandbox.client import ToolSandboxClient


class ToolExecutor:
    """
    Coordinates tool execution.

    Responsibilities:
    - verify that the requested tool exists
    - delegate execution to the isolated sandbox
    - measure execution duration
    - normalize success and failure into ToolResult

    The AgentRuntime does not need to know whether a tool is
    implemented in Python, executed remotely, or isolated inside
    the sandbox.
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
        start = time.perf_counter()

        # ---------------------------------------------------------
        # TOOL DISCOVERY / VALIDATION
        # ---------------------------------------------------------

        if not self.registry.has(name):
            duration = time.perf_counter() - start

            return ToolResult(
                success=False,
                error=f"Unknown tool: {name}",
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
                error=str(exc),
                duration_seconds=duration,
            )

        # ---------------------------------------------------------
        # SUCCESS
        # ---------------------------------------------------------

        duration = time.perf_counter() - start

        return ToolResult(
            success=True,
            output=output,
            duration_seconds=duration,
        )
