"""Integration tests for the RAG API.

Mocks the vector store and embedding client so tests run without a
real PostgreSQL or embedding provider.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Agenyx-Service-Key": "test-service-key"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_rag_chat_returns_answer(client):
    """POST /v1/rag/chat returns answer, sources, and timing."""

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

    mock_service = MagicMock()
    mock_service.answer = AsyncMock(return_value=mock_answer)

    with patch("app.rag.router_state.rag_service", mock_service):
        response = await client.post(
            "/v1/rag/chat",
            json={"query": "What is Agenyx?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "Agenyx is an AI agent runtime."
        assert data["model"] == "qwen2.5:7b"
        assert len(data["sources"]) == 1
        assert "timing_ms" in data


@pytest.mark.asyncio
async def test_rag_chat_rejects_empty_query(client):
    """Empty query returns 400 (validation runs before service check)."""

    response = await client.post(
        "/v1/rag/chat",
        json={"query": ""},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_QUERY"


@pytest.mark.asyncio
async def test_rag_chat_missing_query(client):
    """Missing query returns 400 (validation runs before service check)."""

    response = await client.post(
        "/v1/rag/chat",
        json={},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_QUERY"


@pytest.mark.asyncio
async def test_rag_search_returns_chunks(client):
    """POST /v1/rag/search returns retrieved chunks."""

    mock_chunks = [
        {
            "id": 1,
            "document_id": "doc-1",
            "chunk_index": 0,
            "content": "Agenyx is a runtime.",
            "score": 0.95,
            "search_type": "semantic",
            "metadata": {},
        }
    ]

    mock_service = MagicMock()
    mock_service._embedding.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
    mock_service._retriever.retrieve = AsyncMock(return_value=mock_chunks)

    with patch("app.rag.router_state.rag_service", mock_service):
        response = await client.post(
            "/v1/rag/search",
            json={"query": "What is Agenyx?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["chunks"][0]["content"] == "Agenyx is a runtime."


@pytest.mark.asyncio
async def test_rag_health(client):
    """GET /v1/rag/health returns dependency status."""

    mock_service = MagicMock()
    mock_service.health = AsyncMock(
        return_value={
            "status": "healthy",
            "embedding": True,
            "vector_store": True,
        }
    )

    with patch("app.rag.router_state.rag_service", mock_service):
        response = await client.get("/v1/rag/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["embedding"] is True


@pytest.mark.asyncio
async def test_rag_upsert_documents(client):
    """POST /v1/rag/documents/upsert accepts chunks."""

    mock_service = MagicMock()
    mock_service._store.upsert_chunks = AsyncMock(return_value=[1, 2])

    with patch("app.rag.router_state.rag_service", mock_service):
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
                    {
                        "chunk_index": 1,
                        "content": "chunk two",
                        "embedding": [0.3, 0.4],
                        "metadata": {},
                    },
                ],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chunks_upserted"] == 2
        assert data["document_id"] == "doc-1"


@pytest.mark.asyncio
async def test_rag_embeddings(client):
    """POST /v1/rag/embeddings returns vectors."""

    mock_service = MagicMock()
    mock_service._embedding.embed_batch = AsyncMock(
        return_value=[[0.1, 0.2], [0.3, 0.4]]
    )

    with patch("app.rag.router_state.rag_service", mock_service):
        response = await client.post(
            "/v1/rag/embeddings",
            json={"input": ["hello", "world"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert len(data["data"]) == 2
        assert data["data"][0]["index"] == 0
        assert data["data"][0]["embedding"] == [0.1, 0.2]
