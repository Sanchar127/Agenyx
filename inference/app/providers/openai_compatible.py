from typing import Any

from app.backend import OpenAICompatibleBackend

from .base import InferenceProvider


class OpenAICompatibleProvider(InferenceProvider):
    """
    Provider backed by an OpenAI-compatible HTTP API.

    A single provider can serve multiple models.

    Example:

        ollama-local
            ├── qwen2.5:7b
            ├── llama3.2:3b
            └── another-model

    Model selection is handled by the ModelRegistry and the
    request payload, not by this provider.
    """

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
        provider_name = provider_name.strip()

        if not provider_name:
            raise ValueError(
                "provider_name must not be empty"
            )

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
        """Return the unique provider name."""

        return self._name

    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a chat completion.

        The requested model is supplied in the payload.
        This allows one provider to serve multiple models.
        """

        model = payload.get("model")

        if not isinstance(model, str) or not model.strip():
            raise ValueError(
                "Chat completion payload must contain "
                "a non-empty 'model' field"
            )

        return await self.backend.chat_completion(
            payload
        )

    async def health(self) -> bool:
        """Check whether the provider backend is reachable."""

        return await self.backend.health()

    async def close(self) -> None:
        """Release provider resources."""

        await self.backend.close()
