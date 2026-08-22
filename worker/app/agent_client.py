from __future__ import annotations

from typing import Any

import httpx


class AgentClient:
    """HTTP client for the Agenyx Agent service."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def run(
        self,
        intent: str,
    ) -> dict[str, Any]:
        """Execute an intent through the Agent service."""

        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        ) as client:
            response = await client.post(
                "/v1/agent/run",
                json={
                    "intent": intent,
                },
            )

            response.raise_for_status()

            payload = response.json()

            if not isinstance(payload, dict):
                raise RuntimeError(
                    "Agent returned an invalid response",
                )

            return payload
