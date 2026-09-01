from app.logger import logger

from .base import InferenceProvider


class ProviderRegistry:
    """Registry of available inference providers."""

    def __init__(self) -> None:
        self._providers: dict[str, InferenceProvider] = {}

        logger.debug(
            "Provider registry initialized",
        )

    def register(
        self,
        provider: InferenceProvider,
    ) -> None:
        """
        Register an inference provider.

        Provider names must be unique.
        """

        if provider.name in self._providers:
            logger.error(
                "Provider registration rejected: provider already exists",
                extra={
                    "provider": provider.name,
                },
            )

            raise ValueError(
                f"Provider already registered: {provider.name}"
            )

        self._providers[provider.name] = provider

        logger.info(
            "Inference provider registered",
            extra={
                "provider": provider.name,
                "provider_count": len(self._providers),
            },
        )

    def get(
        self,
        name: str,
    ) -> InferenceProvider:
        """
        Retrieve a registered provider by name.
        """

        try:
            provider = self._providers[name]

        except KeyError as exc:
            available = ", ".join(
                sorted(self._providers)
            )

            logger.warning(
                "Provider lookup failed",
                extra={
                    "provider": name,
                    "available_providers": (
                        available or "none"
                    ),
                },
            )

            raise KeyError(
                f"Unknown provider '{name}'. "
                f"Available providers: "
                f"{available or 'none'}"
            ) from exc

        logger.debug(
            "Provider resolved",
            extra={
                "provider": name,
            },
        )

        return provider

    def list(self) -> list[str]:
        """
        Return registered provider names.
        """

        providers = sorted(self._providers)

        logger.debug(
            "Listed inference providers",
            extra={
                "provider_count": len(providers),
                "providers": providers,
            },
        )

        return providers

    async def health(self) -> dict[str, bool]:
        """
        Check health of every registered provider.
        """

        logger.info(
            "Checking inference provider health",
            extra={
                "provider_count": len(self._providers),
            },
        )

        results: dict[str, bool] = {}

        for name, provider in self._providers.items():
            try:
                results[name] = await provider.health()

            except Exception:
                logger.error(
                    "Provider health check raised an exception",
                    extra={
                        "provider": name,
                    },
                    exc_info=True,
                )

                results[name] = False

        healthy_count = sum(
            1
            for healthy in results.values()
            if healthy
        )

        logger.info(
            "Inference provider health check completed",
            extra={
                "provider_count": len(results),
                "healthy_count": healthy_count,
                "unhealthy_count": (
                    len(results) - healthy_count
                ),
            },
        )

        return results

    async def close(self) -> None:
        """
        Close all registered providers.
        """

        logger.info(
            "Closing inference providers",
            extra={
                "provider_count": len(self._providers),
            },
        )

        for name, provider in self._providers.items():
            try:
                await provider.close()

            except Exception:
                logger.error(
                    "Failed to close inference provider",
                    extra={
                        "provider": name,
                    },
                    exc_info=True,
                )

        logger.info(
            "All inference providers closed",
        )
