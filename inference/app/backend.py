import asyncio
from abc import ABC, abstractmethod
from typing import Any

import httpx


class InferenceBackend(ABC):

    @abstractmethod
    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


class OpenAICompatibleBackend(InferenceBackend):

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

    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:

        url = f"{self.base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.post(
                    url,
                    json=payload,
                    headers=headers,
                )

                # Never retry client errors.
                if 400 <= response.status_code < 500:
                    response.raise_for_status()

                # Retry transient backend/server failures.
                if response.status_code >= 500:
                    if attempt >= self.max_retries:
                        response.raise_for_status()

                    await self._backoff(attempt)
                    continue

                response.raise_for_status()

                try:
                    data = response.json()
                except ValueError as exc:
                    raise RuntimeError(
                        "Inference backend returned invalid JSON"
                    ) from exc

                if not isinstance(data, dict):
                    raise RuntimeError(
                        "Inference backend returned a non-object JSON response"
                    )

                return data

            except httpx.TimeoutException:
                if attempt >= self.max_retries:
                    raise

                await self._backoff(attempt)

            except httpx.ConnectError:
                if attempt >= self.max_retries:
                    raise

                await self._backoff(attempt)

            except httpx.NetworkError:
                if attempt >= self.max_retries:
                    raise

                await self._backoff(attempt)

        raise RuntimeError("Inference request failed")

    async def _backoff(self, attempt: int) -> None:
        delay = 0.5 * (2**attempt)
        await asyncio.sleep(delay)

    async def health(self) -> bool:

        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                },
            )

            return response.status_code < 500

        except httpx.HTTPError:
            return False

    async def close(self) -> None:

        if not self.client.is_closed:
            await self.client.aclose()
