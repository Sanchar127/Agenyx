"""Python data models for the Agenyx Evaluation Platform.

These mirror the Go models in internal/eval/models.py so the Python
evaluation worker can work with the same data structures.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Evaluation:
    """Top-level evaluation configuration snapshot."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = ""
    description: str = ""
    dataset_id: uuid.UUID | None = None
    evaluation_type: str = "llm"
    status: str = "queued"
    progress: int = 0
    priority: str = "normal"
    timeout_seconds: int = 3600
    max_concurrency: int = 5
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_by: str = ""
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    completed_at: dt.datetime | None = None
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "dataset_id": str(self.dataset_id) if self.dataset_id else None,
            "evaluation_type": self.evaluation_type,
            "status": self.status,
            "progress": self.progress,
            "priority": self.priority,
            "timeout_seconds": self.timeout_seconds,
            "max_concurrency": self.max_concurrency,
            "config_snapshot": self.config_snapshot,
            "metadata": self.metadata,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
        }


@dataclass
class EvaluationRun:
    """A single model execution within an evaluation."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    evaluation_id: uuid.UUID | None = None
    model_id: str = ""
    provider_id: str = ""
    status: str = "queued"
    success_rate: float | None = None
    avg_latency_ms: int | None = None
    p50_latency_ms: int | None = None
    p95_latency_ms: int | None = None
    p99_latency_ms: int | None = None
    total_tokens: int | None = None
    total_cost_usd: float | None = None
    error_count: int | None = None
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "evaluation_id": str(self.evaluation_id) if self.evaluation_id else None,
            "model_id": self.model_id,
            "provider_id": self.provider_id,
            "status": self.status,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "error_count": self.error_count,
            "config_snapshot": self.config_snapshot,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_message": self.error_message,
        }


@dataclass
class EvaluationScore:
    """A scored metric for a run."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    run_id: uuid.UUID | None = None
    scorer_name: str = ""
    score_name: str = ""
    score_value: float = 0.0
    score_unit: str = "percent"
    details: dict[str, Any] = field(default_factory=dict)
    recorded_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "run_id": str(self.run_id) if self.run_id else None,
            "scorer_name": self.scorer_name,
            "score_name": self.score_name,
            "score_value": self.score_value,
            "score_unit": self.score_unit,
            "details": self.details,
            "recorded_at": self.recorded_at.isoformat(),
        }


@dataclass
class EvaluationArtifact:
    """A stored artifact for a run."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    run_id: uuid.UUID | None = None
    artifact_type: str = ""
    s3_uri: str = ""
    size_bytes: int | None = None
    checksum: str = ""
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "run_id": str(self.run_id) if self.run_id else None,
            "artifact_type": self.artifact_type,
            "s3_uri": self.s3_uri,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Model:
    """A registered evaluation model."""

    model_id: str = ""
    provider_id: str = ""
    display_name: str = ""
    context_window: int = 0
    capabilities: list[str] = field(default_factory=list)
    endpoint_config: dict[str, Any] = field(default_factory=dict)
    generation_defaults: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 120
    retry_config: dict[str, Any] = field(default_factory=dict)
    health_status: str = "unknown"
    health_checked_at: dt.datetime | None = None
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


@dataclass
class Provider:
    """A registered inference provider."""

    provider_id: str = ""
    display_name: str = ""
    provider_type: str = ""
    endpoint_url: str = ""
    auth_ref: str = ""
    capabilities: list[str] = field(default_factory=list)
    health_status: str = "unknown"
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


@dataclass
class Dataset:
    """A registered evaluation dataset."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = ""
    version: str = ""
    checksum: str = ""
    s3_uri: str = ""
    row_count: int | None = None
    schema_json: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    created_by: str = ""
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
