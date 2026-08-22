from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.agent_client import AgentClient
from app.queue import WorkerQueue


def utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


def iso_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return utc_now().isoformat()


class TaskExecutor:
    """Execute queued tasks through the Agent service."""

    def __init__(
        self,
        *,
        queue: WorkerQueue,
        agent_client: AgentClient,
        max_attempts: int = 4,
        retry_base_delay_seconds: int = 5,
        retry_max_delay_seconds: int = 60,
        shutdown_event: asyncio.Event | None = None,
    ) -> None:
        self.queue = queue
        self.agent_client = agent_client

        self.max_attempts = max_attempts
        self.retry_base_delay_seconds = retry_base_delay_seconds
        self.retry_max_delay_seconds = retry_max_delay_seconds

        self.shutdown_event = shutdown_event

    async def execute(
        self,
        *,
        message_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Execute a task and handle success, retry, or DLQ."""

        execution_id = str(payload["execution_id"])
        intent = str(payload["intent"])

        attempt = self._get_attempt(
            execution_id=execution_id,
        )

        attempt += 1

        started_at = utc_now()

        self._update_state(
            execution_id,
            status="running",
            attempt=attempt,
            worker=self.queue.consumer,
            started_at=started_at.isoformat(),
            original_message_id=message_id,
            error="",
            retry_at="",
            failed_at="",
        )

        try:
            result = await self.agent_client.run(intent)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            await self._handle_failure(
                execution_id=execution_id,
                intent=intent,
                message_id=message_id,
                attempt=attempt,
                started_at=started_at,
                error=str(exc),
            )
            return

        duration_ms = int(
            (utc_now() - started_at).total_seconds() * 1000,
        )

        answer = result.get("answer")
        steps = result.get("steps")

        self._update_state(
            execution_id,
            status="completed",
            answer=answer,
            error="",
            steps=int(steps) if steps is not None else None,
            attempt=attempt,
            worker=self.queue.consumer,
            completed_at=iso_now(),
            duration_ms=duration_ms,
            retry_at="",
            failed_at="",
        )

        self.queue.acknowledge(message_id)

    async def _handle_failure(
        self,
        *,
        execution_id: str,
        intent: str,
        message_id: str,
        attempt: int,
        started_at: datetime,
        error: str,
    ) -> None:
        """Handle retryable and permanent failures."""

        duration_ms = int(
            (utc_now() - started_at).total_seconds() * 1000,
        )

        # ---------------------------------------------------------
        # Maximum attempts reached -> DLQ
        # ---------------------------------------------------------

        if attempt >= self.max_attempts:
            dlq_message_id = self.queue.dead_letter(
                message_id=message_id,
                execution_id=execution_id,
                intent=intent,
                attempt=attempt,
                error=error,
            )

            self._update_state(
                execution_id,
                status="failed",
                error=error,
                attempt=attempt,
                worker=self.queue.consumer,
                failed_at=iso_now(),
                duration_ms=duration_ms,
                dead_letter_message_id=dlq_message_id,
                retry_at="",
            )

            return

        # ---------------------------------------------------------
        # Calculate exponential retry delay
        #
        # attempt 1 -> 5s
        # attempt 2 -> 10s
        # attempt 3 -> 20s
        # attempt 4 -> DLQ
        #
        # Maximum delay is capped at 60s.
        # ---------------------------------------------------------

        delay = self._retry_delay(attempt)

        retry_at = utc_now() + timedelta(
            seconds=delay,
        )

        self._update_state(
            execution_id,
            status="retrying",
            error=error,
            attempt=attempt,
            worker=self.queue.consumer,
            failed_at=iso_now(),
            retry_at=retry_at.isoformat(),
            duration_ms=duration_ms,
        )

        # ---------------------------------------------------------
        # IMPORTANT:
        #
        # The previous implementation used:
        #
        #     await asyncio.sleep(0)
        #
        # which means "do not wait".
        #
        # This actually waits for the configured retry delay while
        # still allowing graceful shutdown.
        # ---------------------------------------------------------

        await self._wait_for_retry(delay)

    async def _wait_for_retry(
        self,
        delay: int,
    ) -> None:
        """Wait for retry delay without blocking graceful shutdown."""

        if delay <= 0:
            return

        if self.shutdown_event is None:
            await asyncio.sleep(delay)
            return

        try:
            await asyncio.wait_for(
                self.shutdown_event.wait(),
                timeout=delay,
            )

        except asyncio.TimeoutError:
            # Retry delay elapsed normally.
            return

    def _retry_delay(
        self,
        attempt: int,
    ) -> int:
        """Calculate exponential retry backoff."""

        delay = self.retry_base_delay_seconds * (
            2 ** max(attempt - 1, 0)
        )

        return min(
            delay,
            self.retry_max_delay_seconds,
        )

    def _get_attempt(
        self,
        *,
        execution_id: str,
    ) -> int:
        """Read the current attempt number from Valkey."""

        state = self.queue.client.hget(
            f"agenyx:execution:{execution_id}",
            "attempt",
        )

        if state is None:
            return 0

        try:
            return int(state)
        except (TypeError, ValueError):
            return 0

    def _update_state(
        self,
        execution_id: str,
        *,
        status: str,
        answer: str | None = None,
        error: str | None = None,
        steps: int | None = None,
        attempt: int | None = None,
        worker: str | None = None,
        queued_at: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        failed_at: str | None = None,
        retry_at: str | None = None,
        duration_ms: int | None = None,
        original_message_id: str | None = None,
        dead_letter_message_id: str | None = None,
    ) -> None:
        """Update execution state in Valkey."""

        key = f"agenyx:execution:{execution_id}"

        mapping: dict[str, Any] = {
            "status": status,
        }

        if answer is not None:
            mapping["answer"] = answer

        if error is not None:
            mapping["error"] = error

        if steps is not None:
            mapping["steps"] = str(steps)

        if attempt is not None:
            mapping["attempt"] = str(attempt)

        if worker is not None:
            mapping["worker"] = worker

        if queued_at is not None:
            mapping["queued_at"] = queued_at

        if started_at is not None:
            mapping["started_at"] = started_at

        if completed_at is not None:
            mapping["completed_at"] = completed_at

        if failed_at is not None:
            mapping["failed_at"] = failed_at

        if retry_at is not None:
            mapping["retry_at"] = retry_at

        if duration_ms is not None:
            mapping["duration_ms"] = str(duration_ms)

        if original_message_id is not None:
            mapping["original_message_id"] = original_message_id

        if dead_letter_message_id is not None:
            mapping["dead_letter_message_id"] = (
                dead_letter_message_id
            )

        self.queue.client.hset(
            key,
            mapping=mapping,
        )
