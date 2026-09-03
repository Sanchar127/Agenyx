
from __future__ import annotations

import os
import socket
from functools import lru_cache


class Settings:
    """Worker configuration."""

    def __init__(self) -> None:
        self.valkey_url = os.getenv(
            "VALKEY_URL",
            "redis://valkey:6379/0",
        )

        self.task_stream = os.getenv(
            "TASK_STREAM",
            "agenyx:tasks",
        )

        self.consumer_group = os.getenv(
            "CONSUMER_GROUP",
            "agenyx-workers",
        )

        self.consumer_name = os.getenv(
            "CONSUMER_NAME",
            socket.gethostname(),
        )

        self.valkey_sentinel_hosts = self._parse_sentinel_hosts(
            os.getenv(
                "VALKEY_SENTINEL_HOSTS",
                "",
            ),
        )

        self.valkey_master_name = os.getenv(
            "VALKEY_MASTER_NAME",
            "mymaster",
        )

        self.valkey_password = os.getenv(
            "VALKEY_PASSWORD",
            "",
        )

        self.agent_url = os.getenv(
            "AGENT_URL",
            "http://agent:8000",
        )

        self.agent_timeout_seconds = float(
            os.getenv(
                "AGENT_TIMEOUT_SECONDS",
                "120",
            ),
        )

        self.max_attempts = int(
            os.getenv(
                "MAX_ATTEMPTS",
                "4",
            ),
        )

        self.retry_base_delay_seconds = int(
            os.getenv(
                "RETRY_BASE_DELAY_SECONDS",
                "5",
            ),
        )

        self.retry_max_delay_seconds = int(
            os.getenv(
                "RETRY_MAX_DELAY_SECONDS",
                "60",
            ),
        )

        self.pending_idle_ms = int(
            os.getenv(
                "PENDING_IDLE_MS",
                "10000",
            ),
        )

        self.pending_batch_size = int(
            os.getenv(
                "PENDING_BATCH_SIZE",
                "10",
            ),
        )



    @staticmethod
    def _parse_sentinel_hosts(
        value: str,
    ) -> list[tuple[str, int]]:
        """Parse comma-separated Sentinel host:port values."""

        hosts: list[tuple[str, int]] = []

        if not value.strip():
            return hosts

        for address in value.split(","):
            address = address.strip()

            if not address:
                continue

            try:
                host, port = address.rsplit(":", 1)

                hosts.append(
                    (
                        host.strip(),
                        int(port),
                    )
                )

            except ValueError as exc:
                raise ValueError(
                    f"Invalid VALKEY_SENTINEL_HOSTS entry: {address!r}"
                ) from exc

        return hosts


@lru_cache
def get_settings() -> Settings:
    """Return cached worker settings."""

    return Settings()
