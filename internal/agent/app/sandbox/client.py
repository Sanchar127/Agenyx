from __future__ import annotations

from typing import Any

import httpx

from app.sandbox.errors import (
    SandboxProtocolError,
    SandboxToolError,
    SandboxUnavailableError,
)


class ToolSandboxClient:
    """Client for executing tools inside the isolated sandbox."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                timeout_seconds,
                connect=2.0,
            ),
        )

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        request = {
            "tool": name,
            "arguments": arguments,
        }

        try:
            response = await self.client.post(
                "/execute",
                json=request,
            )

        except httpx.ConnectError as exc:
            raise SandboxUnavailableError(
                "Sandbox is unavailable"
            ) from exc

        except httpx.TimeoutException as exc:
            raise SandboxUnavailableError(
                "Sandbox request timed out"
            ) from exc

        except httpx.HTTPError as exc:
            raise SandboxUnavailableError(
                "Sandbox connection failed"
            ) from exc

        try:
            payload = response.json()

        except ValueError as exc:
            raise SandboxProtocolError(
                "Sandbox returned invalid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise SandboxProtocolError(
                "Sandbox response must be an object"
            )

        if payload.get("ok") is True:
            result = payload.get("result")

            if not isinstance(result, str):
                raise SandboxProtocolError(
                    "Sandbox result must be a string"
                )

            return result

        error = payload.get("error")

        if not isinstance(error, str):
            error = "Sandbox tool execution failed"

        raise SandboxToolError(error)

    async def close(self) -> None:
        await self.client.aclose()
