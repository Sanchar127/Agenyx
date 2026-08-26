from datetime import datetime, timedelta, timezone
from threading import Lock

from app.reliability.state import (
    CircuitState,
    ProviderHealthState,
    ProviderStatus,
)


class ReliabilityManager:
    """
    Tracks provider reliability and manages circuit-breaker state.

    Circuit states:

        CLOSED
            Normal traffic.

        OPEN
            Provider is considered unavailable and requests
            fail fast.

        HALF_OPEN
            After the cooldown period, allow one probe request
            to determine whether the provider recovered.
    """

    def __init__(
        self,
        *,
        degraded_failure_threshold: int = 1,
        unhealthy_failure_threshold: int = 3,
        recovery_timeout_seconds: float = 10.0,
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

        if recovery_timeout_seconds <= 0:
            raise ValueError(
                "recovery_timeout_seconds must be > 0"
            )

        self.degraded_failure_threshold = (
            degraded_failure_threshold
        )

        self.unhealthy_failure_threshold = (
            unhealthy_failure_threshold
        )

        self.recovery_timeout = timedelta(
            seconds=recovery_timeout_seconds
        )

        self._states: dict[str, ProviderHealthState] = {}

        self._half_open_probe: set[str] = set()

        self._lock = Lock()

    def register(self, provider_name: str) -> None:
        """
        Register a provider for reliability tracking.
        """

        with self._lock:
            if provider_name in self._states:
                raise ValueError(
                    f"Provider already registered: {provider_name}"
                )

            self._states[provider_name] = ProviderHealthState(
                provider_name=provider_name,
            )

    def get(self, provider_name: str) -> ProviderHealthState:
        """
        Return the current provider state.
        """

        with self._lock:
            try:
                return self._states[provider_name]

            except KeyError as exc:
                raise KeyError(
                    f"Provider is not registered: {provider_name}"
                ) from exc

    def allow_request(self, provider_name: str) -> bool:
        """
        Determine whether a request may be sent to the provider.

        CLOSED:
            Allow.

        OPEN:
            Reject until recovery timeout expires.

        HALF_OPEN:
            Allow exactly one probe request.
        """

        with self._lock:
            state = self._get_state(provider_name)

            if state.circuit_state == CircuitState.CLOSED:
                return True

            if state.circuit_state == CircuitState.OPEN:
                now = datetime.now(timezone.utc)

                if (
                    state.circuit_opened_at is not None
                    and now - state.circuit_opened_at
                    >= self.recovery_timeout
                ):
                    state.circuit_state = CircuitState.HALF_OPEN
                    state.circuit_half_opened_at = now

                    if provider_name in self._half_open_probe:
                        return False

                    self._half_open_probe.add(provider_name)

                    return True

                return False

            # HALF_OPEN
            if provider_name in self._half_open_probe:
                return False

            self._half_open_probe.add(provider_name)

            return True

    def record_success(self, provider_name: str) -> None:
        """
        Record a successful request.

        A successful HALF_OPEN probe closes the circuit.
        """

        with self._lock:
            state = self._get_state(provider_name)

            now = datetime.now(timezone.utc)

            state.total_successes += 1
            state.consecutive_failures = 0
            state.last_success_at = now

            state.status = ProviderStatus.HEALTHY
            state.circuit_state = CircuitState.CLOSED

            state.circuit_opened_at = None
            state.circuit_half_opened_at = None

            self._half_open_probe.discard(provider_name)

    def record_failure(self, provider_name: str) -> None:
        """
        Record a failed request.

        Once the failure threshold is reached, the circuit opens.
        A failed HALF_OPEN probe immediately reopens the circuit.
        """

        with self._lock:
            state = self._get_state(provider_name)

            now = datetime.now(timezone.utc)

            state.total_failures += 1
            state.consecutive_failures += 1
            state.last_failure_at = now

            self._half_open_probe.discard(provider_name)

            # A failed HALF_OPEN probe goes straight back to OPEN.
            if state.circuit_state == CircuitState.HALF_OPEN:
                state.circuit_state = CircuitState.OPEN
                state.circuit_opened_at = now
                state.status = ProviderStatus.UNHEALTHY

                return

            if (
                state.consecutive_failures
                >= self.unhealthy_failure_threshold
            ):
                state.status = ProviderStatus.UNHEALTHY
                state.circuit_state = CircuitState.OPEN
                state.circuit_opened_at = now

            elif (
                state.consecutive_failures
                >= self.degraded_failure_threshold
            ):
                state.status = ProviderStatus.DEGRADED

    def is_available(self, provider_name: str) -> bool:
        """
        Backwards-compatible availability check.

        Returns True only when a request is currently allowed.
        """

        return self.allow_request(provider_name)

    def list_states(self) -> list[ProviderHealthState]:
        """
        Return snapshots of all provider states.
        """

        with self._lock:
            return [
                ProviderHealthState(
                    provider_name=state.provider_name,
                    status=state.status,
                    circuit_state=state.circuit_state,
                    consecutive_failures=state.consecutive_failures,
                    total_failures=state.total_failures,
                    total_successes=state.total_successes,
                    last_failure_at=state.last_failure_at,
                    last_success_at=state.last_success_at,
                    circuit_opened_at=state.circuit_opened_at,
                    circuit_half_opened_at=state.circuit_half_opened_at,
                )
                for state in self._states.values()
            ]

    def _get_state(
        self,
        provider_name: str,
    ) -> ProviderHealthState:
        """
        Internal state lookup.

        Caller must hold self._lock.
        """

        try:
            return self._states[provider_name]

        except KeyError as exc:
            raise KeyError(
                f"Provider is not registered: {provider_name}"
            ) from exc
