"""OpenAI-compatible provider adapter for the evaluation platform.

Supports any OpenAI-compatible endpoint (e.g., OpenAI API, local
OpenAI-compatible servers) via the standard ``/v1/chat/completions``
and ``/v1/embeddings`` endpoints.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.eval.providers.base import EvaluationProvider


class OpenAICompatibleProvider(EvaluationProvider):
    """OpenAI-compatible provider adapter.

    Configuration:
        - endpoint_url: https://api.openai.com/v1 or local equivalent
        - auth_ref: API key reference (sent as Bearer token)
    """

    def __init__(
        self,
        *,
        provider_id: str = "openai-compatible",
        endpoint_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        timeout: float = 120.0,
    ) -> None:
        self._provider_id = provider_id
        self._endpoint_url = endpoint_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            base_url=self._endpoint_url,
            timeout=httpx.Timeout(timeout),
            headers=headers,
        )

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def provider_type(self) -> str:
        return "openai-compatible"

    @property
    def endpoint_url(self) -> str:
        return self._endpoint_url

    async def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)

        response = await self._client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()

    async def embedding(
        self,
        *,
        model: str,
        input: list[str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "input": input,
        }
        response = await self._client.post("/v1/embeddings", json=payload)
        response.raise_for_status()
        return response.json()

    async def health(self) -> bool:
        try:
            response = await self._client.get("/v1/models")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
