from __future__ import annotations

import pytest

from app.agent_runtime.retry_policy import RetryPolicy
from app.core.errors import (
    ExecutionCancelled,
    ExecutionLimitExceeded,
    LLMConnectionError,
    LLMResponseError,
    LLMTimeoutError,
    ToolExecutionError,
)


def test_default_policy_configuration() -> None:
    policy = RetryPolicy()

    assert policy.max_attempts == 3
    assert policy.base_delay == 0.2
    assert policy.max_delay == 2.0
    assert policy.jitter is True


def test_retryable_inference_connection_error() -> None:
    policy = RetryPolicy()

    assert policy.should_retry(
        error=LLMConnectionError("connection failed"),
        attempt=1,
    )


def test_retryable_inference_timeout_error() -> None:
    policy = RetryPolicy()

    assert policy.should_retry(
        error=LLMTimeoutError("timeout"),
        attempt=1,
    )


def test_retryable_tool_execution_error() -> None:
    policy = RetryPolicy()

    assert policy.should_retry(
        error=ToolExecutionError("tool failed"),
        attempt=1,
    )


def test_response_error_is_not_retryable() -> None:
    policy = RetryPolicy()

    assert not policy.should_retry(
        error=LLMResponseError("invalid response"),
        attempt=1,
    )


def test_execution_cancelled_is_never_retryable() -> None:
    policy = RetryPolicy()

    assert not policy.should_retry(
        error=ExecutionCancelled("cancelled"),
        attempt=1,
    )


def test_execution_limit_is_never_retryable() -> None:
    policy = RetryPolicy()

    assert not policy.should_retry(
        error=ExecutionLimitExceeded("limit exceeded"),
        attempt=1,
    )


def test_max_attempts_prevents_retry() -> None:
    policy = RetryPolicy(max_attempts=3)

    assert policy.should_retry(
        error=LLMConnectionError("temporary failure"),
        attempt=1,
    )

    assert policy.should_retry(
        error=LLMConnectionError("temporary failure"),
        attempt=2,
    )

    assert not policy.should_retry(
        error=LLMConnectionError("temporary failure"),
        attempt=3,
    )


def test_exponential_backoff_without_jitter() -> None:
    policy = RetryPolicy(
        base_delay=0.2,
        max_delay=2.0,
        jitter=False,
    )

    assert policy.get_delay(attempt=1) == pytest.approx(0.2)
    assert policy.get_delay(attempt=2) == pytest.approx(0.4)
    assert policy.get_delay(attempt=3) == pytest.approx(0.8)
    assert policy.get_delay(attempt=4) == pytest.approx(1.6)


def test_backoff_is_capped() -> None:
    policy = RetryPolicy(
        base_delay=0.2,
        max_delay=1.0,
        jitter=False,
    )

    assert policy.get_delay(attempt=1) == pytest.approx(0.2)
    assert policy.get_delay(attempt=2) == pytest.approx(0.4)
    assert policy.get_delay(attempt=3) == pytest.approx(0.8)
    assert policy.get_delay(attempt=4) == pytest.approx(1.0)
    assert policy.get_delay(attempt=5) == pytest.approx(1.0)


def test_jitter_stays_within_delay_range() -> None:
    policy = RetryPolicy(
        base_delay=0.2,
        max_delay=2.0,
        jitter=True,
    )

    for attempt in range(1, 5):
        delay = policy.get_delay(attempt=attempt)

        expected_max = min(
            0.2 * (2 ** (attempt - 1)),
            2.0,
        )

        assert 0.0 <= delay <= expected_max


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0},
        {"max_attempts": -1},
    ],
)
def test_invalid_max_attempts(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)


def test_negative_base_delay_is_rejected() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(base_delay=-0.1)


def test_negative_max_delay_is_rejected() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(max_delay=-0.1)


def test_max_delay_cannot_be_less_than_base_delay() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(
            base_delay=1.0,
            max_delay=0.5,
        )


def test_invalid_attempt_is_rejected() -> None:
    policy = RetryPolicy()

    with pytest.raises(ValueError):
        policy.should_retry(
            error=LLMConnectionError("failure"),
            attempt=0,
        )

    with pytest.raises(ValueError):
        policy.get_delay(attempt=0)
