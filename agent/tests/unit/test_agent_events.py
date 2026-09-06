import pytest

from app.agent_runtime.events import AgentEvent


def test_agent_event_creates_event() -> None:
    event = AgentEvent(
        type="tool_call_started",
        execution_id="exec-123",
        data={
            "call_id": "call-1",
            "tool_name": "search",
        },
    )

    assert event.type == "tool_call_started"
    assert event.execution_id == "exec-123"
    assert event.data == {
        "call_id": "call-1",
        "tool_name": "search",
    }


def test_agent_event_defaults_to_empty_data() -> None:
    event = AgentEvent(
        type="execution_started",
        execution_id="exec-123",
    )

    assert event.data == {}


def test_agent_event_is_immutable() -> None:
    event = AgentEvent(
        type="execution_started",
        execution_id="exec-123",
    )

    with pytest.raises(AttributeError):
        event.type = "execution_failed"


@pytest.mark.parametrize(
    ("event_type", "execution_id"),
    [
        ("", "exec-123"),
        ("execution_started", ""),
    ],
)
def test_agent_event_rejects_empty_required_fields(
    event_type: str,
    execution_id: str,
) -> None:
    with pytest.raises(ValueError):
        AgentEvent(
            type=event_type,
            execution_id=execution_id,
        )
