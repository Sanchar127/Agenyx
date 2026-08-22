import pytest

from app.core.errors import UnknownToolError
from app.tools.builtin import create_tool_registry


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
