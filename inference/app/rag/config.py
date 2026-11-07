"""RAG configuration.

Loaded from `config/inference.yaml` under the `rag:` key, with
`RAG_`-prefixed environment variables overriding YAML values.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


CONFIG_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "config"
    / "inference.yaml"
)


class EmbeddingConfig(BaseModel):
    """Embedding provider configuration."""

    provider: str
    model: str
    dimensions: int = 1536
    base_url: str | None = None
    api_key: str | None = None


class VectorStoreConfig(BaseModel):
    """Vector store (pgvector) configuration."""

    database_url: str
    table_name: str = "rag_documents"
    embedding_dimensions: int = 1536
    distance_metric: Literal["cosine", "l2", "ip"] = "cosine"

    @field_validator("distance_metric")
    @classmethod
    def validate_distance_metric(cls, value: str) -> str:
        allowed = {"cosine", "l2", "ip"}
        if value not in allowed:
            raise ValueError(
                f"distance_metric must be one of {sorted(allowed)}, "
                f"got {value!r}"
            )
        return value


class RetrievalConfig(BaseModel):
    """Retrieval configuration."""

    top_k: int = 10
    hybrid_top_k: int = 50
    semantic_weight: float = 0.7
    keyword_weight: float = 0.3
    min_score: float = 0.0
    max_chunks_per_document: int = 5
    rerank: bool = False


class GenerationConfig(BaseModel):
    """Generation (context injection) configuration."""

    model: str
    system_prompt: str = (
        "You are a helpful assistant. Answer the user's question using "
        "only the provided context. If the answer cannot be determined "
        "from the context, say so. Cite sources using [Source N] "
        "notation where N corresponds to the source index."
    )
    max_context_chars: int = 12_000
    temperature: float = 0.2
    max_tokens: int = 1_000


class ChunkingConfig(BaseModel):
    """Document chunking configuration."""

    chunk_size: int = 1_000
    chunk_overlap: int = 200
    separators: list[str] = Field(
        default_factory=lambda: [
            "\n\n",
            "\n",
            ". ",
            "? ",
            "! ",
            "; ",
            ", ",
            " ",
        ]
    )

    @field_validator("chunk_overlap")
    @classmethod
    def validate_overlap(
        cls, value: int, info: ValidationInfo
    ) -> int:
        """chunk_overlap must be >= 0 and < chunk_size."""

        if value < 0:
            raise ValueError("chunk_overlap must be >= 0")

        chunk_size = info.data.get("chunk_size")
        if chunk_size is not None and value >= chunk_size:
            raise ValueError(
                "chunk_overlap must be < chunk_size"
            )

        return value


class RagConfig(BaseModel):
    """Top-level RAG configuration."""

    enabled: bool = True
    embedding: EmbeddingConfig
    vector_store: VectorStoreConfig
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    generation: GenerationConfig
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)

    @model_validator(mode="after")
    def validate_cross_fields(self) -> "RagConfig":
        """Validate cross-field relationships within RagConfig."""

        if (
            self.embedding.dimensions
            != self.vector_store.embedding_dimensions
        ):
            raise ValueError(
                "Embedding dimensions "
                f"({self.embedding.dimensions}) must match "
                "vector store embedding dimensions "
                f"({self.vector_store.embedding_dimensions})"
            )

        total_weight = (
            self.retrieval.semantic_weight
            + self.retrieval.keyword_weight
        )
        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(
                "semantic_weight + keyword_weight must equal 1.0"
            )

        return self


class RagSettings(BaseModel):
    """RAG application settings."""

    app_name: str = "agenyx-rag"
    app_version: str = "0.1.0"

    rag: RagConfig

    model_config = {
        "env_prefix": "RAG_",
        "env_nested_delimiter": "__",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache
def get_rag_settings() -> RagSettings:
    """Return cached RAG settings loaded from YAML + environment."""

    import yaml

    with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    rag_raw = raw.get("rag", {})

    # Allow environment variable overrides for nested fields.
    # e.g. RAG__VECTOR_STORE__DATABASE_URL=postgres://...
    env_overrides: dict = {}
    for key, value in os.environ.items():
        if not key.startswith("RAG__"):
            continue
        parts = key[len("RAG__") :].lower().split("__")
        target = env_overrides
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value

    def deep_merge(base: dict, override: dict) -> dict:
        result = dict(base)
        for k, v in override.items():
            if (
                k in result
                and isinstance(result[k], dict)
                and isinstance(v, dict)
            ):
                result[k] = deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    merged = deep_merge(rag_raw, env_overrides)

    return RagSettings(rag=RagConfig(**merged))
