from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.agent_runtime.domain import Execution, ExecutionStatus


def test_execution_is_created_with_safe_defaults() -> None:
    execution = Execution()

    assert execution.id is not None
    assert execution.status is ExecutionStatus.CREATED
    assert execution.created_at.tzinfo is not None
    assert execution.created_at.tzinfo == timezone.utc
    assert execution.started_at is None
    assert execution.completed_at is None
    assert execution.error is None
    assert execution.error_type is None
    assert execution.metadata == {}


def test_execution_ids_are_unique() -> None:
    first = Execution()
    second = Execution()

    assert first.id != second.id


def test_execution_can_be_started() -> None:
    execution = Execution()

    execution.mark_started()

    assert execution.status is ExecutionStatus.RUNNING
    assert execution.started_at is not None
    assert execution.started_at.tzinfo == timezone.utc


def test_start_does_not_replace_original_started_at() -> None:
    execution = Execution()

    execution.mark_started()
    first_started_at = execution.started_at

    execution.mark_started()

    assert execution.started_at == first_started_at


def test_execution_can_be_completed() -> None:
    execution = Execution()

    execution.mark_started()
    execution.mark_completed()

    assert execution.status is ExecutionStatus.COMPLETED
    assert execution.completed_at is not None
    assert execution.duration_seconds is not None
    assert execution.duration_seconds >= 0


def test_execution_can_fail() -> None:
    execution = Execution()

    execution.mark_started()
    execution.mark_failed(
        error="Tool execution failed",
        error_type="ToolExecutionError",
    )

    assert execution.status is ExecutionStatus.FAILED
    assert execution.error == "Tool execution failed"
    assert execution.error_type == "ToolExecutionError"
    assert execution.completed_at is not None


def test_execution_failure_requires_error_message() -> None:
    execution = Execution()

    with pytest.raises(ValueError):
        execution.mark_failed(error="")


def test_execution_can_be_cancelled() -> None:
    execution = Execution()

    execution.mark_started()
    execution.mark_cancelled()

    assert execution.status is ExecutionStatus.CANCELLED
    assert execution.completed_at is not None


def test_duration_is_none_before_execution_starts() -> None:
    execution = Execution()

    assert execution.duration_seconds is None


def test_duration_is_none_while_execution_is_running() -> None:
    execution = Execution()

    execution.mark_started()

    assert execution.duration_seconds is None


def test_metadata_is_not_shared_between_executions() -> None:
    first = Execution()
    second = Execution()

    first.metadata["request_id"] = "abc"

    assert second.metadata == {}


def test_execution_timestamps_are_timezone_aware() -> None:
    execution = Execution()

    assert execution.created_at.tzinfo is not None

    execution.mark_started()

    assert execution.started_at is not None
    assert execution.started_at.tzinfo is not None

    execution.mark_completed()

    assert execution.completed_at is not None
    assert execution.completed_at.tzinfo is not None


def test_created_timestamp_is_valid_utc() -> None:
    execution = Execution()

    assert isinstance(execution.created_at, datetime)
    assert execution.created_at.utcoffset() == timezone.utc.utcoffset(
        execution.created_at
    )
