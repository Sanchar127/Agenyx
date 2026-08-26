from __future__ import annotations

from typing import Any

import httpx

from app.core.errors import (
    LLMConnectionError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.core.logging import logger


class InferenceClient:
    """HTTP client for the Agenyx inference service."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 120.0,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=min(timeout, 10.0),
                read=timeout,
                write=timeout,
                pool=timeout,
            ),
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
            ),
        )

    async def close(self) -> None:
        """Close the HTTP connection pool."""

        if not self._client.is_closed:
            await self._client.aclose()

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Send a chat completion request to the inference layer."""

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        url = f"{self.base_url}/v1/chat/completions"

        logger.info(
            "inference_request_started "
            "url=%s model=%s tools=%s message_count=%s",
            url,
            model,
            len(tools),
            len(messages),
        )

        try:
            response = await self._client.post(
                url,
                json=payload,
            )

        except httpx.ConnectError as exc:
            logger.error(
                "inference_connection_error "
                "url=%s error=%s",
                self.base_url,
                str(exc),
            )

            raise LLMConnectionError(
                f"Unable to connect to inference service "
                f"at {self.base_url}"
            ) from exc

        except httpx.TimeoutException as exc:
            logger.error(
                "inference_timeout timeout=%s",
                self.timeout,
            )

            raise LLMTimeoutError(
                f"Inference request timed out after "
                f"{self.timeout}s"
            ) from exc

        except httpx.HTTPError as exc:
            logger.error(
                "inference_http_error error=%s",
                str(exc),
            )

            raise LLMConnectionError(
                "Inference HTTP request failed"
            ) from exc

        logger.info(
            "inference_http_response status=%s model=%s",
            response.status_code,
            model,
        )

        if response.status_code >= 500:
            logger.error(
                "inference_server_error "
                "status=%s body=%s",
                response.status_code,
                response.text[:2000],
            )

            raise LLMConnectionError(
                f"Inference service returned HTTP "
                f"{response.status_code}"
            )

        if response.status_code >= 400:
            logger.error(
                "inference_client_error "
                "status=%s body=%s",
                response.status_code,
                response.text[:2000],
            )

            raise LLMResponseError(
                f"Inference service returned HTTP "
                f"{response.status_code}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            logger.error(
                "inference_invalid_json_response "
                "body=%s",
                response.text[:2000],
            )

            raise LLMResponseError(
                "Inference service returned invalid JSON"
            ) from exc

        if not isinstance(data, dict):
            raise LLMResponseError(
                "Inference response must be a JSON object"
            )

        self._validate_response(data)

        logger.info(
            "inference_request_completed "
            "model=%s",
            model,
        )

        return data

    @staticmethod
    def _validate_response(
        data: dict[str, Any],
    ) -> None:
        choices = data.get("choices")

        if not isinstance(choices, list) or not choices:
            raise LLMResponseError(
                "Inference response does not contain choices"
            )

        choice = choices[0]

        if not isinstance(choice, dict):
            raise LLMResponseError(
                "Inference response contains invalid choice"
            )

        message = choice.get("message")

        if not isinstance(message, dict):
            raise LLMResponseError(
                "Inference response does not contain message"
            )
