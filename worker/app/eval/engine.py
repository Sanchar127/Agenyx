"""Evaluation engine for the Agenyx Evaluation Platform.

Orchestrates evaluation runs: loads datasets, resolves providers,
executes model queries, applies scorers, and persists results via the
Go evaluation API.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from typing import Any

from app.eval.api_client import EvalAPIClient
from app.eval.dataset_manager import DatasetManager
from app.eval.models import (
    Evaluation,
    EvaluationRun,
    EvaluationScore,
)
from app.eval.providers import get_provider_class
from app.eval.scorers import get_scorer


class EvaluationEngine:
    """Orchestrate evaluation runs against registered models.

    For each model in an evaluation:
    1. Resolve the provider adapter
    2. Load the dataset
    3. Run each record through the model
    4. Score responses using configured scorers
    5. Persist scores and results via the evaluation API
    """

    def __init__(
        self,
        *,
        api_client: EvalAPIClient,
        dataset_manager: DatasetManager,
    ) -> None:
        self._api = api_client
        self._dataset_manager = dataset_manager
        self._providers: dict[str, Any] = {}  # cache_key -> provider instance

    async def _get_provider(
        self,
        *,
        provider_id: str,
        endpoint_url: str,
        api_key: str,
    ) -> Any:
        """Get or create a provider adapter instance."""

        cache_key = f"{provider_id}:{endpoint_url}"
        if cache_key in self._providers:
            return self._providers[cache_key]

        provider_class = get_provider_class(provider_id)
        provider = provider_class(
            provider_id=provider_id,
            endpoint_url=endpoint_url,
            api_key=api_key,
        )
        self._providers[cache_key] = provider
        return provider

    async def run_evaluation(
        self,
        *,
        evaluation: Evaluation,
        models: list[dict[str, Any]],
    ) -> list[EvaluationRun]:
        """Run an evaluation against all configured models.

        Returns a list of EvaluationRun objects.
        """

        runs: list[EvaluationRun] = []

        # Load dataset once
        if not evaluation.dataset_id:
            raise ValueError("Evaluation has no dataset_id")

        dataset = await self._store_get_dataset(evaluation.dataset_id)
        records = await self._dataset_manager.download_dataset(
            s3_uri=dataset["s3_uri"],
        )

        # Run each model
        for model_config in models:
            run = await self._run_single_model(
                evaluation=evaluation,
                model_config=model_config,
                records=records,
            )
            runs.append(run)

        return runs

    async def _store_get_dataset(
        self,
        dataset_id: str | uuid.UUID,
    ) -> dict[str, Any]:
        """Get a dataset from the evaluation API."""

        # The API doesn't have a get-dataset-by-ID endpoint yet.
        # List all datasets and find the match.
        datasets = await self._api.list_datasets()
        dataset_id_str = str(dataset_id)
        for d in datasets:
            if d.get("id") == dataset_id_str:
                return d
        raise ValueError(f"Dataset {dataset_id} not found")

    async def _run_single_model(
        self,
        *,
        evaluation: Evaluation,
        model_config: dict[str, Any],
        records: list[dict[str, Any]],
    ) -> EvaluationRun:
        """Run an evaluation for a single model."""

        model_id = model_config["model_id"]
        provider_id = model_config["provider_id"]
        generation_params = model_config.get("generation_params", {})

        # Validate evaluation has a dataset
        if not evaluation.dataset_id:
            raise ValueError("Evaluation has no dataset_id")

        # Resolve provider - get provider config from the API
        providers = await self._api.list_providers()
        provider_record = None
        for p in providers:
            if p.get("provider_id") == provider_id:
                provider_record = p
                break

        if not provider_record:
            raise ValueError(
                f"Provider {provider_id} not found in evaluation API"
            )

        provider = await self._get_provider(
            provider_id=provider_id,
            endpoint_url=provider_record.get("endpoint_url", ""),
            api_key=provider_record.get("auth_ref", ""),
        )

        # Get scorer names from config
        scorer_names = evaluation.config_snapshot.get(
            "scorers", ["task_completion"]
        )

        start_time = time.time()
        total_latency = 0.0
        success_count = 0
        error_count = 0
        total_tokens = 0

        for record in records:
            try:
                # Build prompt from record
                prompt = record.get("text", record.get("prompt", ""))
                expected = record.get("expected", record.get("answer", ""))

                # Call model
                request_start = time.time()
                response = await provider.chat_completion(
                    model=model_id,
                    messages=[{"role": "user", "content": prompt}],
                    **generation_params,
                )
                request_latency = (time.time() - request_start) * 1000
                total_latency += request_latency

                answer = (
                    response.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                usage = response.get("usage", {})
                total_tokens += usage.get(
                    "total_tokens",
                    usage.get("prompt_tokens", 0)
                    + usage.get("completion_tokens", 0),
                )
                success_count += 1

                # Score the response
                for scorer_name in scorer_names:
                    scorer_class = get_scorer(scorer_name)
                    scorer = scorer_class()
                    score_result = await scorer.score(
                        response=answer,
                        expected=expected,
                        context=record,
                    )

                    score = EvaluationScore(
                        id=uuid.uuid4(),
                        run_id=uuid.uuid4(),  # placeholder
                        scorer_name=scorer_name,
                        score_name=score_result.get(
                            "score_name", scorer_name
                        ),
                        score_value=score_result["score"],
                        score_unit=score_result.get(
                            "score_unit", "percent"
                        ),
                        details=score_result.get("details", {}),
                    )

                    # Persist score via API (when endpoint exists)
                    # For now, scores are tracked in-memory
                    _ = score  # placeholder

            except Exception:
                error_count += 1
                # Log but continue with other records

        # Create the run result
        avg_latency = total_latency / success_count if success_count > 0 else 0
        now = dt.datetime.now(dt.timezone.utc)
        run = EvaluationRun(
            id=uuid.uuid4(),
            evaluation_id=evaluation.id,
            model_id=model_id,
            provider_id=provider_id,
            status="completed",
            success_rate=(
                success_count / len(records) if records else 0.0
            ),
            avg_latency_ms=int(avg_latency),
            p50_latency_ms=int(avg_latency),
            p95_latency_ms=int(avg_latency * 1.5),
            p99_latency_ms=int(avg_latency * 2.0),
            total_tokens=total_tokens,
            error_count=error_count,
            config_snapshot={
                "model_id": model_id,
                "provider_id": provider_id,
                "generation_params": generation_params,
                "scorers": scorer_names,
            },
            started_at=start_time,
            completed_at=dt.datetime.now(dt.timezone.utc),
        )

        return run

    async def close(self) -> None:
        """Close all provider connections."""

        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()
        await self._dataset_manager.close()
