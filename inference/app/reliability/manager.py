from datetime import datetime, timedelta, timezone
from threading import Lock

from app.logger import logger
from app.metrics import (
    PROVIDER_CIRCUIT_STATE,
    PROVIDER_CONSECUTIVE_FAILURES,
    PROVIDER_HEALTH_STATE,
    PROVIDER_TOTAL_FAILURES,
    PROVIDER_TOTAL_SUCCESSES,
)
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

    Prometheus metrics:

        provider_circuit_state
            0 = CLOSED
            1 = OPEN
            2 = HALF_OPEN

        provider_health_state
            0 = UNHEALTHY
            1 = DEGRADED
            2 = HEALTHY

        provider_consecutive_failures
            Current consecutive failure count.

        provider_total_failures
            Total recorded provider failures.

        provider_total_successes
            Total recorded provider successes.
    """

    # Numeric representation used by Prometheus gauges.
    _CIRCUIT_STATE_VALUES = {
        CircuitState.CLOSED: 0,
        CircuitState.OPEN: 1,
        CircuitState.HALF_OPEN: 2,
    }

    _HEALTH_STATE_VALUES = {
        ProviderStatus.UNHEALTHY: 0,
        ProviderStatus.DEGRADED: 1,
        ProviderStatus.HEALTHY: 2,
    }

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

        # Tracks providers currently executing their single
        # HALF_OPEN recovery probe.
        self._half_open_probe: set[str] = set()

        self._lock = Lock()

        logger.info(
            "Reliability manager initialized",
            extra={
                "degraded_failure_threshold": (
                    degraded_failure_threshold
                ),
                "unhealthy_failure_threshold": (
                    unhealthy_failure_threshold
                ),
                "recovery_timeout_seconds": (
                    recovery_timeout_seconds
                ),
            },
        )

    # =====================================================
    # METRICS
    # =====================================================

    def _update_metrics(
        self,
        state: ProviderHealthState,
    ) -> None:
        """
        Update Prometheus gauges for a provider.

        This method is centralized so every reliability
        state transition keeps metrics synchronized with
        the in-memory state.
        """

        provider = state.provider_name

        PROVIDER_CIRCUIT_STATE.labels(
            provider=provider,
        ).set(
            self._CIRCUIT_STATE_VALUES[
                state.circuit_state
            ]
        )

        PROVIDER_HEALTH_STATE.labels(
            provider=provider,
        ).set(
            self._HEALTH_STATE_VALUES[
                state.status
            ]
        )

        PROVIDER_CONSECUTIVE_FAILURES.labels(
            provider=provider,
        ).set(
            state.consecutive_failures
        )

        PROVIDER_TOTAL_FAILURES.labels(
            provider=provider,
        ).set(
            state.total_failures
        )

        PROVIDER_TOTAL_SUCCESSES.labels(
            provider=provider,
        ).set(
            state.total_successes
        )

    # =====================================================
    # REGISTRATION
    # =====================================================

    def register(
        self,
        provider_name: str,
    ) -> None:
        """
        Register a provider for reliability tracking.

        The provider starts in:

            status = HEALTHY
            circuit = CLOSED
        """

        if not provider_name or not provider_name.strip():
            raise ValueError(
                "provider_name must be a non-empty string"
            )

        with self._lock:
            if provider_name in self._states:
                logger.error(
                    "Provider already registered",
                    extra={
                        "provider": provider_name,
                    },
                )

                raise ValueError(
                    f"Provider already registered: {provider_name}"
                )

            state = ProviderHealthState(
                provider_name=provider_name,
            )

            self._states[provider_name] = state

            self._update_metrics(state)

        logger.info(
            "Provider registered for reliability tracking",
            extra={
                "provider": provider_name,
                "status": ProviderStatus.HEALTHY.value,
                "circuit_state": CircuitState.CLOSED.value,
            },
        )

    # =====================================================
    # STATE
    # =====================================================

    def get(
        self,
        provider_name: str,
    ) -> ProviderHealthState:
        """
        Return a snapshot of the current provider state.
        """

        with self._lock:
            state = self._get_state(provider_name)

            return self._copy_state(state)

    # =====================================================
    # CIRCUIT BREAKER
    # =====================================================

    def allow_request(
        self,
        provider_name: str,
    ) -> bool:
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

            # -------------------------------------------------
            # CLOSED
            # -------------------------------------------------

            if state.circuit_state == CircuitState.CLOSED:
                return True

            # -------------------------------------------------
            # OPEN
            # -------------------------------------------------

            if state.circuit_state == CircuitState.OPEN:
                now = datetime.now(timezone.utc)

                if (
                    state.circuit_opened_at is not None
                    and now - state.circuit_opened_at
                    >= self.recovery_timeout
                ):
                    state.circuit_state = (
                        CircuitState.HALF_OPEN
                    )

                    state.circuit_half_opened_at = now

                    self._update_metrics(state)

                    if provider_name in self._half_open_probe:
                        logger.debug(
                            "Provider recovery probe already in progress",
                            extra={
                                "provider": provider_name,
                                "circuit_state": (
                                    CircuitState.HALF_OPEN.value
                                ),
                            },
                        )

                        return False

                    self._half_open_probe.add(
                        provider_name
                    )

                    logger.info(
                        "Provider circuit entering half-open state",
                        extra={
                            "provider": provider_name,
                            "circuit_state": (
                                CircuitState.HALF_OPEN.value
                            ),
                        },
                    )

                    return True

                logger.debug(
                    "Request rejected because provider circuit is open",
                    extra={
                        "provider": provider_name,
                        "circuit_state": (
                            CircuitState.OPEN.value
                        ),
                    },
                )

                return False

            # -------------------------------------------------
            # HALF OPEN
            # -------------------------------------------------

            if state.circuit_state == CircuitState.HALF_OPEN:
                if provider_name in self._half_open_probe:
                    logger.debug(
                        "Provider half-open probe already in progress",
                        extra={
                            "provider": provider_name,
                            "circuit_state": (
                                CircuitState.HALF_OPEN.value
                            ),
                        },
                    )

                    return False

                self._half_open_probe.add(
                    provider_name
                )

                logger.info(
                    "Provider recovery probe allowed",
                    extra={
                        "provider": provider_name,
                        "circuit_state": (
                            CircuitState.HALF_OPEN.value
                        ),
                    },
                )

                return True

            return False

    # =====================================================
    # SUCCESS
    # =====================================================

    def record_success(
        self,
        provider_name: str,
    ) -> None:
        """
        Record a successful request.

        A successful HALF_OPEN probe closes the circuit
        and marks the provider healthy.
        """

        with self._lock:
            state = self._get_state(provider_name)

            previous_status = state.status
            previous_circuit_state = state.circuit_state

            now = datetime.now(timezone.utc)

            state.total_successes += 1
            state.consecutive_failures = 0
            state.last_success_at = now

            state.status = ProviderStatus.HEALTHY
            state.circuit_state = CircuitState.CLOSED

            state.circuit_opened_at = None
            state.circuit_half_opened_at = None

            self._half_open_probe.discard(
                provider_name
            )

            self._update_metrics(state)

            total_successes = state.total_successes

        # Log recovery/state transition rather than every
        # successful inference request.
        if (
            previous_status != ProviderStatus.HEALTHY
            or previous_circuit_state != CircuitState.CLOSED
        ):
            logger.info(
                "Provider recovered",
                extra={
                    "provider": provider_name,
                    "previous_status": (
                        previous_status.value
                    ),
                    "status": (
                        ProviderStatus.HEALTHY.value
                    ),
                    "previous_circuit_state": (
                        previous_circuit_state.value
                    ),
                    "circuit_state": (
                        CircuitState.CLOSED.value
                    ),
                    "total_successes": total_successes,
                },
            )

    # =====================================================
    # FAILURE
    # =====================================================

    def record_failure(
        self,
        provider_name: str,
    ) -> None:
        """
        Record a failed request.

        Once the failure threshold is reached, the circuit
        opens.

        A failed HALF_OPEN probe immediately reopens the circuit.
        """

        with self._lock:
            state = self._get_state(provider_name)

            now = datetime.now(timezone.utc)

            previous_status = state.status
            previous_circuit_state = state.circuit_state

            state.total_failures += 1
            state.consecutive_failures += 1
            state.last_failure_at = now

            self._half_open_probe.discard(
                provider_name
            )

            # -------------------------------------------------
            # Failed HALF_OPEN probe
            # -------------------------------------------------

            if state.circuit_state == CircuitState.HALF_OPEN:
                state.circuit_state = CircuitState.OPEN

                state.circuit_opened_at = now
                state.circuit_half_opened_at = None

                state.status = ProviderStatus.UNHEALTHY

                self._update_metrics(state)

                logger.warning(
                    "Provider recovery probe failed; circuit reopened",
                    extra={
                        "provider": provider_name,
                        "previous_status": (
                            previous_status.value
                        ),
                        "status": (
                            ProviderStatus.UNHEALTHY.value
                        ),
                        "previous_circuit_state": (
                            previous_circuit_state.value
                        ),
                        "circuit_state": (
                            CircuitState.OPEN.value
                        ),
                        "consecutive_failures": (
                            state.consecutive_failures
                        ),
                        "total_failures": (
                            state.total_failures
                        ),
                    },
                )

                return

            # -------------------------------------------------
            # UNHEALTHY
            # -------------------------------------------------

            if (
                state.consecutive_failures
                >= self.unhealthy_failure_threshold
            ):
                state.status = ProviderStatus.UNHEALTHY
                state.circuit_state = CircuitState.OPEN
                state.circuit_opened_at = now
                state.circuit_half_opened_at = None

                self._update_metrics(state)

                logger.warning(
                    "Provider marked unhealthy; circuit opened",
                    extra={
                        "provider": provider_name,
                        "status": (
                            ProviderStatus.UNHEALTHY.value
                        ),
                        "circuit_state": (
                            CircuitState.OPEN.value
                        ),
                        "consecutive_failures": (
                            state.consecutive_failures
                        ),
                        "total_failures": (
                            state.total_failures
                        ),
                    },
                )

            # -------------------------------------------------
            # DEGRADED
            # -------------------------------------------------

            elif (
                state.consecutive_failures
                >= self.degraded_failure_threshold
            ):
                state.status = ProviderStatus.DEGRADED

                self._update_metrics(state)

                logger.warning(
                    "Provider marked degraded",
                    extra={
                        "provider": provider_name,
                        "status": (
                            ProviderStatus.DEGRADED.value
                        ),
                        "circuit_state": (
                            state.circuit_state.value
                        ),
                        "consecutive_failures": (
                            state.consecutive_failures
                        ),
                        "total_failures": (
                            state.total_failures
                        ),
                    },
                )

            else:
                # Failure happened but did not cross the
                # degraded threshold.
                self._update_metrics(state)

    # =====================================================
    # AVAILABILITY
    # =====================================================

    def is_available(
        self,
        provider_name: str,
    ) -> bool:
        """
        Backwards-compatible availability check.

        Returns True only when a request is currently allowed.
        """

        return self.allow_request(provider_name)

    # =====================================================
    # SNAPSHOTS
    # =====================================================

    def list_states(
        self,
    ) -> list[ProviderHealthState]:
        """
        Return snapshots of all provider states.
        """

        with self._lock:
            return [
                self._copy_state(state)
                for state in self._states.values()
            ]

    # =====================================================
    # INTERNAL
    # =====================================================

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

    @staticmethod
    def _copy_state(
        state: ProviderHealthState,
    ) -> ProviderHealthState:
        """
        Return a detached copy of provider state.

        This prevents callers from mutating the manager's
        internal state without acquiring the lock.
        """

        return ProviderHealthState(
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
