from __future__ import annotations

import asyncio
from unittest.mock import MagicMock,MagicMock
import pytest

from app.agent_runtime.approval import (
    AllowListApprovalPolicy,
    ApprovalManager,
    ApprovalStatus,
)
from app.agent_runtime.domain import (
    Execution,
    ExecutionContext,
    ExecutionState,
    ToolCall,
)
from app.agent_runtime.runtime import AgentRuntime
from app.core.errors import ToolExecutionError


def build_runtime() -> AgentRuntime:
    """
    Build a minimal AgentRuntime for approval-focused unit tests.

    Only the components required by _handle_required_approvals()
    are initialized here.
    """
    runtime = object.__new__(AgentRuntime)

    runtime.approval_policy = (
        AllowListApprovalPolicy.from_tools(
            {"delete_file"}
        )
    )

    runtime.approval_manager = ApprovalManager()

    runtime.limits = MagicMock()
    runtime.limits.timeout_seconds = 60.0

    # _handle_required_approvals() asks the execution limits for the
    # remaining execution-wide timeout. Return a real numeric value
    # instead of MagicMock.
    runtime.limits.remaining_timeout.return_value = 60.0

    runtime.limits.validate_timeout = MagicMock()

    return runtime


def build_execution() -> Execution:
    """
    Build an execution at the lifecycle point where the runtime can
    legitimately request human approval.

    Real lifecycle:

        CREATED
            ↓
        PLANNING
            ↓
        INFERENCE
            ↓
        WAITING_APPROVAL
    """
    execution = Execution()

    execution.transition_to(
        ExecutionState.PLANNING
    )

    execution.transition_to(
        ExecutionState.INFERENCE
    )

    return execution


def build_context(
    execution: Execution,
) -> ExecutionContext:
    """
    Build an execution context for the supplied execution.
    """
    return ExecutionContext(
        execution=execution
    )


def build_cancellation() -> MagicMock:
    """
    Build a cancellation token mock that is not cancelled.
    """
    cancellation = MagicMock()
    cancellation.raise_if_cancelled = MagicMock()

    return cancellation


def build_delete_admission(
    *,
    call_id: str = "call-1",
    path: str = "/tmp/test.txt",
) -> tuple[
    ToolCall,
    tuple[str, str],
]:
    """
    Build a protected delete_file tool call and its admission record.
    """
    tool_call = ToolCall(
        name="delete_file",
        arguments={
            "path": path,
        },
        call_id=call_id,
    )

    admission = (
        "delete_file",
        f'{{"path":"{path}"}}',
    )

    return tool_call, admission


@pytest.mark.asyncio
async def test_protected_tool_enters_waiting_approval() -> None:
    runtime = build_runtime()

    execution = build_execution()
    context = build_context(execution)

    tool_call, admission = build_delete_admission()

    admissions = [
        (
            tool_call,
            admission,
        )
    ]

    cancellation = build_cancellation()

    task = asyncio.create_task(
        runtime._handle_required_approvals(
            execution=execution,
            context=context,
            admissions=admissions,
            execution_started_at=0.0,
            cancellation=cancellation,
        )
    )

    # Allow the approval handler to create its approval request
    # and reach its waiting point.
    await asyncio.sleep(0)

    requests = list(
        runtime.approval_manager._requests.values()
    )

    assert len(requests) == 1

    request = requests[0]

    assert request.execution_id == str(
        execution.id
    )

    assert request.call_id == "call-1"

    assert request.tool_name == "delete_file"

    assert request.arguments == {
        "path": "/tmp/test.txt",
    }

    assert request.status is ApprovalStatus.PENDING

    assert (
        execution.state
        is ExecutionState.WAITING_APPROVAL
    )

    # The handler must remain blocked while approval is pending.
    assert not task.done()

    task.cancel()

    with pytest.raises(
        asyncio.CancelledError
    ):
        await task


@pytest.mark.asyncio
async def test_approval_allows_execution_to_continue() -> None:
    runtime = build_runtime()

    execution = build_execution()
    context = build_context(execution)

    tool_call, admission = build_delete_admission()

    admissions = [
        (
            tool_call,
            admission,
        )
    ]

    cancellation = build_cancellation()

    task = asyncio.create_task(
        runtime._handle_required_approvals(
            execution=execution,
            context=context,
            admissions=admissions,
            execution_started_at=0.0,
            cancellation=cancellation,
        )
    )

    await asyncio.sleep(0)

    requests = list(
        runtime.approval_manager._requests.values()
    )

    assert len(requests) == 1

    request = requests[0]

    assert request.status is ApprovalStatus.PENDING

    assert (
        execution.state
        is ExecutionState.WAITING_APPROVAL
    )

    approved = (
        await runtime.approval_manager.approve(
            request.approval_id
        )
    )

    assert (
        approved.status
        is ApprovalStatus.APPROVED
    )

    # The approval barrier should now complete.
    await task

    resolved = (
        await runtime.approval_manager.get(
            request.approval_id
        )
    )

    assert (
        resolved.status
        is ApprovalStatus.APPROVED
    )

    # _handle_required_approvals() only resolves approval.
    # The caller remains responsible for transitioning into
    # TOOL_EXECUTION and actually executing the tool.
    assert (
        execution.state
        is ExecutionState.WAITING_APPROVAL
    )


