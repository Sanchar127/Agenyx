
import asyncio
import random
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.logger import logger


class InferenceBackend(ABC):
    """
    Abstract interface for an inference backend.

    Implementations may communicate with Ollama, vLLM, OpenAI,
    or any other OpenAI-compatible inference server.
    """

    @abstractmethod
    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a non-streaming chat completion request."""
        raise NotImplementedError

    @abstractmethod
    async def chat_completion_stream(
        self,
        payload: dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """Execute a streaming chat completion request."""
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        """Check whether the inference backend is available."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release backend resources."""
        raise NotImplementedError


class OpenAICompatibleBackend(InferenceBackend):
    """
    HTTP client for an OpenAI-compatible inference backend.

    This class is responsible only for backend communication.

    It does NOT handle:

    - model registration
    - provider selection
    - provider failover
    - circuit breaking
    - FastAPI request handling
    - authentication of Agenyx clients
    """

    RETRYABLE_STATUS_CODES = frozenset(
        {
            500,
            502,
            503,
            504,
        }
    )

    MAX_BACKOFF_JITTER_SECONDS = 0.25

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float,
        max_connections: int,
        max_keepalive_connections: int,
        max_retries: int = 2,
    ) -> None:
        """
        Create an OpenAI-compatible HTTP backend.
        """

        self._validate_configuration(
            base_url=base_url,
            timeout=timeout,
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            max_retries=max_retries,
        )

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_retries = max_retries

        self.client = httpx.AsyncClient(
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

        logger.info(
            "Inference backend initialized",
            extra={
                "backend_url": self.base_url,
                "max_retries": self.max_retries,
                "max_connections": max_connections,
                "max_keepalive_connections": (
                    max_keepalive_connections
                ),
            },
        )

    # =====================================================
    # CONFIGURATION
    # =====================================================

    @staticmethod
    def _validate_configuration(
        *,
        base_url: str,
        timeout: float,
        max_connections: int,
        max_keepalive_connections: int,
        max_retries: int,
    ) -> None:
        """
        Validate backend configuration.
        """

        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError(
                "base_url must be a non-empty string"
            )

        if timeout <= 0:
            raise ValueError(
                "timeout must be greater than 0"
            )

        if max_connections < 1:
            raise ValueError(
                "max_connections must be >= 1"
            )

        if max_keepalive_connections < 0:
            raise ValueError(
                "max_keepalive_connections must be >= 0"
            )

        if max_keepalive_connections > max_connections:
            raise ValueError(
                "max_keepalive_connections must be <= "
                "max_connections"
            )

        if max_retries < 0:
            raise ValueError(
                "max_retries must be >= 0"
            )

    # =====================================================
    # HEADERS
    # =====================================================

    @property
    def headers(self) -> dict[str, str]:
        """
        Build headers for provider requests.
        """

        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # =====================================================
    # CHAT COMPLETION
    # =====================================================

    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Send a non-streaming chat completion request.

        Retry policy:

            2xx
                Return response.

            4xx
                Do not retry.

            5xx
                Retry transient server failures.

            timeout
                Retry.

            connection/network failure
                Retry.

        Retries use exponential backoff with jitter.
        """

        if not isinstance(payload, dict):
            raise TypeError(
                "payload must be a dictionary"
            )

        url = f"{self.base_url}/chat/completions"

        model = payload.get("model", "unknown")

        logger.info(
            "Backend inference request started",
            extra={
                "model": model,
                "max_retries": self.max_retries,
            },
        )

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.post(
                    url,
                    json=payload,
                    headers=self.headers,
                )

                # -------------------------------------------------
                # Client errors
                # -------------------------------------------------

                if 400 <= response.status_code < 500:
                    logger.warning(
                        "Backend returned client error",
                        extra={
                            "model": model,
                            "status_code": response.status_code,
                            "attempt": attempt,
                        },
                    )

                    response.raise_for_status()

                # -------------------------------------------------
                # Transient provider errors
                # -------------------------------------------------

                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    logger.warning(
                        "Backend returned retryable error",
                        extra={
                            "model": model,
                            "status_code": response.status_code,
                            "attempt": attempt,
                            "max_retries": self.max_retries,
                        },
                    )

                    if attempt >= self.max_retries:
                        logger.error(
                            "Backend request failed after retries",
                            extra={
                                "model": model,
                                "status_code": response.status_code,
                                "attempt": attempt,
                            },
                        )

                        response.raise_for_status()

                    await self._backoff(attempt)
                    continue

                # -------------------------------------------------
                # Unexpected status codes
                # -------------------------------------------------

                response.raise_for_status()

                # -------------------------------------------------
                # Parse response
                # -------------------------------------------------

                try:
                    data = response.json()

                except ValueError as exc:
                    logger.error(
                        "Backend returned invalid JSON",
                        extra={
                            "model": model,
                            "status_code": response.status_code,
                        },
                        exc_info=True,
                    )

                    raise RuntimeError(
                        "Inference backend returned invalid JSON"
                    ) from exc

                if not isinstance(data, dict):
                    logger.error(
                        "Backend returned non-object JSON",
                        extra={
                            "model": model,
                            "response_type": type(data).__name__,
                        },
                    )

                    raise RuntimeError(
                        "Inference backend returned a "
                        "non-object JSON response"
                    )

                logger.info(
                    "Backend inference request completed",
                    extra={
                        "model": model,
                        "status_code": response.status_code,
                        "attempt": attempt,
                    },
                )

                return data

            except httpx.TimeoutException:
                logger.warning(
                    "Backend request timed out",
                    extra={
                        "model": model,
                        "attempt": attempt,
                        "max_retries": self.max_retries,
                    },
                )

                if attempt >= self.max_retries:
                    logger.error(
                        "Backend request failed due to timeout",
                        extra={
                            "model": model,
                            "attempt": attempt,
                        },
                        exc_info=True,
                    )
                    raise

                await self._backoff(attempt)

            except httpx.NetworkError:
                logger.warning(
                    "Backend network error",
                    extra={
                        "model": model,
                        "attempt": attempt,
                        "max_retries": self.max_retries,
                    },
                    exc_info=True,
                )

                if attempt >= self.max_retries:
                    logger.error(
                        "Backend request failed due to network error",
                        extra={
                            "model": model,
                            "attempt": attempt,
                        },
                        exc_info=True,
                    )
                    raise

                await self._backoff(attempt)

        raise RuntimeError(
            "Inference request failed after all retry attempts"
        )

    # =====================================================
    # STREAMING
    # =====================================================

    async def chat_completion_stream(
        self,
        payload: dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """
        Stream an OpenAI-compatible chat completion response.

        Streaming requests are intentionally NOT retried.
        """

        if not isinstance(payload, dict):
            raise TypeError(
                "payload must be a dictionary"
            )

        url = f"{self.base_url}/chat/completions"

        model = payload.get("model", "unknown")

        logger.info(
            "Backend streaming request started",
            extra={
                "model": model,
            },
        )

        try:
            async with self.client.stream(
                "POST",
                url,
                json=payload,
                headers=self.headers,
            ) as response:

                if response.status_code >= 400:
                    logger.error(
                        "Backend streaming request failed",
                        extra={
                            "model": model,
                            "status_code": response.status_code,
                        },
                    )

                    body = await response.aread()

                    error_response = httpx.Response(
                        status_code=response.status_code,
                        headers=response.headers,
                        content=body,
                        request=response.request,
                    )

                    error_response.raise_for_status()

                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk

            logger.info(
                "Backend streaming request completed",
                extra={
                    "model": model,
                },
            )

        except httpx.HTTPError:
            logger.error(
                "Backend streaming HTTP error",
                extra={
                    "model": model,
                },
                exc_info=True,
            )
            raise

    # =====================================================
    # RETRY BACKOFF
    # =====================================================

    async def _backoff(
        self,
        attempt: int,
    ) -> None:
        """
        Apply exponential backoff with jitter.
        """

        base_delay = 0.5 * (2**attempt)

        jitter = random.uniform(
            0,
            self.MAX_BACKOFF_JITTER_SECONDS,
        )

        delay = base_delay + jitter

        logger.debug(
            "Backend retry backoff",
            extra={
                "attempt": attempt,
                "delay_seconds": round(delay, 3),
            },
        )

        await asyncio.sleep(delay)

    # =====================================================
    # HEALTH
    # =====================================================

    async def health(self) -> bool:
        """
        Check whether the backend is reachable.
        """

        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                },
            )

            healthy = response.is_success

            if healthy:
                logger.debug(
                    "Inference backend health check passed",
                    extra={
                        "status_code": response.status_code,
                    },
                )
            else:
                logger.warning(
                    "Inference backend health check failed",
                    extra={
                        "status_code": response.status_code,
                    },
                )

            return healthy

        except httpx.HTTPError:
            logger.warning(
                "Inference backend health check failed",
                exc_info=True,
            )

            return False

    # =====================================================
    # CLOSE
    # =====================================================

    async def close(self) -> None:
        """
        Close the underlying HTTP client.

        Safe to call multiple times.
        """

        if not self.client.is_closed:
            logger.info(
                "Closing inference backend HTTP client",
            )

            await self.client.aclose()

            logger.info(
                "Inference backend HTTP client closed",
            )
