from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ProviderStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ProviderHealthState:
    provider_name: str

    status: ProviderStatus = ProviderStatus.HEALTHY

    consecutive_failures: int = 0

    total_failures: int = 0
    total_successes: int = 0

    last_failure_at: datetime | None = None
    last_success_at: datetime | None = None
