"""Document upload routes for RAG ingestion.

Client-facing endpoint: authenticated users upload documents, which are
queued as ingestion tasks for the worker to chunk, embed, and upsert
into the pgvector store.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import valkey
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import get_settings


class DocumentUploadRequest(BaseModel):
    """Request to upload a document for RAG ingestion."""

    content: str = Field(..., min_length=1, description="Document text content")
    content_type: str = Field(
        default="text/plain",
        description="MIME type of the document content",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata attached to the document",
    )


class DocumentUploadResponse(BaseModel):
    """Response returned after a document upload is accepted."""

    document_id: str
    execution_id: str
    status: str = "queued"
    message: str


def create_document_router(
    valkey_url: str,
    task_stream: str = "agenyx:tasks",
    consumer_group: str = "agenyx-workers",
) -> APIRouter:
    """Create the document upload router.

    The router lazily connects to Valkey on first request so the agent
    service can start without Valkey being available.
    """

    router = APIRouter(prefix="/v1/documents", tags=["documents"])

    _valkey_client: valkey.Valkey | None = None

    def _client() -> valkey.Valkey:
        nonlocal _valkey_client
        if _valkey_client is None:
            _valkey_client = valkey.from_url(
                valkey_url,
                decode_responses=True,
            )
        return _valkey_client

    settings = get_settings()

    @router.post(
        "/upload",
        response_model=DocumentUploadResponse,
    )
    async def upload_document(
        request: DocumentUploadRequest,
    ) -> DocumentUploadResponse:
        """Upload a document for RAG ingestion.

        The document is queued as an ingestion task. The worker will
        chunk, embed, and upsert it to the vector store.
        """

        document_id = str(
            request.metadata.get("document_id")
            or hashlib.sha256(
                request.content.encode("utf-8")
            ).hexdigest()[:32]
        )
        execution_id = str(uuid.uuid4())

        payload: dict[str, Any] = {
            "execution_id": execution_id,
            "intent": "document.ingest",
            "document_id": document_id,
            "content": request.content,
            "content_type": request.content_type,
            "metadata": request.metadata,
        }

        try:
            client = _client()
            client.xadd(
                task_stream,
                {
                    "execution_id": execution_id,
                    "intent": "document.ingest",
                    "document_id": document_id,
                    "content": request.content,
                    "content_type": request.content_type,
                    "metadata": json.dumps(request.metadata),
                },
            )
        except Exception as exc:  # pragma: no cover - infrastructure
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "INGESTION_QUEUE_FAILED",
                    "message": f"Failed to queue ingestion task: {exc}",
                },
            ) from exc

        return DocumentUploadResponse(
            document_id=document_id,
            execution_id=execution_id,
            message=(
                f"Document '{document_id}' queued for ingestion "
                f"({execution_id})"
            ),
        )

    return router
