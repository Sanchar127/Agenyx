from __future__ import annotations

import asyncio
import json
from typing import Any

from app.sandbox.errors import (
    SandboxError,
    SandboxProtocolError,
    SandboxToolError,
    SandboxUnavailableError,
)


class ToolSandboxClient:
    """Client for executing tools inside the isolated sandbox."""

    def __init__(
        self,
        *,
        socket_path: str = "/sandbox/tool.sock",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.socket_path = socket_path
        self.timeout_seconds = timeout_seconds

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Execute a tool through the sandbox."""

        request = {
            "tool": name,
            "arguments": arguments,
        }

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(
                    self.socket_path,
                ),
                timeout=self.timeout_seconds,
            )

        except (
            OSError,
            asyncio.TimeoutError,
        ) as exc:
            raise SandboxUnavailableError(
                "Sandbox is unavailable"
            ) from exc

        try:
            payload = json.dumps(
                request,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"

            writer.write(payload)

            await asyncio.wait_for(
                writer.drain(),
                timeout=self.timeout_seconds,
            )

            raw_response = await asyncio.wait_for(
                reader.readline(),
                timeout=self.timeout_seconds,
            )

        except asyncio.TimeoutError as exc:
            raise SandboxUnavailableError(
                "Sandbox request timed out"
            ) from exc

        except OSError as exc:
            raise SandboxUnavailableError(
                "Sandbox connection failed"
            ) from exc

        finally:
            writer.close()

            try:
                await writer.wait_closed()
            except OSError:
                pass

        if not raw_response:
            raise SandboxProtocolError(
                "Sandbox returned an empty response"
            )

        try:
            response = json.loads(
                raw_response.decode("utf-8"),
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise SandboxProtocolError(
                "Sandbox returned invalid JSON"
            ) from exc

        if not isinstance(response, dict):
            raise SandboxProtocolError(
                "Sandbox response must be an object"
            )

        if response.get("ok") is True:
            result = response.get("result")

            if not isinstance(result, str):
                raise SandboxProtocolError(
                    "Sandbox result must be a string"
                )

            return result

        error = response.get("error")

        if not isinstance(error, str):
            error = "Sandbox tool execution failed"

        raise SandboxToolError(error)
