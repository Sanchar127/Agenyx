# tests/unit/test_crash_recovery.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest

from app.agent_runtime.domain.status import ExecutionStatus
from app.agent_runtime.recovery.restart_detector import RestartDetector
from app.agent_runtime.recovery.replayer import ContextReplayer
from app.tools.idempotency import IdempotencyManager


@pytest.fixture
def crashed_execution_fixture():
    execution = MagicMock()
    execution.id = "exec_crashed_101"
    execution.status = ExecutionStatus.RUNNING
    execution.recovery_attempts = 0
    execution.updated_at = datetime.now(timezone.utc) - timedelta(seconds=600)
    return execution


@pytest.fixture
def db_session(crashed_execution_fixture):
    session = MagicMock()
    stored_objects = []

    def mock_add(obj):
        stored_objects.append(obj)

    session.add.side_effect = mock_add

    query_mock = MagicMock()
    filter_mock = MagicMock()

    # RestartDetector list scan
    filter_mock.all.return_value = [crashed_execution_fixture]

    # IdempotencyManager get_cached_result lookup
    def mock_first():
        return stored_objects[-1] if stored_objects else None

    filter_mock.first.side_effect = mock_first

    query_mock.filter.return_value = filter_mock
    session.query.return_value = query_mock
    return session


def test_restart_detector_flags_orphaned_runs(db_session, crashed_execution_fixture):
    detector = RestartDetector(db_session=db_session, stale_threshold_seconds=300)
    flagged = detector.scan_and_flag_orphaned_executions()

    assert crashed_execution_fixture.id in flagged
    assert crashed_execution_fixture.status == ExecutionStatus.CRASHED


def test_idempotency_prevents_duplicate_tool_calls(db_session):
    idempotency = IdempotencyManager(db_session)
    key = idempotency.generate_key("exec_1", 1, "calculator", {"expr": "2+2"})

    # First call stores result
    idempotency.save_result(key, "exec_1", {"result": 4})

    # Second call retrieves cached result
    cached = idempotency.get_cached_result(key)
    assert cached == {"result": 4}


def test_context_rehydration_restores_history():
    mock_context_mgr = MagicMock()
    replayer = ContextReplayer(mock_context_mgr)

    mock_events = [
        MagicMock(event_type="USER_INPUT", payload={"text": "Calculate 2+2"}, created_at=1),
        MagicMock(event_type="MODEL_DECISION", payload={"decision": "Calling calculator"}, created_at=2),
    ]

    replayer.rehydrate(MagicMock(), mock_events)

    mock_context_mgr.add_user_message.assert_called_once_with("Calculate 2+2")
    mock_context_mgr.add_assistant_message.assert_called_once_with("Calling calculator")
