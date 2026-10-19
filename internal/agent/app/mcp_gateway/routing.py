from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


ASGIMessage = dict[str, Any]
ASGIReceive = Callable[[], Awaitable[ASGIMessage]]
ASGISend = Callable[[ASGIMessage], Awaitable[None]]


class MCPRootPathMiddleware:
    """Dispatch the exact MCP mount path without a trailing-slash redirect.

    Starlette's Mount normally redirects /mcp to /mcp/. For the exact path,
    dispatch directly to the same MCP ASGI application with its internal path
    set to /. The MCP app's own middleware, including bearer authentication,
    remains responsible for processing the request.
    """

    def __init__(self, app: Any, mcp_app: Any) -> None:
        self.app = app
        self.mcp_app = mcp_app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        if scope["type"] != "http" or scope.get("path") != "/mcp":
            await self.app(scope, receive, send)
            return

        mcp_scope = dict(scope)
        mcp_scope["path"] = "/"
        mcp_scope["raw_path"] = b"/"
        mcp_scope["root_path"] = (
            scope.get("root_path", "").rstrip("/") + "/mcp"
        )

        await self.mcp_app(mcp_scope, receive, send)
