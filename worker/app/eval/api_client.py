"""HTTP client for the Agenyx Evaluation API (Go backend).

The Python evaluation worker uses this client to persist evaluation
results to the Go evaluation API, which writes to PostgreSQL.
"""

from __future__ import annotations

from typing import Any

import httpx


class EvalAPIClient:
    """Client for the Agenyx Evaluation API."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            headers={
                "Content-Type": "application/json",
                "X-Agenyx-API-Key": api_key or "",
            },
        )

    async def create_evaluation(
        self,
        *,
        name: str,
        dataset_id: str,
        evaluation_type: str,
        models: list[dict[str, Any]],
        scorers: list[str] | None = None,
        priority: str = "normal",
        timeout_seconds: int = 3600,
        max_concurrency: int = 5,
        metadata: dict[str, Any] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """Create an evaluation via the API."""

        payload: dict[str, Any] = {
            "name": name,
            "dataset_id": dataset_id,
            "evaluation_type": evaluation_type,
            "models": models,
            "scorers": scorers or ["task_completion"],
            "priority": priority,
            "timeout_seconds": timeout_seconds,
            "max_concurrency": max_concurrency,
            "metadata": metadata or {},
            "description": description,
        }

        response = await self._client.post(
            "/api/v1/eval/evaluations",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def get_evaluation(self, evaluation_id: str) -> dict[str, Any]:
        """Get evaluation details."""

        response = await self._client.get(
            f"/api/v1/eval/evaluations/{evaluation_id}"
        )
        response.raise_for_status()
        return response.json()

    async def create_run(
        self,
        *,
        evaluation_id: str,
        model_id: str,
        provider_id: str,
        config_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Create an evaluation run."""

        # The Go API doesn't have a direct create-run endpoint yet.
        # Runs are created as part of evaluation creation.
        # This is a placeholder for future use.
        raise NotImplementedError(
            "Create run via API not yet implemented; runs are created "
            "during evaluation creation."
        )

    async def create_score(
        self,
        *,
        run_id: str,
        scorer_name: str,
        score_name: str,
        score_value: float,
        score_unit: str = "percent",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a score for a run."""

        # Placeholder - the Go API doesn't have a score endpoint yet.
        raise NotImplementedError(
            "Create score via API not yet implemented."
        )

    async def list_models(self) -> list[dict[str, Any]]:
        """List registered models."""

        response = await self._client.get("/api/v1/eval/models")
        response.raise_for_status()
        return response.json().get("models", [])

    async def create_model(
        self,
        *,
        model_id: str,
        provider_id: str,
        display_name: str = "",
        context_window: int = 0,
        capabilities: list[str] | None = None,
        endpoint_config: dict[str, Any] | None = None,
        generation_defaults: dict[str, Any] | None = None,
        timeout_seconds: int = 120,
        retry_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a model."""

        payload: dict[str, Any] = {
            "model_id": model_id,
            "provider_id": provider_id,
            "display_name": display_name,
            "context_window": context_window,
            "capabilities": capabilities or [],
            "endpoint_config": endpoint_config or {},
            "generation_defaults": generation_defaults or {},
            "timeout_seconds": timeout_seconds,
            "retry_config": retry_config or {},
        }

        response = await self._client.post(
            "/api/v1/eval/models",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def create_provider(
        self,
        *,
        provider_id: str,
        provider_type: str,
        endpoint_url: str,
        display_name: str = "",
        auth_ref: str = "",
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        """Register a provider."""

        payload: dict[str, Any] = {
            "provider_id": provider_id,
            "display_name": display_name,
            "provider_type": provider_type,
            "endpoint_url": endpoint_url,
            "auth_ref": auth_ref,
            "capabilities": capabilities or [],
        }

        response = await self._client.post(
            "/api/v1/eval/providers",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def list_providers(self) -> list[dict[str, Any]]:
        """List registered providers."""

        response = await self._client.get("/api/v1/eval/providers")
        response.raise_for_status()
        return response.json().get("providers", [])

    async def list_datasets(self) -> list[dict[str, Any]]:
        """List registered datasets."""

        response = await self._client.get("/api/v1/eval/datasets")
        response.raise_for_status()
        return response.json().get("datasets", [])

    async def create_dataset(
        self,
        *,
        name: str,
        version: str,
        checksum: str,
        s3_uri: str,
        row_count: int | None = None,
        description: str = "",
        created_by: str = "",
    ) -> dict[str, Any]:
        """Register a dataset."""

        payload: dict[str, Any] = {
            "name": name,
            "version": version,
            "checksum": checksum,
            "s3_uri": s3_uri,
            "row_count": row_count,
            "description": description,
            "created_by": created_by,
        }

        response = await self._client.post(
            "/api/v1/eval/datasets",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def health(self) -> bool:
        """Check whether the evaluation API is reachable."""

        try:
            response = await self._client.get("/api/v1/eval/health")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
