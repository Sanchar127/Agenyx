from __future__ import annotations

import ast
import asyncio
import json
import logging
import operator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s %(levelname)s "
        "%(name)s: %(message)s"
    ),
)

logger = logging.getLogger("sandbox")


# ─────────────────────────────────────────────
# Limits
# ─────────────────────────────────────────────

MAX_REQUEST_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_TOOL_EXECUTION_SECONDS = 5.0
MAX_EXPRESSION_LENGTH = 1024


# ─────────────────────────────────────────────
# Calculator
# ─────────────────────────────────────────────

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

    if len(expression) > MAX_EXPRESSION_LENGTH:
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
    ) -> int | float:

        if (
            isinstance(node, ast.Constant)
            and isinstance(
                node.value,
                (int, float),
            )
        ):
            return node.value

        if isinstance(node, ast.BinOp):
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


# ─────────────────────────────────────────────
# Tool registry
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# Response helpers
# ─────────────────────────────────────────────

def build_error(
    *,
    status_code: int,
    error: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "error": error,
        },
    )


def response_size(
    response: dict[str, Any],
) -> int:
    """Return serialized response size."""

    return len(
        json.dumps(
            response,
            separators=(",", ":"),
        ).encode("utf-8"),
    )


# ─────────────────────────────────────────────
# FastAPI application
# ─────────────────────────────────────────────

app = FastAPI(
    title="Agenyx Sandbox",
    version="0.1.0",
)


# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    """Sandbox liveness endpoint."""

    return {
        "status": "ok",
    }


# ─────────────────────────────────────────────
# Tool execution
# ─────────────────────────────────────────────

@app.post("/execute")
async def execute(
    request: Request,
) -> JSONResponse:
    """Execute an allow-listed tool."""

    logger.info(
        "sandbox_request_received",
    )

    # ─────────────────────────────────────────
    # Request size protection
    # ─────────────────────────────────────────

    content_length = request.headers.get(
        "content-length",
    )

    if content_length is not None:

        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                return build_error(
                    status_code=413,
                    error="Sandbox request too large",
                )

        except ValueError:
            return build_error(
                status_code=400,
                error="Invalid Content-Length",
            )

    try:
        raw_body = await request.body()

    except Exception:
        logger.exception(
            "sandbox_request_read_failed",
        )

        return build_error(
            status_code=400,
            error="Unable to read request body",
        )

    if len(raw_body) > MAX_REQUEST_BYTES:
        return build_error(
            status_code=413,
            error="Sandbox request too large",
        )

    # ─────────────────────────────────────────
    # Parse JSON
    # ─────────────────────────────────────────

    try:
        request_body = json.loads(
            raw_body.decode("utf-8"),
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return build_error(
            status_code=400,
            error="Invalid JSON request",
        )

    # ─────────────────────────────────────────
    # Validate request
    # ─────────────────────────────────────────

    if not isinstance(request_body, dict):
        return build_error(
            status_code=400,
            error="Request must be an object",
        )

    name = request_body.get("tool")

    arguments = request_body.get(
        "arguments",
        {},
    )

    if not isinstance(name, str):
        return build_error(
            status_code=400,
            error="Tool name must be a string",
        )

    if not isinstance(arguments, dict):
        return build_error(
            status_code=400,
            error="Tool arguments must be an object",
        )

    # ─────────────────────────────────────────
    # Tool execution
    # ─────────────────────────────────────────

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
            timeout=MAX_TOOL_EXECUTION_SECONDS,
        )

    except asyncio.TimeoutError:

        logger.warning(
            "sandbox_tool_timeout tool=%s",
            name,
        )

        return build_error(
            status_code=504,
            error="Tool execution timed out",
        )

    except Exception as exc:

        logger.exception(
            "sandbox_tool_failed tool=%s",
            name,
        )

        return build_error(
            status_code=400,
            error=str(exc),
        )

    # ─────────────────────────────────────────
    # Build response
    # ─────────────────────────────────────────

    response = {
        "ok": True,
        "result": result,
    }

    # ─────────────────────────────────────────
    # Response size protection
    # ─────────────────────────────────────────

    if response_size(response) > MAX_RESPONSE_BYTES:

        logger.error(
            "sandbox_response_too_large tool=%s",
            name,
        )

        return build_error(
            status_code=500,
            error="Sandbox response too large",
        )

    logger.info(
        "sandbox_tool_completed tool=%s",
        name,
    )

    return JSONResponse(
        status_code=200,
        content=response,
    )
