from __future__ import annotations

from uuid import uuid4

import pytest

from app.agent_runtime.authorization import (
    AllowListToolAuthorization,
    ToolAuthorizationError,
)
from app.agent_runtime.domain.context import ExecutionContext
from app.agent_runtime.domain.execution import Execution


def create_context() -> ExecutionContext:
    return ExecutionContext(
        execution=Execution(
            id=uuid4(),
        )
    )


@pytest.mark.asyncio
async def test_authorized_tool_is_allowed() -> None:
    authorization = AllowListToolAuthorization.from_tools(
        {"calculator", "echo"},
    )

    context = create_context()

    await authorization.authorize(
        tool_name="calculator",
        context=context,
    )


@pytest.mark.asyncio
async def test_unauthorized_tool_is_denied() -> None:
    authorization = AllowListToolAuthorization.from_tools(
        {"calculator", "echo"},
    )

    context = create_context()

    with pytest.raises(
        ToolAuthorizationError,
        match="Tool 'send_email' is not authorized",
    ):
        await authorization.authorize(
            tool_name="send_email",
            context=context,
        )


@pytest.mark.asyncio
async def test_empty_allow_list_denies_every_tool() -> None:
    authorization = AllowListToolAuthorization.from_tools(
        set(),
    )

    context = create_context()

    with pytest.raises(ToolAuthorizationError):
        await authorization.authorize(
            tool_name="calculator",
            context=context,
        )


@pytest.mark.asyncio
async def test_authorization_is_explicit() -> None:
    authorization = AllowListToolAuthorization.from_tools(
        {"calculator"},
    )

    context = create_context()

    await authorization.authorize(
        tool_name="calculator",
        context=context,
    )

    with pytest.raises(ToolAuthorizationError):
        await authorization.authorize(
            tool_name="echo",
            context=context,
        )


@pytest.mark.asyncio
async def test_authorization_does_not_modify_execution_context() -> None:
    authorization = AllowListToolAuthorization.from_tools(
        {"calculator"},
    )

    context = create_context()

    original_execution = context.execution
    original_messages = list(context.messages)
    original_tool_calls = list(context.tool_calls)
    original_observations = list(context.observations)
    original_errors = list(context.errors)

    await authorization.authorize(
        tool_name="calculator",
        context=context,
    )

    assert context.execution is original_execution
    assert context.messages == original_messages
    assert context.tool_calls == original_tool_calls
    assert context.observations == original_observations
    assert context.errors == original_errors
