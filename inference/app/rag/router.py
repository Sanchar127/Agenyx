"""FastAPI routes for the RAG pipeline.

Endpoints:

- ``POST /v1/rag/chat`` — retrieval-augmented generation
- ``POST /v1/rag/search`` — hybrid retrieval only (no generation)
- ``POST /v1/rag/embeddings`` — embed one or more texts
- ``POST /v1/rag/documents/upsert`` — upsert document chunks to vector store
- ``GET /v1/rag/health`` — RAG dependency health

Input validation always runs before the RAG service availability check,
so malformed requests return ``400`` even when RAG is not initialized.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import require_service_auth
from app.logger import logger
from app.metrics import RAG_REQUESTS_TOTAL, RAG_REQUEST_DURATION_SECONDS
from app.rag.config import get_rag_settings
from app.rag.embedding import EmbeddingError
from app.rag.router_state import require_rag_service
from app.rag.service import RagError, RagService

router = APIRouter(prefix="/v1/rag", tags=["rag"])


def _error(*, status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


@router.post("/chat")
async def rag_chat(
    request: Request,
    _: None = Depends(require_service_auth),
) -> dict[str, Any]:
    """Retrieval-augmented generation.

    Request body:

        {
            "query": "What is Agenyx?",
            "document_id": "optional-doc-id",
            "model": "qwen2.5:7b"
        }
    """

    # Validate input before checking RAG service availability so
    # malformed requests return 400 even when RAG is not initialized.
    start = time.perf_counter()

    try:
        body = await request.json()
    except Exception:
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_JSON",
            message="Invalid JSON request",
        )

    if not isinstance(body, dict):
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_REQUEST_BODY",
            message="Request body must be a JSON object",
        )

    query = body.get("query")
    if not isinstance(query, str) or not query.strip():
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_QUERY",
            message="Field 'query' must be a non-empty string",
        )

    document_id = body.get("document_id")
    if document_id is not None and not isinstance(document_id, str):
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_DOCUMENT_ID",
            message="Field 'document_id' must be a string",
        )

    model = body.get("model")
    if model is not None and not isinstance(model, str):
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_MODEL",
            message="Field 'model' must be a string",
        )

    service: RagService = require_rag_service()

    try:
        result = await service.answer(
            query=query.strip(),
            document_id=document_id,
            model=model,
        )
    except RagError as exc:
        logger.warning(
            "RAG chat failed",
            extra={
                "query_length": len(query),
                "error": str(exc),
            },
        )
        raise _error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="RAG_FAILED",
            message=str(exc),
        ) from exc

    duration = time.perf_counter() - start
    RAG_REQUESTS_TOTAL.labels(
        endpoint="chat",
        status="success",
    ).inc()
    RAG_REQUEST_DURATION_SECONDS.labels(endpoint="chat").observe(duration)

    return result


@router.post("/search")
async def rag_search(
    request: Request,
    _: None = Depends(require_service_auth),
) -> dict[str, Any]:
    """Hybrid retrieval only (no LLM generation)."""

    # Validate input before checking RAG service availability.
    start = time.perf_counter()

    try:
        body = await request.json()
    except Exception:
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_JSON",
            message="Invalid JSON request",
        )

    if not isinstance(body, dict):
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_REQUEST_BODY",
            message="Request body must be a JSON object",
        )

    query = body.get("query")
    if not isinstance(query, str) or not query.strip():
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_QUERY",
            message="Field 'query' must be a non-empty string",
        )

    document_id = body.get("document_id")
    if document_id is not None and not isinstance(document_id, str):
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_DOCUMENT_ID",
            message="Field 'document_id' must be a string",
        )

    service: RagService = require_rag_service()

    try:
        embedding = service._embedding  # type: ignore[attr-defined]
        query_embedding = await embedding.embed(query.strip())

        chunks = await service._retriever.retrieve(  # type: ignore[attr-defined]
            query=query.strip(),
            query_embedding=query_embedding,
            document_id=document_id,
        )
    except EmbeddingError as exc:
        raise _error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="EMBEDDING_FAILED",
            message=str(exc),
        ) from exc
    except Exception as exc:
        logger.warning(
            "RAG search failed",
            extra={
                "query_length": len(query),
                "error": str(exc),
            },
        )
        raise _error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="RETRIEVAL_FAILED",
            message=str(exc),
        ) from exc

    duration = time.perf_counter() - start
    RAG_REQUESTS_TOTAL.labels(
        endpoint="search",
        status="success",
    ).inc()
    RAG_REQUEST_DURATION_SECONDS.labels(endpoint="search").observe(duration)

    return {
        "query": query.strip(),
        "chunks": chunks,
        "count": len(chunks),
    }


@router.post("/documents/upsert")
async def rag_upsert_documents(
    request: Request,
    _: None = Depends(require_service_auth),
) -> dict[str, Any]:
    """Upsert document chunks to the vector store.

    Used by the worker ingestion pipeline.
    """

    # Validate input before checking RAG service availability.
    start = time.perf_counter()

    try:
        body = await request.json()
    except Exception:
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_JSON",
            message="Invalid JSON request",
        )

    if not isinstance(body, dict):
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_REQUEST_BODY",
            message="Request body must be a JSON object",
        )

    document_id = body.get("document_id")
    if not isinstance(document_id, str) or not document_id.strip():
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_DOCUMENT_ID",
            message="Field 'document_id' must be a non-empty string",
        )

    chunks = body.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_CHUNKS",
            message="Field 'chunks' must be a non-empty list",
        )

    # Validate each chunk.
    for idx, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise _error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="INVALID_CHUNK",
                message=f"Chunk at index {idx} must be a JSON object",
            )
        if "content" not in chunk or not isinstance(chunk["content"], str):
            raise _error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="INVALID_CHUNK_CONTENT",
                message=f"Chunk at index {idx} must have string 'content'",
            )
        if "embedding" not in chunk or not isinstance(
            chunk["embedding"], list
        ):
            raise _error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="INVALID_CHUNK_EMBEDDING",
                message=f"Chunk at index {idx} must have list 'embedding'",
            )
        if "chunk_index" not in chunk or not isinstance(
            chunk["chunk_index"], int
        ):
            raise _error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="INVALID_CHUNK_INDEX",
                message=f"Chunk at index {idx} must have int 'chunk_index'",
            )

    service: RagService = require_rag_service()

    try:
        await service._store.upsert_chunks(  # type: ignore[attr-defined]
            document_id=document_id.strip(),
            chunks=[
                {
                    "chunk_index": int(c["chunk_index"]),
                    "content": str(c["content"]),
                    "embedding": [float(v) for v in c["embedding"]],
                    "metadata": c.get("metadata", {}),
                }
                for c in chunks
            ],
        )
    except Exception as exc:
        logger.warning(
            "RAG document upsert failed",
            extra={
                "document_id": document_id,
                "chunk_count": len(chunks),
                "error": str(exc),
            },
        )
        raise _error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="UPSCERT_FAILED",
            message=str(exc),
        ) from exc

    duration = time.perf_counter() - start
    RAG_REQUESTS_TOTAL.labels(
        endpoint="upsert",
        status="success",
    ).inc()
    RAG_REQUEST_DURATION_SECONDS.labels(endpoint="upsert").observe(duration)

    return {
        "document_id": document_id.strip(),
        "chunks_upserted": len(chunks),
    }


@router.post("/embeddings")
async def rag_embeddings(
    request: Request,
    _: None = Depends(require_service_auth),
) -> dict[str, Any]:
    """Embed one or more texts.

    Used by the worker ingestion pipeline.
    """

    # Validate input before checking RAG service availability.
    start = time.perf_counter()

    try:
        body = await request.json()
    except Exception:
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_JSON",
            message="Invalid JSON request",
        )

    if not isinstance(body, dict):
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_REQUEST_BODY",
            message="Request body must be a JSON object",
        )

    inputs = body.get("input")
    if isinstance(inputs, str):
        inputs = [inputs]

    if not isinstance(inputs, list) or not inputs:
        raise _error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_INPUT",
            message="Field 'input' must be a non-empty string or list",
        )

    for idx, item in enumerate(inputs):
        if not isinstance(item, str):
            raise _error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="INVALID_INPUT_ITEM",
                message=f"Input at index {idx} must be a string",
            )

    service: RagService = require_rag_service()

    try:
        vectors = await service._embedding.embed_batch(  # type: ignore[attr-defined]
            [str(i) for i in inputs]
        )
    except EmbeddingError as exc:
        raise _error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="EMBEDDING_FAILED",
            message=str(exc),
        ) from exc

    duration = time.perf_counter() - start
    RAG_REQUESTS_TOTAL.labels(
        endpoint="embeddings",
        status="success",
    ).inc()
    RAG_REQUEST_DURATION_SECONDS.labels(endpoint="embeddings").observe(duration)

    return {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "index": idx,
                "embedding": vector,
            }
            for idx, vector in enumerate(vectors)
        ],
    }


@router.get("/health")
async def rag_health() -> dict[str, Any]:
    """RAG dependency health check.

    Returns 503 if the RAG service is not initialized.
    """

    service = require_rag_service()

    health = await service.health()
    http_status = (
        status.HTTP_200_OK
        if health["status"] == "healthy"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return {
        "status": health["status"],
        "embedding": health["embedding"],
        "vector_store": health["vector_store"],
    }
