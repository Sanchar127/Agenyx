from __future__ import annotations

import hmac
import json
from collections.abc import Awaitable, Callable
from typing import Any


ASGIMessage = dict[str, Any]
ASGIReceive = Callable[[], Awaitable[ASGIMessage]]
ASGISend = Callable[[ASGIMessage], Awaitable[None]]


class BearerTokenMiddleware:
    """Require a dedicated static bearer token for every MCP HTTP request."""

    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        authorization = next(
            (
                value
                for name, value in scope.get("headers", [])
                if name.lower() == b"authorization"
            ),
            None,
        )

        scheme, separator, supplied_token = (
            authorization.decode("latin-1").partition(" ")
            if authorization is not None
            else ("", "", "")
        )

        valid = (
            bool(self.token)
            and separator == " "
            and scheme.lower() == "bearer"
            and bool(supplied_token)
            and hmac.compare_digest(
                supplied_token.encode("utf-8"),
                self.token.encode("utf-8"),
            )
        )

        if valid:
            await self.app(scope, receive, send)
            return

        body = json.dumps(
            {
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "A valid bearer token is required.",
                }
            }
        ).encode("utf-8")

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"www-authenticate", b"Bearer"),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )
