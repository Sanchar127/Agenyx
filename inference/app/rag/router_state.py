"""RAG router state.

Holds the module-level RAG service singleton and a dependency that
returns it (or raises 503 if not initialized). This avoids circular
imports between ``router.py`` and ``bootstrap.py``.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.rag.service import RagService

rag_service: RagService | None = None


def set_rag_service(service: RagService) -> None:
    """Store the initialized RAG service."""

    global rag_service
    rag_service = service


def require_rag_service() -> RagService:
    """Return the RAG service, or raise 503 if not initialized."""

    if rag_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "RAG_NOT_INITIALIZED",
                "message": "RAG service is not initialized.",
            },
        )
    return rag_service
