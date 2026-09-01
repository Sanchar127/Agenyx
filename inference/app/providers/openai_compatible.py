from typing import Any

from app.backend import OpenAICompatibleBackend
from app.logger import logger

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
        provider_name=provider_name,
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        max_connections=max_connections,
        max_keepalive_connections=max_keepalive_connections,
        max_retries=max_retries,
        )

        logger.info(
            "Inference provider initialized",
            extra={
                "provider": self._name,
                "backend": "openai-compatible",
                "base_url": base_url,
            },
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
            logger.warning(
                "Provider received invalid model",
                extra={
                    "provider": self._name,
                },
            )

            raise ValueError(
                "Chat completion payload must contain "
                "a non-empty 'model' field"
            )

        logger.info(
            "Provider inference request started",
            extra={
                "provider": self._name,
                "model": model,
            },
        )

        try:
            response = await self.backend.chat_completion(
                payload
            )

        except Exception:
            logger.error(
                "Provider inference request failed",
                extra={
                    "provider": self._name,
                    "model": model,
                },
                exc_info=True,
            )

            raise

        logger.info(
            "Provider inference request completed",
            extra={
                "provider": self._name,
                "model": model,
            },
        )

        return response

    async def health(self) -> bool:
        """Check whether the provider backend is reachable."""

        healthy = await self.backend.health()

        if healthy:
            logger.debug(
                "Provider health check passed",
                extra={
                    "provider": self._name,
                },
            )
        else:
            logger.warning(
                "Provider health check failed",
                extra={
                    "provider": self._name,
                },
            )

        return healthy

    async def close(self) -> None:
        """Release provider resources."""

        logger.info(
            "Closing inference provider",
            extra={
                "provider": self._name,
            },
        )

        await self.backend.close()

        logger.info(
            "Inference provider closed",
            extra={
                "provider": self._name,
            },
        )
