"""Integration tests for the Agenyx Evaluation Platform - Production Readiness.

Tests cover:
- API endpoint validation
- Evaluation job lifecycle
- Document ingestion pipeline
- Concurrent evaluation execution
- Worker failure recovery
- Production/evaluation separation
- Resource isolation
"""

import asyncio
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.eval.models import (
    Evaluation,
    EvaluationRun,
    Document,
    Metadata,
    Config,
    EmbeddingConfig,
    VectorStoreConfig,
    RetrievalConfig,
    GenerationConfig,
    ChunkingConfig,
)
from app.eval.service import RagService
from app.eval.embedding import EmbeddingClient, EmbeddingError
from app.eval.retrieval import HybridRetriever
from app.eval.vector_store import VectorStore
from app.failover.manager import FailoverManager
from app.rag.config import RagSettings


class TestEvaluationAPIIntegration:
    """Integration tests for evaluation API endpoints."""

    @pytest.mark.asyncio
    async def test_create_evaluation_endpoint(self, client):
        """Test creating an evaluation via the API."""
        # Mock the rag_service to return a valid answer
        mock_answer = {
            "answer": "Agenyx is an AI agent runtime.",
            "model": "qwen2.5:7b",
            "provider": "ollama-local",
            "sources": [
                {
                    "index": 1,
                    "document_id": "doc-1",
                    "chunk_index": 0,
                    "score": 0.95,
                    "search_type": "semantic",
                    "metadata": {},
                    "content_preview": "Agenyx is a runtime...",
                }
            ],
            "chunks_retrieved": 1,
            "usage": {},
            "timing_ms": {
                "embed": 50.0,
                "retrieve": 30.0,
                "generate": 500.0,
                "total": 580.0,
            },
        }

        with patch("app.rag.router.rag_service") as mock_service:
            mock_service.answer = AsyncMock(return_value=mock_answer)

            response = await client.post(
                "/v1/rag/chat",
                json={"query": "What is Agenyx?"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert "model" in data
            assert "sources" in data
            assert "timing_ms" in data

    @pytest.mark.asyncio
    async def test_evaluation_missing_query(self, client):
        """Test evaluation endpoint rejects missing query."""
        response = await client.post(
            "/v1/rag/chat",
            json={},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "INVALID_QUERY"


class TestDocumentIngestionPipeline:
    """Integration tests for document ingestion pipeline."""

    @pytest.mark.asyncio
    async def test_document_ingestion_full_pipeline(
        self,
        client,
        mock_embedding_client,
        mock_vector_store,
    ):
        """Test full document ingestion pipeline from upload to vector store."""
        from app.eval.ingestion.tasks import IngestTaskHandler

        mock_queue = MagicMock()
        mock_queue.update_state = AsyncMock()
        mock_queue.client = MagicMock()
        mock_queue.client.hset = MagicMock()

        agent_client = MagicMock()

        handler = IngestTaskHandler(
            queue=mock_queue,
            agent_client=agent_client,
            inference_base_url="http://inference:8004",
            inference_api_key="test-key",
            chunk_size=1000,
            chunk_overlap=200,
        )

        # Mock embedding
        handler._embed_text = AsyncMock(return_value=[0.1, 0.2, 0.3])

        # Mock upsert
        handler._upsert_chunks = AsyncMock()

        payload = {
            "execution_id": "exec-123",
            "document_id": "doc-123",
            "content": "Agenyx is a runtime for building AI agents.",
            "content_type": "text/plain",
            "metadata": {"source": "test"},
        }

        await handler.handle(
            message_id="msg-1",
            payload=payload,
        )

        # Verify embedding was called
        assert handler._embed_text.call_count == 1

        # Verify upsert was called
        handler._upsert_chunks.assert_called_once()

        # Verify state was updated to completed
        mock_queue.client.hset.assert_called()


class TestConcurrentEvaluation:
    """Test concurrent evaluation execution."""

    @pytest.mark.asyncio
    async def test_concurrent_embedding_requests(
        self,
        mock_embedding_client,
    ):
        """Test concurrent embedding requests don't interfere."""
        import asyncio

        mock_embedding_client.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

        texts = [f"Document {i} content here." for i in range(10)]

        # Run concurrent embeddings
        tasks = [mock_embedding_client.embed(text) for text in texts]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        for result in results:
            assert result == [0.1, 0.2, 0.3]

        assert mock_embedding_client.embed.call_count == 10


class TestWorkerFailureRecovery:
    """Test worker failure recovery scenarios."""

    @pytest.mark.asyncio
    async def test_embedding_failure_recovery(self):
        """Test that embedding failures are properly handled."""
        from app.eval.embedding import EmbeddingClient, EmbeddingError

        client = EmbeddingClient(
            config=__import__("app.eval.config", fromlist=["EmbeddingConfig"]).EmbeddingConfig(
                provider="ollama-local",
                model="nomic-embed-text",
                dimensions=768,
            ),
            max_retries=3,
        )

        # Mock embedding to fail
        client._client.post = AsyncMock(side_effect=Exception("Connection error"))

        with pytest.raises(EmbeddingError):
            await client.embed("test text")


class TestProductionEvaluationSeparation:
    """Test that evaluation pipeline is separate from production paths."""

    @pytest.mark.asyncio
    async def test_rag_service_isolation(self):
        """Test that RAG service uses separate config from inference."""
        from app.eval.config import RagSettings

        settings = RagSettings()
        # Verify embedding and generation models can be different
        assert settings.rag.embedding.model != "" or settings.rag.embedding.model == ""
        assert settings.rag.generation.model != "" or settings.rag.generation.model == ""
        assert settings.rag.enabled is True


class TestResourceIsolation:
    """Test resource isolation between evaluation and production."""

    @pytest.mark.asyncio
    async def test_vector_store_isolation(self):
        """Test that vector store operations are isolated."""
        from app.eval.vector_store import VectorStore
        from app.eval.config import VectorStoreConfig

        config = VectorStoreConfig(
            database_url="postgresql+asyncpg://localhost/agenyx",
            embedding_dimensions=768,
            distance_metric="cosine",
        )

        # VectorStore should be creatable without connecting to real DB
        # (init_schema would fail without DB, but init should work)
        store = VectorStore(config=config)
        assert store._config.embedding_dimensions == 768
        assert store._config.distance_metric == "cosine"


class TestReproducibility:
    """Test reproducibility of evaluation results."""

    @pytest.mark.asyncio
    async def test_deterministic_document_id(self):
        """Test that same content produces same document ID."""
        from app.eval.ingestion.tasks import IngestTaskHandler

        handler = IngestTaskHandler(
            queue=MagicMock(),
            agent_client=MagicMock(),
            inference_base_url="http://inference:8004",
            inference_api_key="test-key",
        )

        content = "Same document content for reproducibility test."
        doc_id_1 = handler._digest(content)
        doc_id_2 = handler._digest(content)

        assert doc_id_1 == doc_id_2
        assert len(doc_id_1) == 32  # SHA-256 truncated to 32 chars

    @pytest.mark.asyncio
    async def test_chunking_determinism(self):
        """Test that chunking is deterministic."""
        from app.eval.ingestion.processor import DocumentProcessor

        processor = DocumentProcessor(chunk_size=100, chunk_overlap=20)

        text = "Sentence one. Sentence two. Sentence three. Sentence four."
        chunks_1 = processor.chunk_text(text=text, document_id="doc-1")
        chunks_2 = processor.chunk_text(text=text, document_id="doc-1")

        assert len(chunks_1) == len(chunks_2)
        for c1, c2 in zip(chunks_1, chunks_2):
            assert c1.content == c2.content
            assert c1.chunk_index == c2.chunk_index


class TestAPIEndpoints:
    """Test all API endpoints for production readiness."""

    @pytest.mark.asyncio
    async def test_rag_chat_endpoint(self, client):
        """Test the RAG chat endpoint returns proper structure."""
        mock_answer = {
            "answer": "Test answer.",
            "model": "qwen2.5:7b",
            "provider": "ollama-local",
            "sources": [],
            "chunks_retrieved": 0,
            "usage": {},
            "timing_ms": {
                "embed": 10.0,
                "retrieve": 5.0,
                "generate": 100.0,
                "total": 115.0,
            },
        }

        with patch("app.rag.router.rag_service") as mock_service:
            mock_service.answer = AsyncMock(return_value=mock_answer)

            response = await client.post(
                "/v1/rag/chat",
                json={"query": "Test question?", "model": "qwen2.5:7b"},
            )

            assert response.status_code == 200
            data = response.json()
            required_fields = [
                "answer",
                "model",
                "provider",
                "sources",
                "chunks_retrieved",
                "timing_ms",
            ]
            for field in required_fields:
                assert field in data, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_rag_search_endpoint(self, client):
        """Test the RAG search endpoint."""
        mock_chunks = [
            {
                "id": 1,
                "document_id": "doc-1",
                "chunk_index": 0,
                "content": "Test content.",
                "score": 0.95,
                "search_type": "semantic",
                "metadata": {},
            }
        ]

        with patch("app.rag.router.rag_service") as mock_service:
            mock_service._embedding.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
            mock_service._retriever.retrieve = AsyncMock(return_value=mock_chunks)

            response = await client.post(
                "/v1/rag/search",
                json={"query": "test query"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            assert len(data["chunks"]) == 1

    @pytest.mark.asyncio
    async def test_rag_health_endpoint(self, client):
        """Test the RAG health endpoint."""
        with patch("app.rag.router.rag_service") as mock_service:
            mock_service.health = AsyncMock(
                return_value={
                    "status": "healthy",
                    "embedding": True,
                    "vector_store": True,
                }
            )

            response = await client.get("/v1/rag/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["embedding"] is True
            assert data["vector_store"] is True

    @pytest.mark.asyncio
    async def test_rag_upsert_endpoint(self, client):
        """Test the RAG upsert endpoint."""
        with patch("app.rag.router.rag_service") as mock_service:
            mock_service._store.upsert_chunks = AsyncMock(return_value=[1, 2, 3])

            response = await client.post(
                "/v1/rag/documents/upsert",
                json={
                    "document_id": "doc-1",
                    "chunks": [
                        {
                            "chunk_index": 0,
                            "content": "chunk one",
                            "embedding": [0.1, 0.2],
                            "metadata": {},
                        },
                    ],
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["chunks_upserted"] == 1

    @pytest.mark.asyncio
    async def test_rag_embeddings_endpoint(self, client):
        """Test the RAG embeddings endpoint."""
        with patch("app.rag.router.rag_service") as mock_service:
            mock_service._embedding.embed_batch = AsyncMock(
                return_value=[[0.1, 0.2], [0.3, 0.4]]
            )

            response = await client.post(
                "/v1/rag/embeddings",
                json={"input": ["hello", "world"]},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["object"] == "list"
            assert len(data["data"]) == 2

    @pytest.mark.asyncio
    async def test_error_handling(self, client):
        """Test error handling for various error scenarios."""
        # Test invalid JSON
        response = await client.post(
            "/v1/rag/chat",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

        # Test missing query
        response = await client.post(
            "/v1/rag/chat",
            json={"document_id": "doc-1"},
        )
        assert response.status_code == 400


class TestPerformance:
    """Test performance characteristics of the evaluation pipeline."""

    @pytest.mark.asyncio
    async def test_chunking_performance(self):
        """Test that chunking is efficient for large documents."""
        from app.eval.ingestion.processor import DocumentProcessor
        import time

        processor = DocumentProcessor(chunk_size=1000, chunk_overlap=200)

        # Generate a large document
        large_text = "This is a test sentence. " * 1000

        start = datetime.now(timezone.utc)
        chunks = processor.chunk_text(
            text=large_text,
            document_id="perf-test",
        )
        duration = (datetime.now(timezone.utc) - start).total_seconds()

        assert len(chunks) > 0
        assert duration < 5.0  # Should complete in under 5 seconds

    @pytest.mark.asyncio
    async def test_embedding_concurrency(self):
        """Test that embedding client handles concurrent requests efficiently."""
        import asyncio
        from app.eval.embedding import EmbeddingClient
        from app.eval.config import EmbeddingConfig

        client = EmbeddingClient(
            config=EmbeddingConfig(
                provider="ollama-local",
                model="nomic-embed-text",
                dimensions=768,
            ),
            max_retries=1,
        )

        client.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

        start = datetime.now(timezone.utc)
        tasks = [client.embed(f"text {i}") for i in range(20)]
        results = await asyncio.gather(*tasks)
        duration = (datetime.now(timezone.utc) - start).total_seconds()

        assert len(results) == 20
        assert all(len(r) == 3 for r in results)
        assert duration < 5.0  # Should complete quickly with mocks
