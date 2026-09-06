from app.agent_runtime.event_types import AgentEventType


def test_event_types_have_expected_values() -> None:
    assert AgentEventType.EXECUTION_STARTED == "execution_started"
    assert AgentEventType.EXECUTION_COMPLETED == "execution_completed"
    assert AgentEventType.EXECUTION_FAILED == "execution_failed"
    assert AgentEventType.EXECUTION_CANCELLED == "execution_cancelled"

    assert AgentEventType.INFERENCE_STARTED == "inference_started"
    assert AgentEventType.INFERENCE_COMPLETED == "inference_completed"

    assert AgentEventType.TOOL_CALL_STARTED == "tool_call_started"
    assert AgentEventType.TOOL_CALL_COMPLETED == "tool_call_completed"

    assert AgentEventType.APPROVAL_REQUIRED == "approval_required"
    assert AgentEventType.APPROVAL_RESOLVED == "approval_resolved"

    assert AgentEventType.STEP_STARTED == "step_started"


def test_event_type_is_string_compatible() -> None:
    event_type = AgentEventType.TOOL_CALL_STARTED

    assert isinstance(event_type, str)
    assert event_type == "tool_call_started"
