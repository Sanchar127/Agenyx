from __future__ import annotations

import random
from dataclasses import dataclass

from app.core.errors import (
    ExecutionCancelled,
    ExecutionLimitExceeded,
    LLMConnectionError,
    LLMTimeoutError,
    ToolExecutionError,
)


@dataclass(frozen=True)
class RetryPolicy:
    """
    Defines retry decisions and backoff behavior for transient failures.

    RetryPolicy only answers:
        - whether an operation should be retried
        - how long the caller should wait before retrying

    It does not execute operations, sleep, handle cancellation,
    or manage the overall execution timeout.
    """

    max_attempts: int = 3
    base_delay: float = 0.2
    max_delay: float = 2.0
    jitter: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError(
                "max_attempts must be greater than zero"
            )

        if self.base_delay < 0:
            raise ValueError(
                "base_delay must be greater than or equal to zero"
            )

        if self.max_delay < 0:
            raise ValueError(
                "max_delay must be greater than or equal to zero"
            )

        if self.max_delay < self.base_delay:
            raise ValueError(
                "max_delay must be greater than or equal to base_delay"
            )

    def should_retry(
        self,
        *,
        error: Exception,
        attempt: int,
    ) -> bool:
        """
        Determine whether another attempt should be made.

        `attempt` is the attempt that just failed.

        Example with max_attempts=3:

            attempt=1 -> retry allowed
            attempt=2 -> retry allowed
            attempt=3 -> no retry
        """

        if attempt < 1:
            raise ValueError(
                "attempt must be greater than or equal to one"
            )

        if attempt >= self.max_attempts:
            return False

        if isinstance(
            error,
            (
                ExecutionCancelled,
                ExecutionLimitExceeded,
            ),
        ):
            return False

        return isinstance(
            error,
            (
                LLMConnectionError,
                LLMTimeoutError,
                ToolExecutionError,
            ),
        )

    def get_delay(self, *, attempt: int) -> float:
        """
        Calculate the delay before the next retry.

        Uses exponential backoff:

            base_delay * 2 ** (attempt - 1)

        The result is capped at max_delay.

        Jitter, when enabled, randomizes the delay between zero
        and the calculated maximum delay.
        """

        if attempt < 1:
            raise ValueError(
                "attempt must be greater than or equal to one"
            )

        exponential_delay = self.base_delay * (
            2 ** (attempt - 1)
        )

        capped_delay = min(
            exponential_delay,
            self.max_delay,
        )

        if not self.jitter:
            return capped_delay

        return random.uniform(
            0.0,
            capped_delay,
        )
