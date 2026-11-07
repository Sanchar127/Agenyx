"""Unit tests for RAG configuration."""

import pytest
from pydantic import ValidationError

from app.rag.config import (
    ChunkingConfig,
    EmbeddingConfig,
    GenerationConfig,
    RagConfig,
    RetrievalConfig,
    VectorStoreConfig,
    get_rag_settings,
)


def test_rag_config_defaults():
    """RAG config loads with sensible defaults."""

    config = RagConfig(
        embedding=EmbeddingConfig(
            provider="ollama-local",
            model="nomic-embed-text",
            dimensions=768,
        ),
        vector_store=VectorStoreConfig(
            database_url="postgresql+asyncpg://localhost/agenyx",
            embedding_dimensions=768,
        ),
        generation=GenerationConfig(model="qwen2.5:7b"),
    )

    assert config.retrieval.top_k == 10
    assert config.retrieval.semantic_weight == 0.7
    assert config.retrieval.keyword_weight == 0.3
    assert config.chunking.chunk_size == 1000
    assert config.chunking.chunk_overlap == 200
    assert config.generation.max_context_chars == 12_000


def test_rag_config_dimensions_must_match():
    """Embedding dimensions must match vector store dimensions."""

    with pytest.raises(
        ValueError, match="Embedding dimensions.*must match"
    ):
        RagConfig(
            embedding=EmbeddingConfig(
                provider="ollama-local",
                model="nomic-embed-text",
                dimensions=768,
            ),
            vector_store=VectorStoreConfig(
                database_url="postgresql+asyncpg://localhost/agenyx",
                embedding_dimensions=1536,
            ),
            generation=GenerationConfig(model="qwen2.5:7b"),
        )


def test_rag_config_weights_must_sum_to_one():
    """semantic_weight + keyword_weight must equal 1.0."""

    with pytest.raises(ValueError, match="must equal 1.0"):
        RagConfig(
            embedding=EmbeddingConfig(
                provider="ollama-local",
                model="nomic-embed-text",
                dimensions=768,
            ),
            vector_store=VectorStoreConfig(
                database_url="postgresql+asyncpg://localhost/agenyx",
                embedding_dimensions=768,
            ),
            retrieval=RetrievalConfig(
                semantic_weight=0.8,
                keyword_weight=0.5,
            ),
            generation=GenerationConfig(model="qwen2.5:7b"),
        )


def test_rag_config_invalid_distance_metric():
    """Invalid distance metric raises ValidationError."""

    with pytest.raises(ValidationError):
        VectorStoreConfig(
            database_url="postgresql+asyncpg://localhost/agenyx",
            embedding_dimensions=768,
            distance_metric="invalid",
        )


def test_chunking_invalid_overlap():
    """chunk_overlap must be < chunk_size."""

    with pytest.raises(ValueError, match="chunk_overlap must be < chunk_size"):
        ChunkingConfig(chunk_size=100, chunk_overlap=100)


def test_chunking_negative_overlap():
    """Negative chunk_overlap is rejected."""

    with pytest.raises(ValueError, match="chunk_overlap must be >= 0"):
        ChunkingConfig(chunk_size=100, chunk_overlap=-1)


def test_get_rag_settings_is_cached():
    """get_rag_settings returns a cached instance."""

    s1 = get_rag_settings()
    s2 = get_rag_settings()
    assert s1 is s2
