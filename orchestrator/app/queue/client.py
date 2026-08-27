from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import valkey
from valkey.sentinel import Sentinel

from app.core.config import Settings


class QueueError(RuntimeError):
    """Raised when the task queue cannot be accessed."""


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


class TaskQueue:
    """Valkey Streams client connected through Valkey Sentinel."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = self._create_client()

    def _create_client(self) -> valkey.Redis:
        """Create a Valkey client connected to the Sentinel primary."""

        addresses = self.settings.valkey_sentinel_addrs.strip()

        if not addresses:
            raise QueueError(
                "Valkey Sentinel addresses are not configured",
            )

        sentinel_addresses: list[tuple[str, int]] = []

        for address in addresses.split(","):
            address = address.strip()

            if not address:
                continue

            try:
                host, port_string = address.rsplit(":", 1)
                port = int(port_string)

                if not host:
                    raise ValueError("empty host")

                if not 1 <= port <= 65535:
                    raise ValueError("invalid port")

            except ValueError as exc:
                raise QueueError(
                    f"Invalid Valkey Sentinel address: {address!r}",
                ) from exc

            sentinel_addresses.append((host, port))

        if not sentinel_addresses:
            raise QueueError(
                "No valid Valkey Sentinel addresses configured",
            )

        try:
            sentinel = Sentinel(
                sentinel_addresses,
                password=self.settings.valkey_password or None,
                decode_responses=True,
            )

            client = sentinel.master_for(
                self.settings.valkey_master_name,
                password=self.settings.valkey_password or None,
                db=0,
                decode_responses=True,
            )

            return client

        except Exception as exc:
            raise QueueError(
                "Unable to initialize Valkey Sentinel client",
            ) from exc

    def ping(self) -> bool:
        """Check whether the Valkey primary is reachable."""

        try:
            return bool(self.client.ping())
        except Exception as exc:
            raise QueueError(
                "Unable to connect to Valkey",
            ) from exc

    def ensure_consumer_group(self) -> None:
        """Create the task consumer group if it does not exist."""

        try:
            self.client.xgroup_create(
                name=self.settings.task_stream,
                groupname=self.settings.consumer_group,
                id="0",
                mkstream=True,
            )

        except valkey.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                return

            raise QueueError(
                "Unable to create Valkey consumer group",
            ) from exc

        except Exception as exc:
            raise QueueError(
                "Unable to create Valkey consumer group",
            ) from exc

    def create_execution(
        self,
        *,
        execution_id: str,
        intent: str,
    ) -> None:
        """Create the initial execution state."""

        key = f"agenyx:execution:{execution_id}"
        now = utc_now()

        try:
            self.client.hset(
                key,
                mapping={
                    "execution_id": execution_id,
                    "status": "queued",
                    "intent": intent,
                    "error": "",
                    "attempt": "0",
                    "max_attempts": str(
                        self.settings.max_attempts,
                    ),
                    "queued_at": now,
                },
            )

            self.client.expire(
                key,
                self.settings.execution_ttl_seconds,
            )

        except Exception as exc:
            raise QueueError(
                "Unable to create execution state",
            ) from exc

    def enqueue(
        self,
        *,
        execution_id: str,
        intent: str,
    ) -> str:
        """Publish an execution to the task stream."""

        try:
            message_id = self.client.xadd(
                self.settings.task_stream,
                {
                    "execution_id": execution_id,
                    "intent": intent,
                },
            )

            return str(message_id)

        except Exception as exc:
            raise QueueError(
                "Unable to enqueue agent execution",
            ) from exc

    def get_execution(
        self,
        execution_id: str,
    ) -> dict[str, Any]:
        """Retrieve execution state."""

        key = f"agenyx:execution:{execution_id}"

        try:
            return dict(
                self.client.hgetall(key),
            )

        except Exception as exc:
            raise QueueError(
                "Unable to retrieve execution state",
            ) from exc

    def update_execution(
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
        """Update execution state."""

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
            mapping["dead_letter_message_id"] = dead_letter_message_id

        try:
            self.client.hset(
                key,
                mapping=mapping,
            )

            self.client.expire(
                key,
                self.settings.execution_ttl_seconds,
            )

        except Exception as exc:
            raise QueueError(
                "Unable to update execution state",
            ) from exc

    def close(self) -> None:
        """Close the Valkey connection."""

        try:
            self.client.close()
        except Exception:
            pass
