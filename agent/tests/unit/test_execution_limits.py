from __future__ import annotations

import pytest

from app.agent_runtime.execution_limits import ExecutionLimits
from app.core.errors import (
    AgentMaxStepsError,
    ExecutionLimitExceeded,
)

import time
def test_execution_limits_accept_valid_values() -> None:
    limits = ExecutionLimits(
        max_steps=5,
        max_tool_calls=10,
    )

    assert limits.max_steps == 5
    assert limits.max_tool_calls == 10


def test_execution_limits_reject_zero_max_steps() -> None:
    with pytest.raises(
        ValueError,
        match="max_steps",
    ):
        ExecutionLimits(
            max_steps=0,
            max_tool_calls=10,
        )


def test_execution_limits_reject_negative_max_steps() -> None:
    with pytest.raises(
        ValueError,
        match="max_steps",
    ):
        ExecutionLimits(
            max_steps=-1,
            max_tool_calls=10,
        )


def test_execution_limits_reject_negative_tool_calls() -> None:
    with pytest.raises(
        ValueError,
        match="max_tool_calls",
    ):
        ExecutionLimits(
            max_steps=5,
            max_tool_calls=-1,
        )


def test_step_limit_allows_configured_step() -> None:
    limits = ExecutionLimits(
        max_steps=5,
        max_tool_calls=10,
    )

    limits.validate_step(5)


def test_step_limit_rejects_next_step() -> None:
    limits = ExecutionLimits(
        max_steps=5,
        max_tool_calls=10,
    )

    with pytest.raises(
        AgentMaxStepsError,
        match="maximum steps",
    ):
        limits.validate_step(6)


def test_step_limit_error_is_execution_limit_error() -> None:
    limits = ExecutionLimits(
        max_steps=5,
        max_tool_calls=10,
    )

    with pytest.raises(
        ExecutionLimitExceeded
    ):
        limits.validate_step(6)


def test_tool_limit_allows_call_before_limit() -> None:
    limits = ExecutionLimits(
        max_steps=5,
        max_tool_calls=3,
    )

    limits.validate_tool_call(0)
    limits.validate_tool_call(1)
    limits.validate_tool_call(2)


def test_tool_limit_rejects_call_at_limit() -> None:
    limits = ExecutionLimits(
        max_steps=5,
        max_tool_calls=3,
    )

    with pytest.raises(
        ExecutionLimitExceeded,
        match="maximum tool calls",
    ):
        limits.validate_tool_call(3)



def test_timeout_allows_execution_before_limit() -> None:
    limits = ExecutionLimits(timeout_seconds=10.0)
    started_at = time.monotonic()

    limits.validate_timeout(started_at)


def test_timeout_rejects_expired_execution() -> None:
    limits = ExecutionLimits(timeout_seconds=1.0)
    started_at = time.monotonic() - 2.0

    with pytest.raises(
        ExecutionLimitExceeded,
        match="timeout",
    ):
        limits.validate_timeout(started_at)


def test_timeout_must_be_positive() -> None:
    with pytest.raises(
        ValueError,
        match="timeout_seconds",
    ):
        ExecutionLimits(timeout_seconds=0)


def test_timeout_rejects_negative_value() -> None:
    with pytest.raises(
        ValueError,
        match="timeout_seconds",
    ):
        ExecutionLimits(timeout_seconds=-1)