@pytest.mark.asyncio
async def test_rejected_approval_prevents_continuation() -> None:
    runtime = build_runtime()

    execution = build_execution()
    context = build_context(execution)

    tool_call, admission = build_delete_admission()

    admissions = [
        (
            tool_call,
            admission,
        )
    ]

    cancellation = build_cancellation()

    task = asyncio.create_task(
        runtime._handle_required_approvals(
            execution=execution,
            context=context,
            admissions=admissions,
            execution_started_at=0.0,
            cancellation=cancellation,
        )
    )

    await asyncio.sleep(0)

    requests = list(
        runtime.approval_manager._requests.values()
    )

    assert len(requests) == 1

    request = requests[0]

    rejected = (
        await runtime.approval_manager.reject(
            request.approval_id
        )
    )

    assert (
        rejected.status
        is ApprovalStatus.REJECTED
    )

    # Rejection must prevent the approval barrier from
    # completing successfully.
    with pytest.raises(
        ToolExecutionError,
        match="Human approval rejected",
    ):
        await task


@pytest.mark.asyncio
async def test_non_protected_tool_does_not_wait_for_approval() -> None:
    runtime = build_runtime()

    execution = build_execution()
    context = build_context(execution)

    tool_call = ToolCall(
        name="calculator",
        arguments={
            "expression": "1 + 1",
        },
        call_id="call-1",
    )

    admissions = [
        (
            tool_call,
            (
                "calculator",
                '{"expression":"1 + 1"}',
            ),
        )
    ]

    cancellation = build_cancellation()

    await runtime._handle_required_approvals(
        execution=execution,
        context=context,
        admissions=admissions,
        execution_started_at=0.0,
        cancellation=cancellation,
    )

    assert (
        len(
            runtime.approval_manager._requests
        )
        == 0
    )

    # No protected tool was present, so the approval handler
    # must not alter the execution lifecycle.
    assert (
        execution.state
        is ExecutionState.INFERENCE
    )


@pytest.mark.asyncio
async def test_multiple_protected_tools_require_all_approvals() -> None:
    runtime = build_runtime()

    execution = build_execution()
    context = build_context(execution)

    admissions = [
        (
            ToolCall(
                name="delete_file",
                arguments={
                    "path": "/tmp/a.txt",
                },
                call_id="call-1",
            ),
            (
                "delete_file",
                '{"path":"/tmp/a.txt"}',
            ),
        ),
        (
            ToolCall(
                name="delete_file",
                arguments={
                    "path": "/tmp/b.txt",
                },
                call_id="call-2",
            ),
            (
                "delete_file",
                '{"path":"/tmp/b.txt"}',
            ),
        ),
    ]

    cancellation = build_cancellation()

    task = asyncio.create_task(
        runtime._handle_required_approvals(
            execution=execution,
            context=context,
            admissions=admissions,
            execution_started_at=0.0,
            cancellation=cancellation,
        )
    )

    await asyncio.sleep(0)

    requests = list(
        runtime.approval_manager._requests.values()
    )

    assert len(requests) == 2

    assert all(
        request.status is ApprovalStatus.PENDING
        for request in requests
    )

    assert (
        execution.state
        is ExecutionState.WAITING_APPROVAL
    )

    # The approval barrier must still be active.
    assert not task.done()

    # Approve only the first protected tool.
    await runtime.approval_manager.approve(
        requests[0].approval_id
    )

    await asyncio.sleep(0)

    # One approval is insufficient.
    assert not task.done()

    first = (
        await runtime.approval_manager.get(
            requests[0].approval_id
        )
    )

    second = (
        await runtime.approval_manager.get(
            requests[1].approval_id
        )
    )

    assert (
        first.status
        is ApprovalStatus.APPROVED
    )

    assert (
        second.status
        is ApprovalStatus.PENDING
    )

    # Approve the second protected tool.
    await runtime.approval_manager.approve(
        requests[1].approval_id
    )

    # Now the complete approval barrier can finish.
    await task

    resolved_requests = [
        await runtime.approval_manager.get(
            request.approval_id
        )
        for request in requests
    ]

    assert all(
        request.status
        is ApprovalStatus.APPROVED
        for request in resolved_requests
    )

    # As above, approval handling does not itself transition into
    # TOOL_EXECUTION. That remains the caller's responsibility.
    assert (
        execution.state
        is ExecutionState.WAITING_APPROVAL
    )


from unittest.mock import AsyncMock, MagicMock
