import pytest

from app.tools.calculator import calculator


def test_calculator_addition() -> None:
    assert calculator("2 + 3") == "5"


def test_calculator_multiplication() -> None:
    assert calculator("25 * 17") == "425"


def test_calculator_division() -> None:
    assert calculator("10 / 2") == "5.0"


def test_calculator_rejects_unsupported_expression() -> None:
    with pytest.raises(ValueError):
        calculator("import os")


def test_calculator_rejects_function_calls() -> None:
    with pytest.raises(ValueError):
        calculator("print(123)")
