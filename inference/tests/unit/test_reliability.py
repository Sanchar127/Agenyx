from datetime import datetime, timedelta, timezone

import pytest

from app.reliability.manager import ReliabilityManager
from app.reliability.state import (
    CircuitState,
    ProviderStatus,
)


# =========================================================
# FIXTURE
# =========================================================


@pytest.fixture
def manager() -> ReliabilityManager:
    return ReliabilityManager(
        degraded_failure_threshold=1,
        unhealthy_failure_threshold=3,
        recovery_timeout_seconds=10.0,
    )


@pytest.fixture
def registered_manager(
    manager: ReliabilityManager,
) -> ReliabilityManager:
    manager.register("provider-a")
    return manager


# =========================================================
# CONFIGURATION
# =========================================================


def test_invalid_degraded_threshold():
    with pytest.raises(
        ValueError,
        match="degraded_failure_threshold must be >= 1",
    ):
        ReliabilityManager(
            degraded_failure_threshold=0,
        )


def test_invalid_unhealthy_threshold():
    with pytest.raises(
        ValueError,
        match="unhealthy_failure_threshold must be >= degraded_failure_threshold",
    ):
        ReliabilityManager(
            degraded_failure_threshold=3,
            unhealthy_failure_threshold=2,
        )


def test_invalid_recovery_timeout():
    with pytest.raises(
        ValueError,
        match="recovery_timeout_seconds must be > 0",
    ):
        ReliabilityManager(
            recovery_timeout_seconds=0,
        )


# =========================================================
# REGISTER
# =========================================================


def test_register_provider(
    manager: ReliabilityManager,
):
    manager.register("provider-a")

    state = manager.get("provider-a")

    assert state.provider_name == "provider-a"
    assert state.status == ProviderStatus.HEALTHY
    assert state.circuit_state == CircuitState.CLOSED


def test_register_duplicate_provider(
    manager: ReliabilityManager,
):
    manager.register("provider-a")

    with pytest.raises(
        ValueError,
        match="Provider already registered",
    ):
        manager.register("provider-a")


# =========================================================
# GET
# =========================================================


def test_get_unknown_provider(
    manager: ReliabilityManager,
):
    with pytest.raises(
        KeyError,
        match="Provider is not registered",
    ):
        manager.get("missing-provider")


# =========================================================
# ALLOW REQUEST
# =========================================================


def test_closed_circuit_allows_request(
    registered_manager: ReliabilityManager,
):
    assert (
        registered_manager.allow_request(
            "provider-a"
        )
        is True
    )


def test_unknown_provider_cannot_be_checked(
    manager: ReliabilityManager,
):
    with pytest.raises(
        KeyError,
        match="Provider is not registered",
    ):
        manager.allow_request("provider-a")


# =========================================================
# SUCCESS
# =========================================================


def test_record_success_updates_state(
    registered_manager: ReliabilityManager,
):
    manager = registered_manager

    manager.record_failure("provider-a")
    manager.record_success("provider-a")

    state = manager.get("provider-a")

    assert state.status == ProviderStatus.HEALTHY
    assert state.circuit_state == CircuitState.CLOSED
    assert state.consecutive_failures == 0
    assert state.total_failures == 1
    assert state.total_successes == 1
    assert state.last_success_at is not None


def test_success_closes_half_open_circuit(
    registered_manager: ReliabilityManager,
):
    manager = registered_manager

    # Mutate the manager's real internal state directly.
    # manager.get() returns a detached copy (by design, so
    # callers can't mutate internal state without the lock),
    # so mutating that copy would never be seen by allow_request.
    state = manager._states["provider-a"]

    state.circuit_state = CircuitState.HALF_OPEN

    assert manager.allow_request("provider-a") is True

    manager.record_success("provider-a")

    state = manager.get("provider-a")

    assert state.circuit_state == CircuitState.CLOSED
    assert state.status == ProviderStatus.HEALTHY
    assert state.consecutive_failures == 0


# =========================================================
# FAILURE
# =========================================================


