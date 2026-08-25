from abc import ABC, abstractmethod
from typing import Any


class InferenceProvider(ABC):
    """Provider abstraction used by the inference gateway."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name."""
        raise NotImplementedError

    @abstractmethod
    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a chat completion."""
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        """Check provider health."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release provider resources."""
        raise NotImplementedError
