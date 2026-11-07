"""RAG (Retrieval-Augmented Generation) module.

Provides production-grade retrieval-augmented generation on top of the
existing inference infrastructure: embedding, vector search (pgvector),
hybrid retrieval, context injection, and LLM generation with failover.
"""

from app.rag.bootstrap import init_rag, shutdown_rag
from app.rag.config import RagSettings
from app.rag.router_state import set_rag_service
from app.rag.service import RagService

__all__ = [
    "RagSettings",
    "RagService",
    "init_rag",
    "shutdown_rag",
    "set_rag_service",
]
