"""Abstract base class for evaluation provider adapters.

A provider adapter wraps an inference backend (Ollama, vLLM, OpenAI,
Anthropic, etc.) and provides a unified interface for the evaluation
pipeline. The same evaluation logic runs against any registered provider
without code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EvaluationProvider(ABC):
    """Abstract interface for an evaluation inference provider.

    Implementations must handle authentication, request formatting,
    response parsing, and error handling for a specific inference
    backend.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Return the unique provider identifier."""

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Return the provider type (ollama, vllm, openai, anthropic, ...)."""

    @property
    @abstractmethod
    def endpoint_url(self) -> str:
        """Return the provider endpoint URL."""

    @abstractmethod
    async def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute a chat completion.

        Returns a normalized response dict:

            {
                "id": "...",
                "model": "...",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "..."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": ..., "completion_tokens": ...}
            }
        """
        raise NotImplementedError

    @abstractmethod
    async def embedding(
        self,
        *,
        model: str,
        input: list[str],
    ) -> dict[str, Any]:
        """Embed one or more texts.

        Returns a normalized response dict:

            {
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [...]}
                ]
            }
        """
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        """Check whether the provider is reachable."""

    @abstractmethod
    async def close(self) -> None:
        """Release provider resources."""
