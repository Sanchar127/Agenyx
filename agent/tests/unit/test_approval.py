
from __future__ import annotations

import pytest

from app.agent_runtime.approval import (
    AllowListApprovalPolicy,
    ApprovalAlreadyResolvedError,
    ApprovalManager,
    ApprovalNotFoundError,
    ApprovalStatus,
)
from app.agent_runtime.domain import (
    Execution,
    ExecutionContext,
)


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(
        execution=Execution()
    )




@pytest.mark.asyncio
async def test_allow_list_requires_approval_for_configured_tool(
    context: ExecutionContext,
) -> None:
    policy = AllowListApprovalPolicy.from_tools(
        {"delete_file"}
    )

    assert await policy.requires_approval(
        tool_name="delete_file",
        arguments={"path": "/tmp/test.txt"},
        context=context,
    )


@pytest.mark.asyncio
async def test_allow_list_does_not_require_approval_for_other_tool(
    context: ExecutionContext,
) -> None:
    policy = AllowListApprovalPolicy.from_tools(
        {"delete_file"}
    )

    assert not await policy.requires_approval(
        tool_name="calculator",
        arguments={"expression": "1 + 1"},
        context=context,
    )


@pytest.mark.asyncio
async def test_create_approval_request() -> None:
    manager = ApprovalManager()

    request = await manager.create_request(
        approval_id="approval-1",
        execution_id="execution-1",
        call_id="call-1",
        tool_name="delete_file",
        arguments={
            "path": "/tmp/test.txt",
        },
    )

    assert request.approval_id == "approval-1"
    assert request.execution_id == "execution-1"
    assert request.call_id == "call-1"
    assert request.tool_name == "delete_file"
    assert request.arguments == {
        "path": "/tmp/test.txt",
    }
    assert request.status is ApprovalStatus.PENDING


@pytest.mark.asyncio
async def test_get_approval_request() -> None:
    manager = ApprovalManager()

    created = await manager.create_request(
        approval_id="approval-1",
        execution_id="execution-1",
        call_id="call-1",
        tool_name="delete_file",
        arguments={
            "path": "/tmp/test.txt",
        },
    )

    fetched = await manager.get(
        "approval-1"
    )

    assert fetched == created


@pytest.mark.asyncio
async def test_approve_request() -> None:
    manager = ApprovalManager()

    await manager.create_request(
        approval_id="approval-1",
        execution_id="execution-1",
        call_id="call-1",
        tool_name="delete_file",
        arguments={
            "path": "/tmp/test.txt",
        },
    )

    approved = await manager.approve(
        "approval-1"
    )

    assert approved.status is ApprovalStatus.APPROVED
    assert approved.approval_id == "approval-1"
    assert approved.execution_id == "execution-1"
    assert approved.call_id == "call-1"


@pytest.mark.asyncio
async def test_reject_request() -> None:
    manager = ApprovalManager()

    await manager.create_request(
        approval_id="approval-1",
        execution_id="execution-1",
        call_id="call-1",
        tool_name="delete_file",
        arguments={
            "path": "/tmp/test.txt",
        },
    )

    rejected = await manager.reject(
        "approval-1"
    )

    assert rejected.status is ApprovalStatus.REJECTED


@pytest.mark.asyncio
async def test_cannot_approve_already_approved_request() -> None:
    manager = ApprovalManager()

    await manager.create_request(
        approval_id="approval-1",
        execution_id="execution-1",
        call_id="call-1",
        tool_name="delete_file",
        arguments={},
    )

    await manager.approve(
        "approval-1"
    )

    with pytest.raises(
        ApprovalAlreadyResolvedError
    ):
        await manager.approve(
            "approval-1"
        )


@pytest.mark.asyncio
async def test_cannot_reject_already_rejected_request() -> None:
    manager = ApprovalManager()

    await manager.create_request(
        approval_id="approval-1",
        execution_id="execution-1",
        call_id="call-1",
        tool_name="delete_file",
        arguments={},
    )

    await manager.reject(
        "approval-1"
    )

    with pytest.raises(
        ApprovalAlreadyResolvedError
    ):
        await manager.reject(
            "approval-1"
        )


@pytest.mark.asyncio
async def test_cannot_approve_rejected_request() -> None:
    manager = ApprovalManager()

    await manager.create_request(
        approval_id="approval-1",
        execution_id="execution-1",
        call_id="call-1",
        tool_name="delete_file",
        arguments={},
    )

    await manager.reject(
        "approval-1"
    )

    with pytest.raises(
        ApprovalAlreadyResolvedError
    ):
        await manager.approve(
            "approval-1"
        )


@pytest.mark.asyncio
async def test_cannot_reject_approved_request() -> None:
    manager = ApprovalManager()

    await manager.create_request(
        approval_id="approval-1",
        execution_id="execution-1",
        call_id="call-1",
        tool_name="delete_file",
        arguments={},
    )

    await manager.approve(
        "approval-1"
    )

    with pytest.raises(
        ApprovalAlreadyResolvedError
    ):
        await manager.reject(
            "approval-1"
        )


@pytest.mark.asyncio
async def test_missing_approval_request() -> None:
    manager = ApprovalManager()

    with pytest.raises(
        ApprovalNotFoundError
    ):
        await manager.get(
            "does-not-exist"
        )


@pytest.mark.asyncio
async def test_duplicate_approval_id_is_rejected() -> None:
    manager = ApprovalManager()

    await manager.create_request(
        approval_id="approval-1",
        execution_id="execution-1",
        call_id="call-1",
        tool_name="delete_file",
        arguments={},
    )

    with pytest.raises(
        ValueError,
        match="Approval request already exists",
    ):
        await manager.create_request(
            approval_id="approval-1",
            execution_id="execution-2",
            call_id="call-2",
            tool_name="send_email",
            arguments={},
        )


@pytest.mark.asyncio
async def test_approval_request_preserves_arguments() -> None:
    manager = ApprovalManager()

    arguments = {
        "path": "/important/file.txt",
        "recursive": True,
    }

    request = await manager.create_request(
        approval_id="approval-1",
        execution_id="execution-1",
        call_id="call-1",
        tool_name="delete_file",
        arguments=arguments,
    )

    arguments["recursive"] = False

    assert request.arguments == {
        "path": "/important/file.txt",
        "recursive": True,
    }
