"""Anthropic provider adapter for the evaluation platform.

Anthropic uses a different API shape than OpenAI-compatible backends.
This adapter translates between the evaluation platform's normalized
interface and Anthropic's ``/v1/messages`` endpoint.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.eval.providers.base import EvaluationProvider


class AnthropicProvider(EvaluationProvider):
    """Anthropic provider adapter.

    Configuration:
        - endpoint_url: https://api.anthropic.com/v1
        - auth_ref: Anthropic API key (sent as x-api-key header)
    """

    def __init__(
        self,
        *,
        provider_id: str = "anthropic",
        endpoint_url: str = "https://api.anthropic.com/v1",
        api_key: str = "",
        timeout: float = 120.0,
    ) -> None:
        self._provider_id = provider_id
        self._endpoint_url = endpoint_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

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
        return "anthropic"

    @property
    def endpoint_url(self) -> str:
        return self._endpoint_url

    def _anthropic_messages(
        self,
        messages: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]]]:
        """Convert OpenAI-style messages to Anthropic format.

        Returns (system_prompt, messages) where system_prompt is the
        content of any system message and messages excludes system roles.
        """
        system_prompt = ""
        anthropic_messages: list[dict[str, str]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_prompt = content
            else:
                anthropic_messages.append({"role": role, "content": content})
        return system_prompt, anthropic_messages

    async def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        system_prompt, anthropic_messages = self._anthropic_messages(messages)

        payload: dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)

        response = await self._client.post("/v1/messages", json=payload)
        response.raise_for_status()
        data = response.json()

        # Normalize Anthropic response to OpenAI-compatible shape
        content_blocks = data.get("content", [])
        text_content = ""
        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")

        return {
            "id": data.get("id", ""),
            "model": data.get("model", model),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text_content},
                    "finish_reason": data.get("stop_reason", "stop"),
                }
            ],
            "usage": data.get("usage", {}),
        }

    async def embedding(
        self,
        *,
        model: str,
        input: list[str],
    ) -> dict[str, Any]:
        # Anthropic does not expose a public embeddings endpoint as of
        # this implementation. Raise a clear error.
        raise NotImplementedError(
            "Anthropic provider does not support embeddings via this adapter"
        )

    async def health(self) -> bool:
        try:
            # Anthropic does not have a public /v1/models endpoint that
            # works without a specific model. Use a lightweight messages
            # call to verify connectivity.
            response = await self._client.post(
                "/v1/messages",
                json={
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
            return response.status_code in (200, 400)  # 400 means reachable
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
