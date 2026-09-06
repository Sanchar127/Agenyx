from app.agent_runtime.context_manager import ContextManager
from app.agent_runtime.domain.context import ExecutionContext
from app.agent_runtime.domain.execution import Execution


def create_manager() -> ContextManager:
    context = ExecutionContext(
        execution=Execution(),
    )

    return ContextManager(context)


def test_context_manager_requires_execution_context():
    try:
        ContextManager(None)  # type: ignore[arg-type]
    except TypeError as exc:
        assert str(exc) == (
            "ContextManager requires a valid ExecutionContext"
        )
    else:
        raise AssertionError("Expected TypeError")


def test_context_manager_exposes_underlying_context():
    manager = create_manager()

    assert isinstance(
        manager.context,
        ExecutionContext,
    )


def test_add_system_message():
    manager = create_manager()

    manager.add_system_message(
        "You are an AI assistant."
    )

    assert manager.get_messages() == [
        {
            "role": "system",
            "content": "You are an AI assistant.",
        }
    ]


def test_add_user_message():
    manager = create_manager()

    manager.add_user_message(
        "Calculate 25 * 17."
    )

    assert manager.get_messages() == [
        {
            "role": "user",
            "content": "Calculate 25 * 17.",
        }
    ]


def test_add_assistant_message():
    manager = create_manager()

    message = {
        "role": "assistant",
        "content": "The answer is 425.",
    }

    manager.add_assistant_message(message)

    assert manager.get_messages() == [message]


def test_assistant_message_requires_assistant_role():
    manager = create_manager()

    try:
        manager.add_assistant_message(
            {
                "role": "user",
                "content": "invalid",
            }
        )
    except ValueError as exc:
        assert str(exc) == (
            "Assistant message must have role 'assistant'"
        )
    else:
        raise AssertionError("Expected ValueError")


def test_add_tool_message():
    manager = create_manager()

    manager.add_tool_message(
        call_id="call-1",
        name="calculator",
        content="425",
    )

    assert manager.get_messages() == [
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "name": "calculator",
            "content": "425",
        }
    ]


def test_tool_message_requires_call_id():
    manager = create_manager()

    try:
        manager.add_tool_message(
            call_id="",
            name="calculator",
            content="425",
        )
    except ValueError as exc:
        assert str(exc) == (
            "Tool message requires a call_id"
        )
    else:
        raise AssertionError("Expected ValueError")


def test_tool_message_requires_name():
    manager = create_manager()

    try:
        manager.add_tool_message(
            call_id="call-1",
            name="",
            content="425",
        )
    except ValueError as exc:
        assert str(exc) == (
            "Tool message requires a tool name"
        )
    else:
        raise AssertionError("Expected ValueError")


def test_get_messages_returns_snapshot():
    manager = create_manager()

    manager.add_user_message("hello")

    messages = manager.get_messages()

    messages.append(
        {
            "role": "user",
            "content": "external mutation",
        }
    )

    assert manager.get_messages() == [
        {
            "role": "user",
            "content": "hello",
        }
    ]


def test_add_tool_call():
    manager = create_manager()

    tool_call = {
        "id": "call-1",
        "name": "calculator",
        "arguments": {
            "expression": "25 * 17",
        },
        "result": "425",
    }

    manager.add_tool_call(tool_call)

    assert manager.get_tool_calls() == [tool_call]
    assert manager.tool_call_count == 1


def test_get_tool_calls_returns_snapshot():
    manager = create_manager()

    manager.add_tool_call(
        {
            "id": "call-1",
            "name": "calculator",
            "arguments": {},
            "result": "425",
        }
    )

    tool_calls = manager.get_tool_calls()

    tool_calls.clear()

    assert manager.tool_call_count == 1


def test_add_observation():
    manager = create_manager()

    manager.add_observation(
        "The calculator returned 425."
    )

    assert manager.get_observations() == [
        "The calculator returned 425."
    ]


def test_get_observations_returns_snapshot():
    manager = create_manager()

    manager.add_observation("result")

    observations = manager.get_observations()

    observations.clear()

    assert manager.get_observations() == [
        "result"
    ]


def test_clear_only_clears_llm_context():
    manager = create_manager()

    manager.add_user_message("hello")

    manager.add_tool_call(
        {
            "id": "call-1",
            "name": "calculator",
            "arguments": {},
            "result": "425",
        }
    )

    manager.add_observation("425")

    manager.context.current_step = 3
    manager.context.metadata["model"] = "test-model"

    manager.clear()

    assert manager.get_messages() == []
    assert manager.get_tool_calls() == []
    assert manager.get_observations() == []

    assert manager.context.current_step == 3
    assert manager.context.metadata == {
        "model": "test-model",
    }
