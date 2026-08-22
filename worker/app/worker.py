
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from valkey.exceptions import TimeoutError as ValkeyTimeoutError

from app.executor import TaskExecutor
from app.queue import WorkerQueue


logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return the current UTC time."""

    return datetime.now(timezone.utc)


def parse_retry_at(
    value: str | None,
) -> datetime | None:
    """Parse an ISO-8601 retry timestamp."""

    if not value:
        return None

    try:
        retry_at = datetime.fromisoformat(value)

        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(
                tzinfo=timezone.utc,
            )

        return retry_at

    except (TypeError, ValueError):
        logger.warning(
            "invalid_retry_at value=%r",
            value,
        )
        return None


class Worker:
    """Long-running Valkey task consumer."""

    def __init__(
        self,
        *,
        queue: WorkerQueue,
        executor: TaskExecutor,
    ) -> None:
        self.queue = queue
        self.executor = executor

        # Single shutdown event owned by the worker.
        #
        # TaskExecutor should use this same event when waiting
        # during retry backoff so SIGTERM/SIGINT can interrupt
        # the wait immediately.
        self._shutdown = asyncio.Event()

    @property
    def shutdown_event(self) -> asyncio.Event:
        """Return the worker shutdown event."""

        return self._shutdown

    def request_shutdown(self) -> None:
        """Request graceful worker shutdown."""

        if self._shutdown.is_set():
            return

        logger.info(
            "worker_shutdown_requested",
        )

        self._shutdown.set()

    async def run(self) -> None:
        """Run the worker loop."""

        self.queue.ensure_group()

        logger.info(
            "worker_started consumer=%s",
            self.queue.consumer,
        )

        try:
            while not self._shutdown.is_set():
                # First recover tasks abandoned by another worker.
                await self._recover_pending()

                if self._shutdown.is_set():
                    break

                try:
                    messages = await asyncio.to_thread(
                        self.queue.read,
                    )

                except ValkeyTimeoutError:
                    logger.debug(
                        "valkey_read_timeout",
                    )
                    continue

                except Exception:
                    logger.exception(
                        "queue_read_failed; retrying",
                    )

                    # Wait briefly before retrying the queue.
                    #
                    # The wait is interruptible by SIGTERM/SIGINT.
                    try:
                        await asyncio.wait_for(
                            self._shutdown.wait(),
                            timeout=2,
                        )
                    except asyncio.TimeoutError:
                        pass

                    continue

                if not messages:
                    continue

                for _, entries in messages:
                    for message_id, payload in entries:
                        if self._shutdown.is_set():
                            break

                        await self._process(
                            message_id=message_id,
                            payload=payload,
                        )

        finally:
            logger.info(
                "worker_stopping",
            )

            self.queue.close()

            logger.info(
                "worker_stopped",
            )

    async def _recover_pending(self) -> None:
        """Recover abandoned pending tasks."""

        try:
            pending = await asyncio.to_thread(
                self.queue.claim_pending,
            )

        except ValkeyTimeoutError:
            logger.debug(
                "valkey_pending_recovery_timeout",
            )
            return

        except Exception:
            logger.exception(
                "pending_recovery_failed",
            )
            return

        for message_id, payload in pending:
            if self._shutdown.is_set():
                return

            execution_id = payload.get(
                "execution_id",
            )

            if not execution_id:
                logger.error(
                    "pending_task_missing_execution_id "
                    "id=%s",
                    message_id,
                )
                continue

            execution_key = (
                f"agenyx:execution:{execution_id}"
            )

            retry_at_raw = self.queue.client.hget(
                execution_key,
                "retry_at",
            )

            retry_at = parse_retry_at(
                retry_at_raw,
            )

            if retry_at is not None:
                now = utc_now()

                if retry_at > now:
                    remaining = (
                        retry_at - now
                    ).total_seconds()

                    logger.info(
                        "pending_task_retry_not_ready "
                        "id=%s execution_id=%s "
                        "retry_at=%s "
                        "remaining_seconds=%.2f",
                        message_id,
                        execution_id,
                        retry_at.isoformat(),
                        max(remaining, 0),
                    )

                    # IMPORTANT:
                    #
                    # Do not execute the task yet.
                    # The message remains pending in the
                    # consumer group and can be reclaimed again
                    # after the retry timestamp has passed.
                    continue

            logger.info(
                "pending_task_claimed "
                "id=%s execution_id=%s",
                message_id,
                execution_id,
            )

            await self._process(
                message_id=message_id,
                payload=payload,
            )

    async def _process(
        self,
        *,
        message_id: str,
        payload: dict[str, str],
    ) -> None:
        """Process a single task."""

        execution_id = payload.get(
            "execution_id",
        )

        if not execution_id:
            logger.error(
                "task_missing_execution_id "
                "id=%s",
                message_id,
            )
            return

        logger.info(
            "task_received "
            "id=%s execution_id=%s",
            message_id,
            execution_id,
        )

        try:
            await self.executor.execute(
                message_id=message_id,
                payload=payload,
            )

            state = self.queue.client.hget(
                f"agenyx:execution:{execution_id}",
                "status",
            )

            if state == "completed":
                logger.info(
                    "task_completed "
                    "id=%s execution_id=%s",
                    message_id,
                    execution_id,
                )

            elif state == "retrying":
                retry_at = self.queue.client.hget(
                    f"agenyx:execution:{execution_id}",
                    "retry_at",
                )

                logger.warning(
                    "task_retrying "
                    "id=%s execution_id=%s "
                    "retry_at=%s",
                    message_id,
                    execution_id,
                    retry_at,
                )

            elif state == "failed":
                logger.error(
                    "task_failed "
                    "id=%s execution_id=%s",
                    message_id,
                    execution_id,
                )

            else:
                logger.warning(
                    "task_finished_with_unknown_state "
                    "id=%s execution_id=%s "
                    "status=%s",
                    message_id,
                    execution_id,
                    state,
                )

        except asyncio.CancelledError:
            logger.warning(
                "task_processing_cancelled "
                "id=%s execution_id=%s",
                message_id,
                execution_id,
            )
            raise

        except Exception:
            logger.exception(
                "task_processing_failed "
                "id=%s execution_id=%s",
                message_id,
                execution_id,
            )
