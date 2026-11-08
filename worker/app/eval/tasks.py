"""Evaluation task handler for the RAG worker.

Consumes document ingestion tasks from the Valkey queue, parses and
chunks the document, embeds each chunk, and upserts to the pgvector
store via the inference service's RAG vector store.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

import httpx

from app.agent_client import AgentClient
from app.config import get_settings
from app.eval.processor import DocumentProcessor
from app.queue import WorkerQueue

logger = logging.getLogger(__name__)


class EvalTaskHandler:
    """Handle a single document ingestion task for evaluation workloads."""

    def __init__(
        self,
        *,
        queue: WorkerQueue,
        agent_client: AgentClient,
        inference_base_url: str,
        inference_api_key: str,
        chunk_size: int = 1_000,
        chunk_overlap: int = 200,
    ) -> None:
        self._queue = queue
        self._agent_client = agent_client
        self._inference_base_url = inference_base_url.rstrip("/")
        self._api_key = inference_api_key
        self._processor = DocumentProcessor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            headers={
                "Content-Type": "application/json",
                "X-Agenyx-Service-Key": self._api_key,
            },
        )

    async def handle(
        self,
        *,
        message_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Process one ingestion task."""

        execution_id = str(payload.get("execution_id", ""))
        document_id = str(payload.get("document_id", ""))
        content = str(payload.get("content", ""))
        content_type = str(payload.get("content_type", "text/plain"))
        metadata_raw = payload.get("metadata", "{}")
        try:
            metadata = (
                json.loads(metadata_raw)
                if isinstance(metadata_raw, str)
                else metadata_raw or {}
            )
        except (json.JSONDecodeError, TypeError):
            metadata = {}

        if not document_id:
            document_id = self._digest(content)

        if not content.strip():
            logger.warning(
                "ingestion_empty_content",
                message_id=message_id,
                document_id=document_id,
            )
            self._update_state(
                execution_id,
                status="completed",
                answer="No content to ingest",
            )
            return

        logger.info(
            "ingestion_started",
            message_id=message_id,
            document_id=document_id,
            content_bytes=len(content),
        )

        start = time.perf_counter()

        try:
            # 1. Chunk the document.
            chunks = self._processor.parse_document(
                content=content,
                content_type=content_type,
                document_id=document_id,
                metadata=metadata,
            )

            if not chunks:
                self._update_state(
                    execution_id,
                    status="completed",
                    answer="Document produced no chunks",
                )
                return

            # 2. Embed each chunk via the inference service.
            embedded_chunks: list[dict[str, Any]] = []
            for idx, chunk in enumerate(chunks):
                embedding = await self._embed_text(chunk.content)
                embedded_chunks.append(
                    {
                        "chunk_index": idx,
                        "content": chunk.content,
                        "embedding": embedding,
                        "metadata": chunk.metadata,
                    }
                )

            # 3. Upsert to the vector store via the inference RAG API.
            await self._upsert_chunks(
                document_id=document_id,
                chunks=embedded_chunks,
            )

            duration_ms = int((time.perf_counter() - start) * 1000)

            self._update_state(
                execution_id,
                status="completed",
                answer=(
                    f"Ingested document '{document_id}': "
                    f"{len(embedded_chunks)} chunks"
                ),
                steps=len(embedded_chunks),
                duration_ms=duration_ms,
            )

            logger.info(
                "ingestion_completed",
                message_id=message_id,
                document_id=document_id,
                chunks=len(embedded_chunks),
                duration_ms=duration_ms,
            )

        except Exception:
            logger.exception(
                "ingestion_failed",
                message_id=message_id,
                document_id=document_id,
            )
            raise

    async def _embed_text(self, text: str) -> list[float]:
        """Embed a single text via the inference service embedding endpoint."""

        url = f"{self._inference_base_url}/v1/rag/embeddings"
        payload = {
            "input": [text],
        }

        response = await self._client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        items = data.get("data", [])
        if not items:
            raise RuntimeError("Embedding response contained no data")

        return [float(v) for v in items[0]["embedding"]]

    async def _upsert_chunks(
        self,
        *,
        document_id: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        """Upsert chunks to the inference service vector store."""

        url = f"{self._inference_base_url}/v1/rag/documents/upsert"
        payload = {
            "document_id": document_id,
            "chunks": chunks,
        }

        response = await self._client.post(url, json=payload)
        response.raise_for_status()

    def _digest(self, content: str) -> str:
        """Generate a stable document ID from content."""

        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]

    def _update_state(
        self,
        execution_id: str,
        *,
        status: str,
        answer: str | None = None,
        steps: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Update execution state in Valkey (mirrors executor pattern)."""

        key = f"agenyx:execution:{execution_id}"
        mapping: dict[str, Any] = {"status": status}

        if answer is not None:
            mapping["answer"] = answer
        if steps is not None:
            mapping["steps"] = str(steps)
        if duration_ms is not None:
            mapping["duration_ms"] = str(duration_ms)

        self._queue.client.hset(key, mapping=mapping)

    async def close(self) -> None:
        await self._client.aclose()


def make_handler(
    *,
    queue: WorkerQueue,
    agent_client: AgentClient,
) -> EvalTaskHandler:
    """Build an :class:`EvalTaskHandler` from worker settings."""

    settings = get_settings()

    return EvalTaskHandler(
        queue=queue,
        agent_client=agent_client,
        inference_base_url=settings.inference_url,
        inference_api_key=os.getenv("INFERENCE_SERVICE_API_KEY", ""),
        chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "1000")),
        chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "200")),
    )
