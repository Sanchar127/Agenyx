from typing import Any

from .base import InferenceProvider


class ProviderRegistry:
    """Registry of available inference providers."""

    def __init__(self) -> None:
        self._providers: dict[str, InferenceProvider] = {}

    def register(
        self,
        provider: InferenceProvider,
    ) -> None:
        if provider.name in self._providers:
            raise ValueError(
                f"Provider already registered: {provider.name}"
            )

        self._providers[provider.name] = provider

    def get(
        self,
        name: str,
    ) -> InferenceProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._providers))

            raise KeyError(
                f"Unknown provider '{name}'. "
                f"Available providers: {available or 'none'}"
            ) from exc

    def list(self) -> list[str]:
        return sorted(self._providers)

    async def health(self) -> dict[str, bool]:
        results: dict[str, bool] = {}

        for name, provider in self._providers.items():
            results[name] = await provider.health()

        return results

    async def close(self) -> None:
        for provider in self._providers.values():
            await provider.close()
