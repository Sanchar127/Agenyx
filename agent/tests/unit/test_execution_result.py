from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.agent_runtime.domain import (
    Execution,
    ExecutionResult,
    ExecutionStatus,
)


def test_result_can_be_created_from_completed_execution() -> None:
    execution = Execution(
        metadata={
            "request_id": "req-123",
        }
    )

    execution.mark_started()
    execution.mark_completed()

    result = ExecutionResult.from_execution(
        execution,
        output="Hello",
    )

    assert result.execution_id == execution.id
    assert result.status is ExecutionStatus.COMPLETED
    assert result.output == "Hello"
    assert result.error is None
    assert result.succeeded is True
    assert result.failed is False
    assert result.cancelled is False


def test_result_preserves_failure_information() -> None:
    execution = Execution()

    execution.mark_started()
    execution.mark_failed(
        error="Something went wrong",
        error_type="AgentExecutionError",
    )

    result = ExecutionResult.from_execution(execution)

    assert result.status is ExecutionStatus.FAILED
    assert result.error == "Something went wrong"
    assert result.error_type == "AgentExecutionError"
    assert result.failed is True


def test_result_preserves_cancellation() -> None:
    execution = Execution()

    execution.mark_started()
    execution.mark_cancelled()

    result = ExecutionResult.from_execution(execution)

    assert result.status is ExecutionStatus.CANCELLED
    assert result.cancelled is True


def test_result_copies_metadata() -> None:
    execution = Execution(
        metadata={
            "request_id": "req-123",
        }
    )

    execution.mark_started()
    execution.mark_completed()

    result = ExecutionResult.from_execution(execution)

    execution.metadata["new_value"] = "should not affect result"

    assert result.metadata == {
        "request_id": "req-123",
    }


def test_result_is_immutable() -> None:
    execution = Execution()

    execution.mark_started()
    execution.mark_completed()

    result = ExecutionResult.from_execution(execution)

    with pytest.raises(FrozenInstanceError):
        result.status = ExecutionStatus.FAILED
