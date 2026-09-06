from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.agent_runtime.domain.context import ExecutionContext


class ApprovalStatus(str, Enum):
    """
    Lifecycle state of a human approval request.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRequiredError(Exception):
    """Raised when a tool requires human approval."""


class ApprovalNotFoundError(Exception):
    """Raised when an approval request cannot be found."""


class ApprovalAlreadyResolvedError(Exception):
    """Raised when an approval has already been resolved."""


@dataclass(frozen=True)
class ApprovalRequest:
    """
    Represents a human approval request for one tool call.

    The request is correlated to the exact agent execution and
    exact model-generated tool call.
    """

    approval_id: str
    execution_id: str
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    status: ApprovalStatus = ApprovalStatus.PENDING


class ApprovalPolicy(ABC):
    """
    Determines whether a tool call requires human approval.
    """

    @abstractmethod
    async def requires_approval(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> bool:
        raise NotImplementedError


@dataclass(frozen=True)
class AllowListApprovalPolicy(ApprovalPolicy):
    """
    Requires approval for explicitly configured tools.
    """

    approval_required_tools: frozenset[str]

    @classmethod
    def from_tools(
        cls,
        tools: set[str]
        | list[str]
        | tuple[str, ...],
    ) -> AllowListApprovalPolicy:
        return cls(
            approval_required_tools=frozenset(
                tools
            )
        )

    async def requires_approval(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> bool:
        return (
            tool_name
            in self.approval_required_tools
        )


class ApprovalManager:
    """
    Manages human approval requests and their decisions.

    This Phase 1 implementation is intentionally in-memory.

    Approval state is represented by:

        _requests
            Stores the current ApprovalRequest.

        _events
            One asyncio.Event per approval request.

    The event allows the runtime to asynchronously wait for a
    human decision without polling.

    Persistent approval state will be introduced later with
    Persistent Execution.
    """

    def __init__(self) -> None:
        self._requests: dict[
            str,
            ApprovalRequest,
        ] = {}

        self._events: dict[
            str,
            asyncio.Event,
        ] = {}

    async def create_request(
        self,
        *,
        approval_id: str,
        execution_id: str,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ApprovalRequest:
        """
        Create a new pending approval request.
        """

        if not approval_id:
            raise ValueError(
                "approval_id cannot be empty"
            )

        if not execution_id:
            raise ValueError(
                "execution_id cannot be empty"
            )

        if not call_id:
            raise ValueError(
                "call_id cannot be empty"
            )

        if not tool_name:
            raise ValueError(
                "tool_name cannot be empty"
            )

        if approval_id in self._requests:
            raise ValueError(
                "Approval request already exists: "
                f"{approval_id}"
            )

        request = ApprovalRequest(
            approval_id=approval_id,
            execution_id=execution_id,
            call_id=call_id,
            tool_name=tool_name,
            arguments=dict(arguments),
            status=ApprovalStatus.PENDING,
        )

        self._requests[approval_id] = request

        # Create the event before returning the request.
        #
        # The runtime can safely begin waiting immediately after
        # request creation.
        self._events[approval_id] = (
            asyncio.Event()
        )

        return request

    async def get(
        self,
        approval_id: str,
    ) -> ApprovalRequest:
        """
        Return an approval request by ID.
        """

        request = self._requests.get(
            approval_id
        )

        if request is None:
            raise ApprovalNotFoundError(
                "Approval request not found: "
                f"{approval_id}"
            )

        return request

    async def wait_for_resolution(
        self,
        approval_id: str,
    ) -> ApprovalRequest:
        """
        Wait until an approval request is resolved.

        If the request is already APPROVED or REJECTED,
        return immediately.

        Otherwise wait asynchronously for approve() or reject()
        to signal the request's event.
        """

        request = await self.get(
            approval_id
        )

        # Important for race safety:
        #
        # The request may have been resolved between creation
        # and the runtime beginning to wait.
        if request.status is not ApprovalStatus.PENDING:
            return request

        event = self._events.get(
            approval_id
        )

        if event is None:
            raise ApprovalNotFoundError(
                "Approval event not found: "
                f"{approval_id}"
            )

        await event.wait()

        # Re-read the request after the event is signalled so the
        # caller receives the resolved immutable request.
        return await self.get(
            approval_id
        )

    async def approve(
        self,
        approval_id: str,
    ) -> ApprovalRequest:
        """
        Approve a pending request.
        """

        request = await self.get(
            approval_id
        )

        if request.status is not ApprovalStatus.PENDING:
            raise ApprovalAlreadyResolvedError(
                "Approval request already resolved: "
                f"{approval_id}"
            )

        resolved = ApprovalRequest(
            approval_id=request.approval_id,
            execution_id=request.execution_id,
            call_id=request.call_id,
            tool_name=request.tool_name,
            arguments=dict(
                request.arguments
            ),
            status=ApprovalStatus.APPROVED,
        )

        self._requests[approval_id] = (
            resolved
        )

        event = self._events.get(
            approval_id
        )

        if event is not None:
            event.set()

        return resolved

    async def reject(
        self,
        approval_id: str,
    ) -> ApprovalRequest:
        """
        Reject a pending request.
        """

        request = await self.get(
            approval_id
        )

        if request.status is not ApprovalStatus.PENDING:
            raise ApprovalAlreadyResolvedError(
                "Approval request already resolved: "
                f"{approval_id}"
            )

        resolved = ApprovalRequest(
            approval_id=request.approval_id,
            execution_id=request.execution_id,
            call_id=request.call_id,
            tool_name=request.tool_name,
            arguments=dict(
                request.arguments
            ),
            status=ApprovalStatus.REJECTED,
        )

        self._requests[approval_id] = (
            resolved
        )

        event = self._events.get(
            approval_id
        )

        if event is not None:
            event.set()

        return resolved
