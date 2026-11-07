"""Embedding client for RAG.

Wraps an OpenAI-compatible embedding endpoint (e.g. Ollama, vLLM,
OpenAI text-embedding models) and provides async embedding of single
texts and batches, with retries and structured logging.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.logger import logger
from app.metrics import (
    PROVIDER_ERRORS_TOTAL,
    PROVIDER_REQUEST_DURATION_SECONDS,
    PROVIDER_REQUESTS_TOTAL,
)
from app.rag.config import EmbeddingConfig


class EmbeddingError(RuntimeError):
    """Raised when an embedding request fails after retries."""


class EmbeddingClient:
    """Async client for an OpenAI-compatible embedding endpoint.

    Example request:

        POST /v1/embeddings
        {
            "model": "text-embedding-3-small",
            "input": ["hello world"]
        }

    Example response:

        {
            "object": "list",
            "data": [
                {"object": "embedding", "index": 0, "embedding": [0.1, ...]}
            ]
        }
    """

    def __init__(
        self,
        *,
        config: EmbeddingConfig,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._config = config
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff_seconds
        self._timeout = timeout_seconds

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        base_url = config.base_url or ""
        self._embed_url = base_url.rstrip("/") + "/embeddings"

        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
        )

        logger.info(
            "Embedding client initialized",
            extra={
                "provider": config.provider,
                "model": config.model,
                "dimensions": config.dimensions,
                "url": self._embed_url,
            },
        )

    async def embed(
        self,
        text: str,
    ) -> list[float]:
        """Embed a single text and return its vector."""

        vectors = await self.embed_batch([text])
        return vectors[0]

    async def embed_batch(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """Embed multiple texts in a single request."""

        if not texts:
            return []

        payload: dict[str, Any] = {
            "model": self._config.model,
            "input": texts,
        }

        last_error: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            start = time.perf_counter()
            try:
                response = await self._client.post(
                    self._embed_url,
                    json=payload,
                )

                duration = time.perf_counter() - start

                if response.status_code >= 400:
                    PROVIDER_REQUESTS_TOTAL.labels(
                        provider=self._config.provider,
                        model=self._config.model,
                        status="error",
                    ).inc()
                    PROVIDER_ERRORS_TOTAL.labels(
                        provider=self._config.provider,
                        model=self._config.model,
                        error_type=f"http_{response.status_code}",
                    ).inc()

                    raise EmbeddingError(
                        f"Embedding request failed with HTTP "
                        f"{response.status_code}: {response.text}"
                    )

                data = response.json()

                items = data.get("data")
                if not isinstance(items, list) or len(items) != len(texts):
                    raise EmbeddingError(
                        "Embedding response has unexpected structure"
                    )

                vectors: list[list[float]] = []
                for item in items:
                    embedding = item.get("embedding")
                    if not isinstance(embedding, list):
                        raise EmbeddingError(
                            "Embedding item missing 'embedding' vector"
                        )
                    vectors.append([float(v) for v in embedding])

                PROVIDER_REQUESTS_TOTAL.labels(
                    provider=self._config.provider,
                    model=self._config.model,
                    status="success",
                ).inc()
                PROVIDER_REQUEST_DURATION_SECONDS.labels(
                    provider=self._config.provider,
                    model=self._config.model,
                ).observe(duration)

                logger.debug(
                    "Embedding batch completed",
                    extra={
                        "provider": self._config.provider,
                        "model": self._config.model,
                        "count": len(texts),
                        "duration_ms": round(duration * 1000, 2),
                    },
                )

                return vectors

            except (httpx.RequestError, EmbeddingError) as exc:
                last_error = exc
                duration = time.perf_counter() - start

                PROVIDER_ERRORS_TOTAL.labels(
                    provider=self._config.provider,
                    model=self._config.model,
                    error_type=type(exc).__name__,
                ).inc()

                logger.warning(
                    "Embedding attempt failed",
                    extra={
                        "provider": self._config.provider,
                        "model": self._config.model,
                        "attempt": attempt,
                        "max_retries": self._max_retries,
                        "error": str(exc),
                    },
                )

                if attempt < self._max_retries:
                    await asyncio.sleep(
                        self._retry_backoff * (2 ** (attempt - 1))
                    )

        PROVIDER_REQUESTS_TOTAL.labels(
            provider=self._config.provider,
            model=self._config.model,
            status="error",
        ).inc()

        raise EmbeddingError(
            f"Embedding failed after {self._max_retries} attempts: "
            f"{last_error}"
        ) from last_error

    async def health(self) -> bool:
        """Check whether the embedding endpoint is reachable."""

        try:
            await self.embed("health check")
            return True
        except Exception:
            logger.warning(
                "Embedding health check failed",
                extra={
                    "provider": self._config.provider,
                    "model": self._config.model,
                },
            )
            return False

    async def close(self) -> None:
        """Release the HTTP client."""

        await self._client.aclose()
