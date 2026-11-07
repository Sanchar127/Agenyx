"""Document ingestion package for the RAG pipeline.

Handles document parsing, chunking, embedding, and vector store
upsertion as asynchronous worker tasks.
"""

from app.ingestion.processor import DocumentProcessor, Chunk

__all__ = [
    "DocumentProcessor",
    "Chunk",
]
