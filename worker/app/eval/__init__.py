"""Evaluation worker package for the Agenyx Evaluation Platform.

This package handles document ingestion, chunking, embedding, and vector store
upsertion as asynchronous worker tasks for document-based evaluation workloads.
"""

from app.eval.processor import DocumentProcessor, Chunk
from app.eval.tasks import EvalTaskHandler

__all__ = [
    "DocumentProcessor",
    "Chunk",
    "EvalTaskHandler",
]
