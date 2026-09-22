from dataclasses import dataclass
from typing import Any

from app.providers.registry import ProviderRegistry
from app.reliability.manager import ReliabilityManager


@dataclass
class FailoverAttempt:
    """Result metadata for a single provider attempt."""

    provider: str
    success: bool
    error: str | None = None


@dataclass
class FailoverResult:
    """Result returned by the failover manager."""

    response: dict[str, Any]
    provider: str
    attempts: list[FailoverAttempt]


class FailoverManager:
    """
    Execute inference requests using model-specific provider routes.

    Each model has an ordered list of providers. Providers are
    attempted in that order until one succeeds or the configured
    attempt limit is reached.

    Example:

        qwen2.5:7b
            ↓
        ollama-local
            ↓ failure
        vllm-local
            ↓ success
        return response

    Providers whose circuit is OPEN are skipped.
    """

    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        reliability: ReliabilityManager,
        model_routes: dict[str, tuple[str, ...]],
        max_attempts: int = 3,
    ) -> None:

        if not model_routes:
            raise ValueError(
                "model_routes must contain at least one model"
            )

        if max_attempts < 1:
            raise ValueError(
                "max_attempts must be >= 1"
            )

        self.registry = registry
        self.reliability = reliability
        self.model_routes = model_routes
        self.max_attempts = max_attempts

        self._validate_routes()

    def _validate_routes(self) -> None:
        """Validate that every configured provider exists."""

        registered_providers = set(
            self.registry.list()
        )

        for model_id, providers in self.model_routes.items():

            if not model_id.strip():
                raise ValueError(
                    "model_routes contains an empty model ID"
                )

            if not providers:
                raise ValueError(
                    f"Model '{model_id}' has no providers"
                )

            for provider_name in providers:
                if provider_name not in registered_providers:
                    raise ValueError(
                        f"Model '{model_id}' references "
                        f"unregistered provider "
                        f"'{provider_name}'"
                    )

    def _providers_for_model(
        self,
        model_id: str,
    ) -> tuple[str, ...]:
        """Return the ordered provider route for a model."""

        try:
            return self.model_routes[model_id]

        except KeyError as exc:
            raise KeyError(
                f"No failover route configured for model "
                f"'{model_id}'"
            ) from exc

    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> FailoverResult:
        """
        Execute a model-aware inference request.

        The payload must contain a valid ``model`` field.
        """

        model_id = payload.get("model")

        if not isinstance(model_id, str) or not model_id:
            raise ValueError(
                "Inference payload must contain a "
                "non-empty string 'model'"
            )

        providers = self._providers_for_model(
            model_id
        )

        attempts: list[FailoverAttempt] = []
        attempted_count = 0
        last_error: Exception | None = None

        for provider_name in providers:

            if attempted_count >= self.max_attempts:
                break

            provider = self.registry.get(
                provider_name
            )

            if not self.reliability.allow_request(
                provider.name
            ):
                attempts.append(
                    FailoverAttempt(
                        provider=provider.name,
                        success=False,
                        error="Provider circuit is open",
                    )
                )

                continue

            attempted_count += 1

            try:
                response = await provider.chat_completion(
                    payload
                )

            except Exception as exc:
                self.reliability.record_failure(
                    provider.name
                )

                last_error = exc

                attempts.append(
                    FailoverAttempt(
                        provider=provider.name,
                        success=False,
                        error=str(exc),
                    )
                )

                continue

            self.reliability.record_success(
                provider.name
            )

            attempts.append(
                FailoverAttempt(
                    provider=provider.name,
                    success=True,
                )
            )

            return FailoverResult(
                response=response,
                provider=provider.name,
                attempts=attempts,
            )

        if last_error is not None:
            raise RuntimeError(
                f"All failover providers failed for "
                f"model '{model_id}'"
            ) from last_error

        raise RuntimeError(
            f"No failover providers are currently "
            f"available for model '{model_id}'"
        )
