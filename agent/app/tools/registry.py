from dataclasses import dataclass
from typing import Any, Callable

from app.core.errors import (
    InvalidToolArgumentsError,
    ToolExecutionError,
    UnknownToolError,
)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[..., str]


class ToolRegistry:

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(
                f"Tool already registered: {tool.name}"
            )

        self._tools[tool.name] = tool

    def has(self, name: str) -> bool:
      return name in self._tools

    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> str:

        tool = self._tools.get(name)

        if tool is None:
            raise UnknownToolError(
                f"Unknown tool: {name}"
            )

        try:
            return tool.execute(**arguments)

        except TypeError as exc:
            raise InvalidToolArgumentsError(
                f"Invalid arguments for '{name}': {exc}"
            ) from exc

        except Exception as exc:
            raise ToolExecutionError(
                f"Tool '{name}' failed"
            ) from exc
