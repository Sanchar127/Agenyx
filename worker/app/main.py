
from __future__ import annotations

import asyncio
import logging
import signal

from app.agent_client import AgentClient
from app.config import get_settings
from app.executor import TaskExecutor
from app.queue import WorkerQueue
from app.worker import Worker


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s %(levelname)s "
        "%(name)s: %(message)s"
    ),
)


def create_worker() -> Worker:
    """Create the configured worker."""

    settings = get_settings()

    queue = WorkerQueue(
        url=settings.valkey_url,
        stream=settings.task_stream,
        group=settings.consumer_group,
        consumer=settings.consumer_name,
        dead_letter_stream="agenyx:tasks:dead-letter",
        pending_idle_ms=settings.pending_idle_ms,
        pending_batch_size=settings.pending_batch_size,
    )

    agent_client = AgentClient(
        base_url=settings.agent_url,
        timeout=settings.agent_timeout_seconds,
    )

    # Create the Worker first so it owns the single shutdown event.
    #
    # We temporarily create the executor with the worker's event
    # after the Worker exists.
    #
    # The Worker and Executor share exactly one shutdown signal.
    worker = Worker(
        queue=queue,
        executor=None,  # type: ignore[arg-type]
    )

    executor = TaskExecutor(
        queue=queue,
        agent_client=agent_client,
        max_attempts=settings.max_attempts,
        retry_base_delay_seconds=(
            settings.retry_base_delay_seconds
        ),
        retry_max_delay_seconds=(
            settings.retry_max_delay_seconds
        ),
        shutdown_event=worker.shutdown_event,
    )

    worker.executor = executor

    return worker


async def async_main() -> None:
    """Run the worker."""

    worker = create_worker()

    loop = asyncio.get_running_loop()

    for sig in (
        signal.SIGTERM,
        signal.SIGINT,
    ):
        loop.add_signal_handler(
            sig,
            worker.request_shutdown,
        )

    await worker.run()


def main() -> None:
    """Start the worker."""

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
