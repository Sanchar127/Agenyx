from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import FrozenSet

from app.agent_runtime.domain.context import ExecutionContext


class ToolAuthorizationError(Exception):
    """
    Raised when a tool execution is not authorized.
    """


class ToolAuthorization(ABC):
    """
    Authorization boundary for tool execution.

    Implementations decide whether a particular execution context
    is allowed to invoke a specific tool.
    """

    @abstractmethod
    async def authorize(
        self,
        *,
        tool_name: str,
        context: ExecutionContext,
    ) -> None:
        """
        Authorize a tool invocation.

        Returns normally when the invocation is allowed.

        Raises ToolAuthorizationError when the invocation is denied.
        """
        raise NotImplementedError


@dataclass(frozen=True)
class AllowListToolAuthorization(ToolAuthorization):
    """
    Explicit allow-list authorization policy.

    A tool is authorized only when its name is present in the
    configured allow-list.

    Security model:

        explicitly allowed -> ALLOW
        everything else    -> DENY
    """

    allowed_tools: FrozenSet[str]

    @classmethod
    def from_tools(
        cls,
        tools: set[str] | list[str] | tuple[str, ...],
    ) -> AllowListToolAuthorization:
        """
        Construct an authorization policy from tool names.
        """
        return cls(
            allowed_tools=frozenset(tools),
        )

    async def authorize(
        self,
        *,
        tool_name: str,
        context: ExecutionContext,
    ) -> None:
        """
        Authorize a tool invocation using the configured allow-list.

        The execution context is intentionally accepted even though
        this first policy does not use it yet. Future policies can
        use execution identity, metadata, roles, scopes, or other
        execution attributes without changing the interface.
        """
        if tool_name not in self.allowed_tools:
            raise ToolAuthorizationError(
                f"Tool '{tool_name}' is not authorized"
            )
