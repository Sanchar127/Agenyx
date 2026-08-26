from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ProviderStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ProviderHealthState:
    provider_name: str

    status: ProviderStatus = ProviderStatus.HEALTHY
    circuit_state: CircuitState = CircuitState.CLOSED

    consecutive_failures: int = 0

    total_failures: int = 0
    total_successes: int = 0

    last_failure_at: datetime | None = None
    last_success_at: datetime | None = None

    circuit_opened_at: datetime | None = None
    circuit_half_opened_at: datetime | None = None
