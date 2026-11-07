"""RAG bootstrap: wire embedding client, vector store, retriever, and
service into a single :class:`~app.rag.service.RagService` instance.

Call :func:`init_rag` from the FastAPI lifespan (see ``app/main.py``).
"""

from __future__ import annotations

from app.failover.manager import FailoverManager
from app.rag.config import get_rag_settings, RagSettings
from app.rag.embedding import EmbeddingClient
from app.rag.retrieval import HybridRetriever
from app.rag.router_state import set_rag_service
from app.rag.service import RagService
from app.rag.vector_store import VectorStore


async def init_rag(
    *,
    failover: FailoverManager,
) -> RagService:
    """Initialize and return the full RAG pipeline."""

    settings = get_rag_settings()
    rag_config = settings.rag

    if not rag_config.enabled:
        raise RuntimeError("RAG is disabled in configuration")

    # -------------------------------------------------------------
    # 1. Embedding client
    # -------------------------------------------------------------
    embedding_client = EmbeddingClient(
        config=rag_config.embedding,
        max_retries=3,
        retry_backoff_seconds=1.0,
        timeout_seconds=60.0,
    )

    # -------------------------------------------------------------
    # 2. Vector store (pgvector)
    # -------------------------------------------------------------
    vector_store = VectorStore(config=rag_config.vector_store)
    await vector_store.init_schema()

    # -------------------------------------------------------------
    # 3. Hybrid retriever
    # -------------------------------------------------------------
    retriever = HybridRetriever(
        vector_store=vector_store,
        config=rag_config.retrieval,
    )

    # -------------------------------------------------------------
    # 4. RAG service
    # -------------------------------------------------------------
    service = RagService(
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
        retriever=retriever,
        failover=failover,
    )

    set_rag_service(service)

    return service


async def shutdown_rag() -> None:
    """Close RAG clients and dispose of connection pools."""

    from app.rag.router_state import rag_service, set_rag_service

    service = rag_service
    if service is None:
        return

    await service._embedding.close()  # type: ignore[attr-defined]
    await service._store.close()  # type: ignore[attr-defined]

    set_rag_service(None)
