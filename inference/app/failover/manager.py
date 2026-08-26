from dataclasses import dataclass
from typing import Any

from app.providers.base import InferenceProvider
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
    Executes inference requests across multiple providers.

    Provider order is deterministic.

    Example:

        provider A
            ↓ failure
        provider B
            ↓ failure
        provider C
            ↓ success
        return response

    Providers whose circuit is OPEN are skipped immediately.
    """

    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        reliability: ReliabilityManager,
        provider_order: list[str],
        max_attempts: int = 3,
    ) -> None:

        if not provider_order:
            raise ValueError(
                "provider_order must contain at least one provider"
            )

        if max_attempts < 1:
            raise ValueError(
                "max_attempts must be >= 1"
            )

        self.registry = registry
        self.reliability = reliability
        self.provider_order = provider_order
        self.max_attempts = max_attempts

    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> FailoverResult:
        """
        Execute a request with provider failover.

        Providers are attempted in configured order.

        Providers whose circuit breaker does not allow traffic
        are skipped.

        If every eligible provider fails, the final provider
        exception is raised.
        """

        attempts: list[FailoverAttempt] = []
        attempted_count = 0
        last_error: Exception | None = None

        for provider_name in self.provider_order:

            if attempted_count >= self.max_attempts:
                break

            # The provider must exist.
            provider = self.registry.get(provider_name)

            # Circuit breaker decides whether this provider
            # can receive traffic.
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
                "All inference providers failed"
            ) from last_error

        raise RuntimeError(
            "No inference providers are currently available"
        )
