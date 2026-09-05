from __future__ import annotations

from uuid import uuid4

import pytest

from app.agent_runtime.domain import (
    Execution,
    ExecutionContext,
    ExecutionStatus,
    DecisionType,
)
from app.agent_runtime.planner import Planner
from app.core.errors import AgentProtocolError
from app.tools.builtin import create_tool_registry


@pytest.fixture
def planner() -> Planner:
    return Planner(tools=create_tool_registry())


@pytest.fixture
def context() -> ExecutionContext:
    execution = Execution()
    context = ExecutionContext(execution=execution)
    context.current_step = 1
    return context


def test_plan_final_response(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello, how can I help you?",
                }
            }
        ]
    }

    decision = planner.plan(
        response=response,
        context=context,
    )

    assert decision.type is DecisionType.FINAL
    assert decision.is_final
    assert not decision.is_tool_call
    assert decision.content == "Hello, how can I help you?"
    assert decision.tool_name is None
    assert decision.arguments == {}
    assert decision.call_id is None


def test_plan_strips_final_response_content(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "   Hello world   ",
                }
            }
        ]
    }

    decision = planner.plan(
        response=response,
        context=context,
    )

    assert decision.is_final
    assert decision.content == "Hello world"


def test_plan_calculator_tool_call(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "calculator",
                                "arguments": '{"expression": "25 * 17"}',
                            },
                        }
                    ],
                }
            }
        ]
    }

    decision = planner.plan(
        response=response,
        context=context,
    )

    assert decision.type is DecisionType.TOOL_CALL
    assert decision.is_tool_call
    assert not decision.is_final

    assert decision.tool_name == "calculator"
    assert decision.arguments == {
        "expression": "25 * 17",
    }
    assert decision.call_id == "call_123"
    assert decision.content is None


def test_plan_rejects_unknown_tool(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_unknown",
                            "type": "function",
                            "function": {
                                "name": "unknown_tool",
                                "arguments": "{}",
                            },
                        }
                    ],
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="Unknown tool requested by model",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_missing_choices(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {}

    with pytest.raises(
        AgentProtocolError,
        match="'choices' must be a list",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_empty_choices(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": []
    }

    with pytest.raises(
        AgentProtocolError,
        match="does not contain choices",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_invalid_choice(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            "invalid-choice"
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="invalid choice",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_missing_message(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {}
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="does not contain message",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_invalid_message(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": "invalid-message"
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="does not contain message",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_non_assistant_role(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "user",
                    "content": "Hello",
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="role 'assistant'",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_invalid_tool_calls_type(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": "invalid",
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="'tool_calls' must be a list",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_multiple_tool_calls(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "calculator",
                                "arguments": "{}",
                            },
                        },
                        {
                            "id": "call_2",
                            "function": {
                                "name": "calculator",
                                "arguments": "{}",
                            },
                        },
                    ],
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="multiple tool calls",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_invalid_tool_call(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        "invalid-tool-call"
                    ],
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="Tool call must be an object",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_missing_call_id(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "calculator",
                                "arguments": "{}",
                            }
                        }
                    ],
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="no valid ID",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_invalid_function(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": "invalid-function",
                        }
                    ],
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="invalid function",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_missing_tool_name(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": {
                                "arguments": "{}",
                            },
                        }
                    ],
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="no valid name",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_invalid_json_arguments(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": {
                                "name": "calculator",
                                "arguments": "not-json",
                            },
                        }
                    ],
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="Invalid JSON arguments",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_non_object_arguments(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": {
                                "name": "calculator",
                                "arguments": '["25 * 17"]',
                            },
                        }
                    ],
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="must be a JSON object",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_non_string_arguments(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": {
                                "name": "calculator",
                                "arguments": {
                                    "expression": "25 * 17"
                                },
                            },
                        }
                    ],
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="arguments must be a JSON string",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_accepts_missing_arguments_as_empty_object(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": {
                                "name": "calculator",
                            },
                        }
                    ],
                }
            }
        ]
    }

    decision = planner.plan(
        response=response,
        context=context,
    )

    assert decision.is_tool_call
    assert decision.tool_name == "calculator"
    assert decision.arguments == {}


def test_plan_rejects_empty_final_content(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "   ",
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="empty content",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_non_string_final_content(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": {
                        "answer": "hello"
                    },
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="content must be a string",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_rejects_invalid_context(
    planner: Planner,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello",
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="valid ExecutionContext",
    ):
        planner.plan(
            response=response,
            context=None,  # type: ignore[arg-type]
        )


def test_plan_rejects_invalid_context_step(
    planner: Planner,
) -> None:
    execution = Execution()
    context = ExecutionContext(
        execution=execution,
    )

    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": {
                                "name": "calculator",
                                "arguments": '{"expression": "2 + 2"}',
                            },
                        }
                    ],
                }
            }
        ]
    }

    with pytest.raises(
        AgentProtocolError,
        match="Invalid execution step",
    ):
        planner.plan(
            response=response,
            context=context,
        )


def test_plan_accepts_positive_execution_step(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    context.current_step = 1

    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": {
                                "name": "calculator",
                                "arguments": '{"expression": "2 + 2"}',
                            },
                        }
                    ],
                }
            }
        ]
    }

    decision = planner.plan(
        response=response,
        context=context,
    )

    assert decision.is_tool_call
    assert decision.tool_name == "calculator"
    assert decision.arguments == {
        "expression": "2 + 2",
    }
    assert decision.call_id == "call_123"


def test_final_decision_is_immutable(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello",
                }
            }
        ]
    }

    decision = planner.plan(
        response=response,
        context=context,
    )

    with pytest.raises(AttributeError):
        decision.content = "Changed"  # type: ignore[misc]


def test_tool_decision_is_immutable(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": str(uuid4()),
                            "function": {
                                "name": "calculator",
                                "arguments": '{"expression": "2 + 2"}',
                            },
                        }
                    ],
                }
            }
        ]
    }

    decision = planner.plan(
        response=response,
        context=context,
    )

    with pytest.raises(AttributeError):
        decision.tool_name = "something_else"  # type: ignore[misc]


def test_planner_does_not_execute_tool(
    planner: Planner,
    context: ExecutionContext,
) -> None:
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": {
                                "name": "calculator",
                                "arguments": '{"expression": "2 + 2"}',
                            },
                        }
                    ],
                }
            }
        ]
    }

    decision = planner.plan(
        response=response,
        context=context,
    )

    assert decision.is_tool_call

    # Planner only creates a decision.
    # It must not execute the calculator itself.
    assert context.tool_call_count == 0
    assert context.observations == []
