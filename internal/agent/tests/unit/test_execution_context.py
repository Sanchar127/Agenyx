from app.agent_runtime.domain.context import ExecutionContext
from app.agent_runtime.domain.execution import Execution


def test_context_starts_with_safe_defaults():
    execution = Execution()

    context = ExecutionContext(execution=execution)

    assert context.execution is execution
    assert context.messages == []
    assert context.current_plan is None
    assert context.current_step == 0
    assert context.tool_calls == []
    assert context.observations == []
    assert context.errors == []
    assert context.metadata == {}


def test_context_collections_are_independent():
    context_a = ExecutionContext(execution=Execution())
    context_b = ExecutionContext(execution=Execution())

    context_a.messages.append({"role": "user", "content": "hello"})
    context_a.observations.append("result")
    context_a.errors.append("error")

    assert context_b.messages == []
    assert context_b.observations == []
    assert context_b.errors == []


def test_add_message():
    context = ExecutionContext(execution=Execution())

    message = {
        "role": "user",
        "content": "Calculate 25 * 17",
    }

    context.add_message(message)

    assert context.messages == [message]


def test_add_tool_call():
    context = ExecutionContext(execution=Execution())

    tool_call = {
        "name": "calculator",
        "arguments": {"expression": "25 * 17"},
    }

    context.add_tool_call(tool_call)

    assert context.tool_calls == [tool_call]
    assert context.tool_call_count == 1


def test_add_observation():
    context = ExecutionContext(execution=Execution())

    context.add_observation("The calculator returned 425.")

    assert context.observations == [
        "The calculator returned 425."
    ]
    assert context.has_observations is True


def test_add_error():
    context = ExecutionContext(execution=Execution())

    context.add_error("Calculator failed")

    assert context.errors == ["Calculator failed"]
    assert context.has_errors is True


def test_empty_error_is_rejected():
    context = ExecutionContext(execution=Execution())

    try:
        context.add_error("")
    except ValueError as exc:
        assert str(exc) == "Execution context error cannot be empty"
    else:
        raise AssertionError("Expected ValueError")


def test_advance_step():
    context = ExecutionContext(execution=Execution())

    assert context.current_step == 0

    context.advance_step()
    assert context.current_step == 1

    context.advance_step()
    assert context.current_step == 2


def test_metadata_is_independent():
    context_a = ExecutionContext(execution=Execution())
    context_b = ExecutionContext(execution=Execution())

    context_a.metadata["model"] = "test-model"

    assert context_b.metadata == {}
