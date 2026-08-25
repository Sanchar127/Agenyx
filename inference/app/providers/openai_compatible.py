from typing import Any

from app.backend import OpenAICompatibleBackend

from .base import InferenceProvider


class OpenAICompatibleProvider(InferenceProvider):
    """Provider backed by an OpenAI-compatible HTTP API."""

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
        timeout: float,
        max_connections: int,
        max_keepalive_connections: int,
        max_retries: int,
    ) -> None:
        self._name = provider_name

        self.backend = OpenAICompatibleBackend(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            max_retries=max_retries,
        )

    @property
    def name(self) -> str:
        return self._name

    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.backend.chat_completion(payload)

    async def health(self) -> bool:
        return await self.backend.health()

    async def close(self) -> None:
        await self.backend.close()
