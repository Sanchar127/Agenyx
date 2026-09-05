from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.core.errors import (
    InvalidToolArgumentsError,
    ToolExecutionError,
    UnknownToolError,
)


@dataclass(frozen=True)
class Tool:
    """
    Definition of a tool available to the Agent.

    A Tool contains:

    - name:
        Stable identifier used by the model.

    - description:
        Human/model-readable description of the tool.

    - input_schema:
        JSON-schema-like definition describing accepted arguments.

    - execute:
        Callable responsible for performing the actual operation.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    execute: Callable[..., Any]


class ToolRegistry:
    """
    Registry of tools available to the Agent.

    Responsibilities:

    - register tools
    - prevent duplicate registration
    - check whether a tool exists
    - expose tool definitions to inference
    - execute registered tools
    - translate low-level tool failures into Agenyx exceptions

    The registry does NOT:

    - perform model inference
    - perform model routing
    - manage execution state
    - communicate with the sandbox
    - make planning decisions
    - persist execution state
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        Register a tool.

        Tool names must be unique.
        """

        if tool.name in self._tools:
            raise ValueError(
                f"Tool already registered: {tool.name}"
            )

        self._tools[tool.name] = tool

    def has(self, name: str) -> bool:
        """
        Return True if a tool with the given name is registered.
        """

        return name in self._tools

    def definitions(self) -> list[dict[str, Any]]:
        """
        Return all registered tools in an OpenAI-compatible format.

        These definitions are provided to the Inference service so
        the model knows which tools are available.
        """

        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in self._tools.values()
        ]

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """
        Execute a registered tool.

        Error classification:

        UnknownToolError
            The requested tool does not exist.

            UnknownToolError inherits from ToolNotFound, so the
            Agent-level abstraction remains ToolNotFound.

        InvalidToolArgumentsError
            The tool exists, but the supplied arguments are invalid.

            InvalidToolArgumentsError inherits from ToolValidationError.

        ToolExecutionError
            The tool exists and the arguments reach the tool, but
            the tool itself fails during execution.

        This method deliberately converts low-level Python errors
        into stable Agenyx-level exceptions.
        """

        tool = self._tools.get(name)

        if tool is None:
            raise UnknownToolError(
                f"Unknown tool: {name}"
            )

        try:
            return tool.execute(**arguments)

        except TypeError as exc:
            """
            A TypeError raised during invocation is treated as an
            argument-validation failure.

            Examples:

            - missing required argument
            - unexpected argument
            - invalid Python-level argument shape
            """

            raise InvalidToolArgumentsError(
                f"Invalid arguments for '{name}': {exc}"
            ) from exc

        except Exception as exc:
            """
            Any other exception belongs to the tool execution
            boundary.

            The Agent should receive ToolExecutionError rather than
            an arbitrary implementation-specific exception.
            """

            raise ToolExecutionError(
                f"Tool '{name}' failed"
            ) from exc
