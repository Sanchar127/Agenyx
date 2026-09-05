from __future__ import annotations

from app.agent_runtime.domain.decision import (
    AgentDecision,
    DecisionType,
)


def test_final_decision() -> None:
    decision = AgentDecision(
        type=DecisionType.FINAL,
        content="The answer is 425.",
    )

    assert decision.type is DecisionType.FINAL
    assert decision.is_final is True
    assert decision.is_tool_call is False
    assert decision.content == "The answer is 425."


def test_tool_call_decision() -> None:
    decision = AgentDecision(
        type=DecisionType.TOOL_CALL,
        tool_name="calculator",
        arguments={
            "expression": "25 * 17",
        },
        call_id="call-1",
    )

    assert decision.type is DecisionType.TOOL_CALL
    assert decision.is_tool_call is True
    assert decision.tool_name == "calculator"
    assert decision.arguments == {
        "expression": "25 * 17",
    }
    assert decision.call_id == "call-1"


def test_continue_decision() -> None:
    decision = AgentDecision(
        type=DecisionType.CONTINUE,
    )

    assert decision.type is DecisionType.CONTINUE
    assert decision.is_continue is True


def test_failure_decision() -> None:
    decision = AgentDecision(
        type=DecisionType.FAIL,
        error="Unable to continue execution.",
    )

    assert decision.type is DecisionType.FAIL
    assert decision.is_failure is True
    assert decision.error == (
        "Unable to continue execution."
    )


def test_arguments_default_to_empty_dict() -> None:
    first = AgentDecision(
        type=DecisionType.TOOL_CALL,
    )

    second = AgentDecision(
        type=DecisionType.TOOL_CALL,
    )

    assert first.arguments == {}
    assert second.arguments == {}
    assert first.arguments is not second.arguments


def test_decision_is_immutable() -> None:
    decision = AgentDecision(
        type=DecisionType.FINAL,
        content="Done",
    )

    try:
        decision.content = "Changed"
    except AttributeError:
        pass
    else:
        raise AssertionError(
            "AgentDecision should be immutable"
        )
