import pytest

from app.core.errors import (
    InvalidToolArgumentsError,
    ToolExecutionError,
    ToolNotFound,
    ToolValidationError,
    UnknownToolError,
)
from app.tools.builtin import create_tool_registry
from app.tools.registry import Tool, ToolRegistry


def test_calculator_is_registered() -> None:
    registry = create_tool_registry()

    names = registry.definitions()

    assert len(names) == 1
    assert names[0]["function"]["name"] == "calculator"


def test_calculator_executes() -> None:
    registry = create_tool_registry()

    result = registry.execute(
        "calculator",
        {"expression": "25 * 17"},
    )

    assert result == "425"


def test_unknown_tool_fails() -> None:
    registry = create_tool_registry()

    with pytest.raises(UnknownToolError):
        registry.execute(
            "does_not_exist",
            {},
        )


def test_unknown_tool_is_tool_not_found() -> None:
    registry = create_tool_registry()

    with pytest.raises(ToolNotFound):
        registry.execute(
            "does_not_exist",
            {},
        )


def test_invalid_tool_arguments_are_validation_error() -> None:
    registry = ToolRegistry()

    def requires_expression(
        expression: str,
    ) -> str:
        return expression

    registry.register(
        Tool(
            name="requires_expression",
            description="Requires an expression argument.",
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                    },
                },
                "required": ["expression"],
            },
            execute=requires_expression,
        )
    )

    with pytest.raises(InvalidToolArgumentsError):
        registry.execute(
            "requires_expression",
            {},
        )


def test_invalid_tool_arguments_are_tool_validation_error() -> None:
    registry = ToolRegistry()

    def requires_expression(
        expression: str,
    ) -> str:
        return expression

    registry.register(
        Tool(
            name="requires_expression",
            description="Requires an expression argument.",
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                    },
                },
                "required": ["expression"],
            },
            execute=requires_expression,
        )
    )

    with pytest.raises(ToolValidationError):
        registry.execute(
            "requires_expression",
            {},
        )


def test_tool_execution_failure_is_tool_execution_error() -> None:
    registry = ToolRegistry()

    def failing_tool() -> str:
        raise RuntimeError("database connection failed")

    registry.register(
        Tool(
            name="failing_tool",
            description="A tool that always fails.",
            input_schema={
                "type": "object",
                "properties": {},
            },
            execute=failing_tool,
        )
    )

    with pytest.raises(
        ToolExecutionError,
        match="Tool 'failing_tool' failed",
    ):
        registry.execute(
            "failing_tool",
            {},
        )
