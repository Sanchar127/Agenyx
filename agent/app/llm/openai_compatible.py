import asyncio
from typing import Any

import httpx

from app.core.errors import (
    LLMConnectionError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.core.logging import logger
from app.llm.base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(self.max_retries + 1):
            try:
                return await self._request(
                    payload,
                    headers,
                )

            except (LLMConnectionError, LLMTimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise

                retry_number = attempt + 1

                logger.warning(
                    "llm_request_retry "
                    "attempt=%s max_retries=%s error=%s",
                    retry_number,
                    self.max_retries,
                    type(exc).__name__,
                )

                await asyncio.sleep(0.5 * (2**attempt))

        raise LLMConnectionError("LLM request failed")

    async def _request(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )

        except httpx.ConnectError as exc:
            raise LLMConnectionError(
                f"Unable to connect to LLM at {self.base_url}"
            ) from exc

        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"LLM request timed out after {self.timeout}s"
            ) from exc

        except httpx.HTTPError as exc:
            raise LLMConnectionError(
                "LLM HTTP request failed"
            ) from exc

        if response.status_code >= 500:
            raise LLMConnectionError(
                f"LLM returned HTTP {response.status_code}"
            )

        if response.status_code >= 400:
            raise LLMResponseError(
                f"LLM returned HTTP {response.status_code}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise LLMResponseError(
                "LLM returned invalid JSON"
            ) from exc
