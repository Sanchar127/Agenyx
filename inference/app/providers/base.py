from abc import ABC, abstractmethod
from typing import Any


class InferenceProvider(ABC):
    """
    Provider abstraction used by the inference gateway.

    A provider is a backend capable of serving one or more models.

    Model selection is intentionally NOT part of the provider
    interface. Models are resolved by ModelRegistry and passed
    through the request payload.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the unique provider name.
        """
        raise NotImplementedError

    @abstractmethod
    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a non-streaming chat completion.

        The payload contains the requested model.
        """
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        """
        Check whether the provider is healthy.
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """
        Release provider resources.
        """
        raise NotImplementedError
