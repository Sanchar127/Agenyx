from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    execute: Callable[..., Any]


def calculator(expression: str) -> str:
    """
    Simple calculator for basic arithmetic.

    This intentionally supports only a restricted character set.
    It is NOT arbitrary Python execution.
    """
    allowed = set("0123456789+-*/(). ")

    if not expression or any(char not in allowed for char in expression):
        raise ValueError("Expression contains unsupported characters")

    try:
        result = eval(expression, {"__builtins__": {}}, {})
    except Exception as exc:
        raise ValueError(f"Invalid expression: {exc}") from exc

    return str(result)


def get_tools() -> dict[str, Tool]:
    return {
        "calculator": Tool(
            name="calculator",
            description="Calculate a basic arithmetic expression.",
            execute=calculator,
        ),
    }
