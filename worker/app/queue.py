from __future__ import annotations

from typing import Any

import valkey
from valkey.sentinel import Sentinel


class WorkerQueue:
    """Valkey Streams consumer used by workers."""

    def __init__(
        self,
        *,
        url: str,
        stream: str,
        group: str,
        consumer: str,
        dead_letter_stream: str = "agenyx:tasks:dead-letter",
        pending_idle_ms: int = 10_000,
        pending_batch_size: int = 10,
        sentinel_hosts: list[tuple[str, int]] | None = None,
        master_name: str | None = None,
        password: str | None = None,
    ) -> None:
        if pending_idle_ms < 1:
            raise ValueError(
                "pending_idle_ms must be greater than zero",
            )

        if pending_batch_size < 1:
            raise ValueError(
                "pending_batch_size must be greater than zero",
            )

        self.stream = stream
        self.group = group
        self.consumer = consumer
        self.dead_letter_stream = dead_letter_stream

        self.pending_idle_ms = pending_idle_ms
        self.pending_batch_size = pending_batch_size

        if sentinel_hosts and master_name:
            sentinel = Sentinel(
                sentinel_hosts,
                password=password,
                decode_responses=True,
            )

            self.client = sentinel.master_for(
                master_name,
                password=password,
                decode_responses=True,
            )

        else:
            self.client = valkey.from_url(
                url,
                decode_responses=True,
            )

    def ensure_group(self) -> None:
        """Create the consumer group if necessary."""

        try:
            self.client.xgroup_create(
                name=self.stream,
                groupname=self.group,
                id="0",
                mkstream=True,
            )
        except valkey.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def read(
        self,
    ) -> list[tuple[str, list[tuple[str, dict[str, Any]]]]]:
        """Read new messages from the stream."""

        return self.client.xreadgroup(
            groupname=self.group,
            consumername=self.consumer,
            streams={
                self.stream: ">",
            },
            count=1,
            block=5000,
        )

    def claim_pending(
        self,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Claim tasks abandoned by another worker."""

        result = self.client.xautoclaim(
            name=self.stream,
            groupname=self.group,
            consumername=self.consumer,
            min_idle_time=self.pending_idle_ms,
            start_id="0-0",
            count=self.pending_batch_size,
        )

        if not result:
            return []

        return result[1]

    def acknowledge(
        self,
        message_id: str,
    ) -> None:
        """Acknowledge a successfully handled task."""

        self.client.xack(
            self.stream,
            self.group,
            message_id,
        )

    def dead_letter(
        self,
        *,
        message_id: str,
        execution_id: str,
        intent: str,
        attempt: int,
        error: str,
    ) -> str:
        """Move a permanently failed task to the DLQ."""

        dlq_message_id = str(
            self.client.xadd(
                self.dead_letter_stream,
                {
                    "execution_id": execution_id,
                    "intent": intent,
                    "attempt": str(attempt),
                    "original_message_id": message_id,
                    "error": error,
                    "consumer": self.consumer,
                },
            ),
        )

        self.acknowledge(message_id)

        return dlq_message_id

    def pending_count(self) -> int:
        """Return the number of pending tasks."""

        result = self.client.xpending(
            self.stream,
            self.group,
        )

        return int(result[0])

    def close(self) -> None:
        """Close the Valkey client."""

        self.client.close()
