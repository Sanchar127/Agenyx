from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.logging import logger


class SemanticRouterError(Exception):
    """Raised when the semantic router cannot provide a decision."""


@dataclass(frozen=True)
class RoutingDecision:
    model: str
    provider: str
    score: float | None = None
    strategy: str | None = None


class SemanticRouterClient:
    """
    Client for the Agenyx semantic-router service.

    The agent asks the router which model should handle
    the current execution.

    This client does not:
    - execute inference
    - execute tools
    - contain routing logic
    - select models locally
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=min(timeout, 2.0),
                read=timeout,
                write=timeout,
                pool=timeout,
            ),
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=20,
            ),
        )

    async def close(self) -> None:
        if not self._client.is_closed:
            await self._client.aclose()

    async def route(
        self,
        *,
        session_id: str,
        task: str,
        messages: list[dict[str, Any]],
        required_capabilities: list[str] | None = None,
    ) -> RoutingDecision:

        payload = {
            "session_id": session_id,
            "task": task,
            "messages": messages,
            "constraints": {
                "required_capabilities": (
                    required_capabilities or []
                ),
            },
        }

        url = f"{self.base_url}/route"

        logger.info(
            "semantic_router_request_started "
            "execution_session=%s task=%s",
            session_id,
            task,
        )

        try:
            response = await self._client.post(
                url,
                json=payload,
            )

        except httpx.TimeoutException as exc:
            logger.error(
                "semantic_router_timeout "
                "session_id=%s timeout=%s",
                session_id,
                self.timeout,
            )

            raise SemanticRouterError(
                "Semantic router request timed out"
            ) from exc

        except httpx.HTTPError as exc:
            logger.error(
                "semantic_router_connection_error "
                "session_id=%s error=%s",
                session_id,
                str(exc),
            )

            raise SemanticRouterError(
                "Unable to connect to semantic router"
            ) from exc

        if response.status_code >= 500:
            raise SemanticRouterError(
                f"Semantic router returned HTTP "
                f"{response.status_code}"
            )

        if response.status_code >= 400:
            raise SemanticRouterError(
                f"Semantic router rejected request "
                f"with HTTP {response.status_code}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise SemanticRouterError(
                "Semantic router returned invalid JSON"
            ) from exc

        if not isinstance(data, dict):
            raise SemanticRouterError(
                "Semantic router response must be an object"
            )

        model = data.get("model")
        provider = data.get("provider")

        if not isinstance(model, str) or not model:
            raise SemanticRouterError(
                "Semantic router response is missing model"
            )

        if not isinstance(provider, str) or not provider:
            raise SemanticRouterError(
                "Semantic router response is missing provider"
            )

        score = data.get("score")

        if score is not None and not isinstance(
            score,
            (int, float),
        ):
            score = None

        strategy = data.get("strategy")

        if strategy is not None and not isinstance(
            strategy,
            str,
        ):
            strategy = None

        decision = RoutingDecision(
            model=model,
            provider=provider,
            score=float(score) if score is not None else None,
            strategy=strategy,
        )

        logger.info(
            "semantic_router_decision "
            "session_id=%s model=%s provider=%s "
            "score=%s strategy=%s",
            session_id,
            decision.model,
            decision.provider,
            decision.score,
            decision.strategy,
        )

        return decision
