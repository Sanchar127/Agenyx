from datetime import datetime, timezone

from app.reliability.state import (
    ProviderHealthState,
    ProviderStatus,
)


class ReliabilityManager:
    """
    Tracks runtime reliability state for inference providers.
    """

    def __init__(
        self,
        *,
        degraded_failure_threshold: int = 1,
        unhealthy_failure_threshold: int = 3,
    ) -> None:
        if degraded_failure_threshold < 1:
            raise ValueError(
                "degraded_failure_threshold must be >= 1"
            )

        if unhealthy_failure_threshold < degraded_failure_threshold:
            raise ValueError(
                "unhealthy_failure_threshold must be >= "
                "degraded_failure_threshold"
            )

        self.degraded_failure_threshold = (
            degraded_failure_threshold
        )

        self.unhealthy_failure_threshold = (
            unhealthy_failure_threshold
        )

        self._states: dict[str, ProviderHealthState] = {}

    def register(self, provider_name: str) -> None:
        """
        Register a provider for reliability tracking.
        """

        if provider_name in self._states:
            raise ValueError(
                f"Provider already registered: {provider_name}"
            )

        self._states[provider_name] = ProviderHealthState(
            provider_name=provider_name,
        )

    def get(self, provider_name: str) -> ProviderHealthState:
        """
        Return current provider health state.
        """

        try:
            return self._states[provider_name]

        except KeyError as exc:
            raise KeyError(
                f"Provider is not registered: {provider_name}"
            ) from exc

    def record_success(self, provider_name: str) -> None:
        """
        Record a successful provider request.
        """

        state = self.get(provider_name)

        now = datetime.now(timezone.utc)

        state.total_successes += 1
        state.consecutive_failures = 0
        state.last_success_at = now

        state.status = ProviderStatus.HEALTHY

    def record_failure(self, provider_name: str) -> None:
        """
        Record a failed provider request.
        """

        state = self.get(provider_name)

        now = datetime.now(timezone.utc)

        state.total_failures += 1
        state.consecutive_failures += 1
        state.last_failure_at = now

        if (
            state.consecutive_failures
            >= self.unhealthy_failure_threshold
        ):
            state.status = ProviderStatus.UNHEALTHY

        elif (
            state.consecutive_failures
            >= self.degraded_failure_threshold
        ):
            state.status = ProviderStatus.DEGRADED

    def is_available(self, provider_name: str) -> bool:
        """
        Determine whether a provider can currently receive traffic.
        """

        state = self.get(provider_name)

        return state.status != ProviderStatus.UNHEALTHY

    def list_states(self) -> list[ProviderHealthState]:
        """
        Return all provider health states.
        """

        return list(self._states.values())
