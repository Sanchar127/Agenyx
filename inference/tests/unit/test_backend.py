import asyncio
import random
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.logger import logger
from app.metrics import (
    PROVIDER_ERRORS_TOTAL,
    PROVIDER_REQUEST_DURATION_SECONDS,
    PROVIDER_REQUESTS_TOTAL,
    PROVIDER_RETRIES_TOTAL,
)


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
        """Check backend health."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close backend resources."""
        raise NotImplementedError


class OpenAICompatibleBackend(InferenceBackend):
    """
    HTTP backend for OpenAI-compatible inference APIs.

    Compatible with providers such as:

    - Ollama
    - vLLM
    - OpenAI
    - Other OpenAI-compatible servers
    """

    RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
    MAX_BACKOFF_JITTER = 0.25

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
    ) -> None:
        if not provider_name:
            raise ValueError("provider_name must not be empty")

        if not base_url:
            raise ValueError("base_url must not be empty")

        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        if max_connections <= 0:
            raise ValueError("max_connections must be greater than zero")

        if max_keepalive_connections <= 0:
            raise ValueError(
                "max_keepalive_connections must be greater than zero"
            )

        self.provider_name = provider_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
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

    @property
    def client(self) -> httpx.AsyncClient:
        """Public alias for the underlying HTTP client (used by tests)."""
        return self._client

    @client.setter
    def client(self, value: httpx.AsyncClient) -> None:
        self._client = value

    @property
    def headers(self) -> dict[str, str]:
        """Return HTTP headers for provider requests."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a non-streaming chat completion request.

        Retry behavior:

        - 4xx errors are not retried.
        - 5xx errors are retried.
        - Network errors are retried.
        - Timeout errors are retried.
        """

        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary")

        model = str(payload.get("model", "unknown"))

        for attempt in range(self.max_retries + 1):
            started_at = time.perf_counter()

            try:
                response = await self._client.post(
                    "/chat/completions",
                    headers=self.headers,
                    json=payload,
                )

                duration = time.perf_counter() - started_at

                PROVIDER_REQUEST_DURATION_SECONDS.labels(
                    provider=self.provider_name,
                    model=model,
                ).observe(duration)

                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    PROVIDER_REQUESTS_TOTAL.labels(
                        provider=self.provider_name,
                        model=model,
                        status="retryable_error",
                    ).inc()

                    if attempt < self.max_retries:
                        PROVIDER_RETRIES_TOTAL.labels(
                            provider=self.provider_name,
                            model=model,
                            reason=f"http_{response.status_code}",
                        ).inc()

                        await self._backoff(attempt)
                        continue

                    PROVIDER_ERRORS_TOTAL.labels(
                        provider=self.provider_name,
                        model=model,
                        error_type=f"http_{response.status_code}",
                    ).inc()

                    response.raise_for_status()

                if 400 <= response.status_code < 500:
                    PROVIDER_REQUESTS_TOTAL.labels(
                        provider=self.provider_name,
                        model=model,
                        status="client_error",
                    ).inc()

                    response.raise_for_status()

                response.raise_for_status()

                try:
                    data = response.json()
                except ValueError as exc:
                    PROVIDER_ERRORS_TOTAL.labels(
                        provider=self.provider_name,
                        model=model,
                        error_type="invalid_json",
                    ).inc()

                    raise RuntimeError(
                        "Inference provider returned invalid JSON"
                    ) from exc

                if not isinstance(data, dict):
                    PROVIDER_ERRORS_TOTAL.labels(
                        provider=self.provider_name,
                        model=model,
                        error_type="invalid_response",
                    ).inc()

                    raise RuntimeError(
                        "Inference provider returned a non-object response"
                    )

                PROVIDER_REQUESTS_TOTAL.labels(
                    provider=self.provider_name,
                    model=model,
                    status="success",
                ).inc()

                logger.debug(
                    "Inference request completed",
                    extra={
                        "provider": self.provider_name,
                        "model": model,
                        "duration_seconds": duration,
                        "attempt": attempt,
                    },
                )

                return data

            except httpx.TimeoutException:
                duration = time.perf_counter() - started_at

                PROVIDER_REQUEST_DURATION_SECONDS.labels(
                    provider=self.provider_name,
                    model=model,
                ).observe(duration)

                PROVIDER_ERRORS_TOTAL.labels(
                    provider=self.provider_name,
                    model=model,
                    error_type="timeout",
                ).inc()

                if attempt < self.max_retries:
                    PROVIDER_RETRIES_TOTAL.labels(
                        provider=self.provider_name,
                        model=model,
                        reason="timeout",
                    ).inc()

                    await self._backoff(attempt)
                    continue

                PROVIDER_REQUESTS_TOTAL.labels(
                    provider=self.provider_name,
                    model=model,
                    status="error",
                ).inc()

                raise

            except httpx.RequestError:
                duration = time.perf_counter() - started_at

                PROVIDER_REQUEST_DURATION_SECONDS.labels(
                    provider=self.provider_name,
                    model=model,
                ).observe(duration)

                PROVIDER_ERRORS_TOTAL.labels(
                    provider=self.provider_name,
                    model=model,
                    error_type="network_error",
                ).inc()

                if attempt < self.max_retries:
                    PROVIDER_RETRIES_TOTAL.labels(
                        provider=self.provider_name,
                        model=model,
                        reason="network_error",
                    ).inc()

                    await self._backoff(attempt)
                    continue

                PROVIDER_REQUESTS_TOTAL.labels(
                    provider=self.provider_name,
                    model=model,
                    status="error",
                ).inc()

                raise

            except httpx.HTTPStatusError:
                PROVIDER_ERRORS_TOTAL.labels(
                    provider=self.provider_name,
                    model=model,
                    error_type="http_error",
                ).inc()

                PROVIDER_REQUESTS_TOTAL.labels(
                    provider=self.provider_name,
                    model=model,
                    status="error",
                ).inc()

                raise

            except Exception as exc:
                PROVIDER_ERRORS_TOTAL.labels(
                    provider=self.provider_name,
                    model=model,
                    error_type=type(exc).__name__,
                ).inc()

                PROVIDER_REQUESTS_TOTAL.labels(
                    provider=self.provider_name,
                    model=model,
                    status="error",
                ).inc()

                logger.exception(
                    "Unexpected inference provider error",
                    extra={
                        "provider": self.provider_name,
                        "model": model,
                    },
                )

                raise

        raise RuntimeError(
            "Inference request failed after all retries"
        )

    async def chat_completion_stream(
        self,
        payload: dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """
        Execute a streaming chat completion request.

        Streaming requests are intentionally not retried because the
        response may already have been partially consumed.
        """

        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary")

        model = str(payload.get("model", "unknown"))
        started_at = time.perf_counter()

        try:
            async with self._client.stream(
                "POST",
                "/chat/completions",
                headers={
                    **self.headers,
                    "Accept": "text/event-stream",
                },
                json=payload,
            ) as response:
                response.raise_for_status()

                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk

            duration = time.perf_counter() - started_at

            PROVIDER_REQUEST_DURATION_SECONDS.labels(
                provider=self.provider_name,
                model=model,
            ).observe(duration)

            PROVIDER_REQUESTS_TOTAL.labels(
                provider=self.provider_name,
                model=model,
                status="success",
            ).inc()

        except httpx.TimeoutException:
            duration = time.perf_counter() - started_at

            PROVIDER_REQUEST_DURATION_SECONDS.labels(
                provider=self.provider_name,
                model=model,
            ).observe(duration)

            PROVIDER_ERRORS_TOTAL.labels(
                provider=self.provider_name,
                model=model,
                error_type="timeout",
            ).inc()

            PROVIDER_REQUESTS_TOTAL.labels(
                provider=self.provider_name,
                model=model,
                status="error",
            ).inc()

            raise

        except httpx.HTTPStatusError as exc:
            duration = time.perf_counter() - started_at

            PROVIDER_REQUEST_DURATION_SECONDS.labels(
                provider=self.provider_name,
                model=model,
            ).observe(duration)

            PROVIDER_ERRORS_TOTAL.labels(
                provider=self.provider_name,
                model=model,
                error_type=f"http_{exc.response.status_code}",
            ).inc()

            PROVIDER_REQUESTS_TOTAL.labels(
                provider=self.provider_name,
                model=model,
                status="error",
            ).inc()

            raise

        except httpx.RequestError:
            duration = time.perf_counter() - started_at

            PROVIDER_REQUEST_DURATION_SECONDS.labels(
                provider=self.provider_name,
                model=model,
            ).observe(duration)

            PROVIDER_ERRORS_TOTAL.labels(
                provider=self.provider_name,
                model=model,
                error_type="network_error",
            ).inc()

            PROVIDER_REQUESTS_TOTAL.labels(
                provider=self.provider_name,
                model=model,
                status="error",
            ).inc()

            raise

        except Exception as exc:
            duration = time.perf_counter() - started_at

            PROVIDER_REQUEST_DURATION_SECONDS.labels(
                provider=self.provider_name,
                model=model,
            ).observe(duration)

            PROVIDER_ERRORS_TOTAL.labels(
                provider=self.provider_name,
                model=model,
                error_type=type(exc).__name__,
            ).inc()

            PROVIDER_REQUESTS_TOTAL.labels(
                provider=self.provider_name,
                model=model,
                status="error",
            ).inc()

            logger.exception(
                "Unexpected streaming inference provider error",
                extra={
                    "provider": self.provider_name,
                    "model": model,
                },
            )

            raise

    async def health(self) -> bool:
        """Check whether the provider is reachable."""

        try:
            response = await self._client.get(
                "/models",
                headers=self.headers,
            )

            return response.is_success

        except (httpx.TimeoutException, httpx.RequestError):
            return False

        except Exception:
            logger.exception(
                "Inference provider health check failed",
                extra={
                    "provider": self.provider_name,
                },
            )

            return False

    async def close(self) -> None:
        """Close the HTTP client."""

        if not self._client.is_closed:
            await self._client.aclose()

    async def _backoff(self, attempt: int) -> None:
        """Wait using exponential backoff with jitter."""

        delay = min(
            0.5 * (2**attempt),
            10.0,
        )

        jitter = random.uniform(
            0.0,
            self.MAX_BACKOFF_JITTER,
        )

        await asyncio.sleep(delay + jitter)