def test_first_failure_marks_provider_degraded(
    registered_manager: ReliabilityManager,
):
    manager = registered_manager

    manager.record_failure("provider-a")

    state = manager.get("provider-a")

    assert state.status == ProviderStatus.DEGRADED
    assert state.circuit_state == CircuitState.CLOSED
    assert state.consecutive_failures == 1
    assert state.total_failures == 1


def test_unhealthy_threshold_opens_circuit(
    registered_manager: ReliabilityManager,
):
    manager = registered_manager

    manager.record_failure("provider-a")
    manager.record_failure("provider-a")
    manager.record_failure("provider-a")

    state = manager.get("provider-a")

    assert state.status == ProviderStatus.UNHEALTHY
    assert state.circuit_state == CircuitState.OPEN
    assert state.consecutive_failures == 3
    assert state.total_failures == 3
    assert state.circuit_opened_at is not None


def test_open_circuit_rejects_request(
    registered_manager: ReliabilityManager,
):
    manager = registered_manager

    for _ in range(3):
        manager.record_failure("provider-a")

    assert (
        manager.allow_request("provider-a")
        is False
    )


# =========================================================
# HALF OPEN
# =========================================================


def test_open_circuit_becomes_half_open_after_timeout(
    registered_manager: ReliabilityManager,
):
    manager = registered_manager

    for _ in range(3):
        manager.record_failure("provider-a")

    # Mutate the manager's real internal state directly.
    # manager.get() returns a detached copy, so mutating that
    # copy's circuit_opened_at would never be seen by allow_request.
    state = manager._states["provider-a"]

    state.circuit_opened_at = (
        datetime.now(timezone.utc)
        - timedelta(seconds=11)
    )

    assert manager.allow_request("provider-a") is True

    assert (
        state.circuit_state
        == CircuitState.HALF_OPEN
    )


def test_only_one_half_open_probe_allowed(
    registered_manager: ReliabilityManager,
):
    manager = registered_manager

    for _ in range(3):
        manager.record_failure("provider-a")

    # Mutate the manager's real internal state directly (see note
    # in test_open_circuit_becomes_half_open_after_timeout above).
    state = manager._states["provider-a"]

    state.circuit_opened_at = (
        datetime.now(timezone.utc)
        - timedelta(seconds=11)
    )

    assert manager.allow_request("provider-a") is True
    assert manager.allow_request("provider-a") is False


def test_failed_half_open_probe_reopens_circuit(
    registered_manager: ReliabilityManager,
):
    manager = registered_manager

    # Mutate the manager's real internal state directly (see note
    # in test_open_circuit_becomes_half_open_after_timeout above).
    state = manager._states["provider-a"]

    state.circuit_state = CircuitState.HALF_OPEN

    assert manager.allow_request("provider-a") is True

    manager.record_failure("provider-a")

    state = manager.get("provider-a")

    assert state.circuit_state == CircuitState.OPEN
    assert state.status == ProviderStatus.UNHEALTHY
    assert state.circuit_opened_at is not None


# =========================================================
# AVAILABILITY
# =========================================================


def test_is_available_matches_allow_request(
    registered_manager: ReliabilityManager,
):
    manager = registered_manager

    assert (
        manager.is_available("provider-a")
        is True
    )

    for _ in range(3):
        manager.record_failure("provider-a")

    assert (
        manager.is_available("provider-a")
        is False
    )


# =========================================================
# LIST STATES
# =========================================================


def test_list_states_returns_snapshots(
    registered_manager: ReliabilityManager,
):
    manager = registered_manager

    manager.record_failure("provider-a")

    states = manager.list_states()

    assert len(states) == 1

    state = states[0]

    assert state.provider_name == "provider-a"
    assert state.status == ProviderStatus.DEGRADED
    assert state.total_failures == 1
    assert state.consecutive_failures == 1


def test_list_states_returns_copy(
    registered_manager: ReliabilityManager,
):
    manager = registered_manager

    states = manager.list_states()

    states[0].consecutive_failures = 999

    actual = manager.get("provider-a")

    assert actual.consecutive_failures == 0
