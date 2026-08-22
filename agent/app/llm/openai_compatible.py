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

        logger.info(
            "llm_request_started "
            "model=%s base_url=%s tools=%s message_count=%s",
            self.model,
            self.base_url,
            len(tools),
            len(messages),
        )

        for attempt in range(self.max_retries + 1):
            try:
                return await self._request(
                    payload,
                    headers,
                )

            except (
                LLMConnectionError,
                LLMTimeoutError,
            ) as exc:
                if attempt >= self.max_retries:
                    logger.error(
                        "llm_request_failed "
                        "attempts=%s error=%s",
                        attempt + 1,
                        type(exc).__name__,
                    )
                    raise

                retry_number = attempt + 1

                logger.warning(
                    "llm_request_retry "
                    "attempt=%s max_retries=%s error=%s",
                    retry_number,
                    self.max_retries,
                    type(exc).__name__,
                )

                await asyncio.sleep(
                    0.5 * (2**attempt),
                )

        raise LLMConnectionError(
            "LLM request failed",
        )

    async def _request(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:

        logger.info(
            "llm_http_request "
            "url=%s model=%s tools=%s",
            f"{self.base_url}/chat/completions",
            self.model,
            len(payload.get("tools", [])),
        )

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )

        except httpx.ConnectError as exc:
            logger.error(
                "llm_connection_error "
                "url=%s error=%s",
                self.base_url,
                str(exc),
            )

            raise LLMConnectionError(
                f"Unable to connect to LLM at {self.base_url}"
            ) from exc

        except httpx.TimeoutException as exc:
            logger.error(
                "llm_timeout "
                "timeout=%s",
                self.timeout,
            )

            raise LLMTimeoutError(
                f"LLM request timed out after {self.timeout}s"
            ) from exc

        except httpx.HTTPError as exc:
            logger.error(
                "llm_http_error error=%s",
                str(exc),
            )

            raise LLMConnectionError(
                "LLM HTTP request failed"
            ) from exc

        logger.info(
            "llm_http_response "
            "status=%s",
            response.status_code,
        )

        if response.status_code >= 500:
            logger.error(
                "llm_server_error "
                "status=%s body=%s",
                response.status_code,
                response.text[:2000],
            )

            raise LLMConnectionError(
                f"LLM returned HTTP {response.status_code}"
            )

        if response.status_code >= 400:
            logger.error(
                "llm_client_error "
                "status=%s body=%s",
                response.status_code,
                response.text[:2000],
            )

            raise LLMResponseError(
                f"LLM returned HTTP {response.status_code}"
            )

        try:
            data = response.json()

        except ValueError as exc:
            logger.error(
                "llm_invalid_json_response "
                "body=%s",
                response.text[:2000],
            )

            raise LLMResponseError(
                "LLM returned invalid JSON"
            ) from exc

        logger.info(
            "llm_response_received response=%s",
            data,
        )

        try:
            choices = data.get("choices", [])

            if choices:
                message = choices[0].get(
                    "message",
                    {},
                )

                tool_calls = message.get(
                    "tool_calls",
                    [],
                )

                content = message.get(
                    "content",
                )

                logger.info(
                    "llm_response_parsed "
                    "has_content=%s "
                    "content_length=%s "
                    "tool_calls=%s",
                    isinstance(content, str),
                    len(content) if isinstance(
                        content,
                        str,
                    ) else 0,
                    len(tool_calls)
                    if isinstance(
                        tool_calls,
                        list,
                    )
                    else 0,
                )

                if tool_calls:
                    logger.info(
                        "llm_tool_calls_received "
                        "tools=%s",
                        [
                            call.get(
                                "function",
                                {},
                            ).get(
                                "name",
                            )
                            for call in tool_calls
                            if isinstance(
                                call,
                                dict,
                            )
                        ],
                    )

                else:
                    logger.info(
                        "llm_no_tool_calls "
                        "content=%s",
                        content,
                    )

        except Exception:
            logger.exception(
                "llm_response_logging_failed",
            )

        return data
