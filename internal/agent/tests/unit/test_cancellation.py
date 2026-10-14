import pytest

from app.agent_runtime.cancellation import CancellationToken
from app.core.errors import ExecutionCancelled


def test_token_starts_not_cancelled() -> None:
    token = CancellationToken()

    assert token.is_cancelled is False


def test_cancel_marks_token_cancelled() -> None:
    token = CancellationToken()

    token.cancel()

    assert token.is_cancelled is True


def test_raise_if_cancelled_does_nothing_before_cancel() -> None:
    token = CancellationToken()

    token.raise_if_cancelled()


def test_raise_if_cancelled_raises_after_cancel() -> None:
    token = CancellationToken()

    token.cancel()

    with pytest.raises(
        ExecutionCancelled,
        match="cancelled",
    ):
        token.raise_if_cancelled()


def test_cancel_is_idempotent() -> None:
    token = CancellationToken()

    token.cancel()
    token.cancel()
    token.cancel()

    assert token.is_cancelled is True
