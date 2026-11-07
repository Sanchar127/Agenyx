"""Unit tests for document upload (RAG ingestion) endpoint."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.documents import create_document_router


def create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(
        create_document_router(
            valkey_url="redis://localhost:6379/0",
            task_stream="agenyx:tasks",
            consumer_group="agenyx-workers",
        )
    )
    return app


@patch("app.api.documents.valkey.from_url")
def test_upload_document_queues_ingestion(mock_from_url):
    """Uploading a document queues an ingestion task and returns document_id."""

    os.environ["AGENTYX_INFERENCE_SERVICE_API_KEY"] = "test-key"

    mock_client = MagicMock()
    mock_from_url.return_value = mock_client

    app = create_test_app()

    with TestClient(app) as client:
        response = client.post(
            "/v1/documents/upload",
            json={
                "content": "Agenyx is a runtime for building AI agents.",
                "content_type": "text/plain",
                "metadata": {"source": "upload.pdf"},
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "document_id" in data
    assert "execution_id" in data
    assert data["status"] == "queued"

    # Verify Valkey xadd was called.
    assert mock_client.xadd.called
    call_args = mock_client.xadd.call_args
    assert call_args[0][0] == "agenyx:tasks"  # stream name

    payload = json.loads(call_args[0][1]["payload"])
    assert payload["document_id"] == data["document_id"]
    assert payload["execution_id"] == data["execution_id"]
    assert payload["intent"] == "document.ingest"
    assert "Agenyx is a runtime" in payload["content"]

    del os.environ["AGENTYX_INFERENCE_SERVICE_API_KEY"]


@patch("app.api.documents.valkey.from_url")
def test_upload_document_rejects_empty_content(mock_from_url):
    """Empty content returns 422 (Pydantic validation)."""

    os.environ["AGENTYX_INFERENCE_SERVICE_API_KEY"] = "test-key"

    app = create_test_app()

    with TestClient(app) as client:
        response = client.post(
            "/v1/documents/upload",
            json={
                "content": "",
                "content_type": "text/plain",
            },
        )

    assert response.status_code == 422

    del os.environ["AGENTYX_INFERENCE_SERVICE_API_KEY"]


@patch("app.api.documents.valkey.from_url")
def test_upload_document_generates_deterministic_id(mock_from_url):
    """Same content produces the same document_id when no custom ID given."""

    os.environ["AGENTYX_INFERENCE_SERVICE_API_KEY"] = "test-key"

    mock_client = MagicMock()
    mock_from_url.return_value = mock_client

    app = create_test_app()

    with TestClient(app) as client:
        r1 = client.post(
            "/v1/documents/upload",
            json={"content": "Same document content here."},
        )
        r2 = client.post(
            "/v1/documents/upload",
            json={"content": "Same document content here."},
        )

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert (
        r1.json()["document_id"] == r2.json()["document_id"]
    ), "Same content should yield same document_id"

    del os.environ["AGENTYX_INFERENCE_SERVICE_API_KEY"]


@patch("app.api.documents.valkey.from_url")
def test_upload_document_uses_custom_document_id(mock_from_url):
    """Custom document_id from metadata is respected."""

    os.environ["AGENTYX_INFERENCE_SERVICE_API_KEY"] = "test-key"

    mock_client = MagicMock()
    mock_from_url.return_value = mock_client

    app = create_test_app()

    with TestClient(app) as client:
        response = client.post(
            "/v1/documents/upload",
            json={
                "content": "Custom ID document.",
                "metadata": {"document_id": "custom-doc-123"},
            },
        )

    assert response.status_code == 200
    assert response.json()["document_id"] == "custom-doc-123"

    payload = json.loads(mock_client.xadd.call_args[0][1]["payload"])
    assert payload["document_id"] == "custom-doc-123"

    del os.environ["AGENTYX_INFERENCE_SERVICE_API_KEY"]
