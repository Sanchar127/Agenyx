from __future__ import annotations

import ast
import asyncio
import json
import logging
import operator
import os
import signal
from pathlib import Path
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s %(levelname)s "
        "%(name)s: %(message)s"
    ),
)

logger = logging.getLogger("sandbox")


SOCKET_PATH = os.getenv(
    "SANDBOX_SOCKET_PATH",
    "/sandbox/tool.sock",
)

MAX_REQUEST_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 64 * 1024


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def calculator(expression: str) -> str:
    """Safely evaluate a basic arithmetic expression."""

    if not isinstance(expression, str):
        raise ValueError(
            "expression must be a string"
        )

    if len(expression) > 1024:
        raise ValueError(
            "expression is too long"
        )

    try:
        tree = ast.parse(
            expression,
            mode="eval",
        )

    except SyntaxError as exc:
        raise ValueError(
            "Invalid mathematical expression"
        ) from exc

    def evaluate(
        node: ast.AST,
    ) -> float:
        if isinstance(
            node,
            ast.Constant,
        ) and isinstance(
            node.value,
            (int, float),
        ):
            return node.value

        if isinstance(
            node,
            ast.BinOp,
        ):
            operation = _OPERATORS.get(
                type(node.op),
            )

            if operation is None:
                raise ValueError(
                    "Unsupported operator"
                )

            return operation(
                evaluate(node.left),
                evaluate(node.right),
            )

        raise ValueError(
            "Unsupported expression"
        )

    return str(
        evaluate(tree.body),
    )


TOOLS = {
    "calculator": calculator,
}


def execute_tool(
    name: str,
    arguments: dict[str, Any],
) -> str:
    """Execute an allow-listed tool."""

    tool = TOOLS.get(name)

    if tool is None:
        raise ValueError(
            f"Unknown tool: {name}"
        )

    return str(
        tool(**arguments),
    )


def build_response(
    *,
    ok: bool,
    result: str | None = None,
    error: str | None = None,
) -> bytes:
    response: dict[str, Any] = {
        "ok": ok,
    }

    if result is not None:
        response["result"] = result

    if error is not None:
        response["error"] = error

    payload = json.dumps(
        response,
        separators=(",", ":"),
    ).encode("utf-8")

    if len(payload) > MAX_RESPONSE_BYTES:
        payload = json.dumps(
            {
                "ok": False,
                "error": "Sandbox response too large",
            },
            separators=(",", ":"),
        ).encode("utf-8")

    return payload + b"\n"


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle one sandbox request."""

    try:
        raw_request = await asyncio.wait_for(
            reader.readline(),
            timeout=5.0,
        )

        if not raw_request:
            return

        if len(raw_request) > MAX_REQUEST_BYTES:
            writer.write(
                build_response(
                    ok=False,
                    error="Sandbox request too large",
                ),
            )
            await writer.drain()
            return

        try:
            request = json.loads(
                raw_request.decode("utf-8"),
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            writer.write(
                build_response(
                    ok=False,
                    error="Invalid JSON request",
                ),
            )
            await writer.drain()
            return

        if not isinstance(request, dict):
            writer.write(
                build_response(
                    ok=False,
                    error="Request must be an object",
                ),
            )
            await writer.drain()
            return

        name = request.get("tool")
        arguments = request.get(
            "arguments",
            {},
        )

        if not isinstance(name, str):
            writer.write(
                build_response(
                    ok=False,
                    error="Tool name must be a string",
                ),
            )
            await writer.drain()
            return

        if not isinstance(arguments, dict):
            writer.write(
                build_response(
                    ok=False,
                    error="Tool arguments must be an object",
                ),
            )
            await writer.drain()
            return

        logger.info(
            "sandbox_tool_started tool=%s",
            name,
        )

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    execute_tool,
                    name,
                    arguments,
                ),
                timeout=5.0,
            )

        except asyncio.TimeoutError:
            writer.write(
                build_response(
                    ok=False,
                    error="Tool execution timed out",
                ),
            )
            await writer.drain()
            return

        except Exception as exc:
            logger.exception(
                "sandbox_tool_failed tool=%s",
                name,
            )

            writer.write(
                build_response(
                    ok=False,
                    error=str(exc),
                ),
            )
            await writer.drain()
            return

        logger.info(
            "sandbox_tool_completed tool=%s",
            name,
        )

        writer.write(
            build_response(
                ok=True,
                result=result,
            ),
        )

        await writer.drain()

    except asyncio.TimeoutError:
        logger.warning(
            "sandbox_client_timeout",
        )

    except Exception:
        logger.exception(
            "sandbox_client_failed",
        )

    finally:
        writer.close()

        try:
            await writer.wait_closed()
        except OSError:
            pass


async def main() -> None:
    """Start the sandbox Unix socket server."""

    socket = Path(SOCKET_PATH)

    socket.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        socket.unlink()

    except FileNotFoundError:
        pass

    server = await asyncio.start_unix_server(
        handle_client,
        path=SOCKET_PATH,
    )

    os.chmod(
        SOCKET_PATH,
        0o660,
    )

    logger.info(
        "sandbox_started socket=%s",
        SOCKET_PATH,
    )

    stop_event = asyncio.Event()

    def request_shutdown() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()

    for sig in (
        signal.SIGTERM,
        signal.SIGINT,
    ):
        try:
            loop.add_signal_handler(
                sig,
                request_shutdown,
            )
        except NotImplementedError:
            pass

    async with server:
        await stop_event.wait()

    logger.info(
        "sandbox_stopped",
    )


if __name__ == "__main__":
    asyncio.run(main())
