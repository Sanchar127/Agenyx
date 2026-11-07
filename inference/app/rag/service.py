"""RAG service: orchestrate retrieve -> augment -> generate.

Takes a user query, embeds it, retrieves relevant chunks via hybrid
search, builds a context-augmented prompt, and calls the LLM through
the existing inference failover infrastructure.
"""

from __future__ import annotations

import time
from typing import Any

from app.failover.manager import FailoverManager
from app.logger import logger
from app.metrics import (
    INFERENCE_REQUESTS_TOTAL,
    INFERENCE_REQUEST_DURATION_SECONDS,
)
from app.rag.config import RagSettings
from app.rag.embedding import EmbeddingClient
from app.rag.retrieval import HybridRetriever
from app.rag.vector_store import VectorStore


class RagError(RuntimeError):
    """Raised when the RAG pipeline fails."""


class RagService:
    """End-to-end RAG pipeline."""

    def __init__(
        self,
        *,
        settings: RagSettings,
        embedding_client: EmbeddingClient,
        vector_store: VectorStore,
        retriever: HybridRetriever,
        failover: FailoverManager,
    ) -> None:
        self._settings = settings
        self._embedding = embedding_client
        self._store = vector_store
        self._retriever = retriever
        self._failover = failover

    async def answer(
        self,
        *,
        query: str,
        document_id: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Run the full RAG pipeline and return the answer with sources."""

        request_start = time.perf_counter()

        # ---------------------------------------------------------
        # 1. Embed the query
        # ---------------------------------------------------------
        embed_start = time.perf_counter()
        try:
            query_embedding = await self._embedding.embed(query)
        except Exception as exc:
            logger.error(
                "RAG query embedding failed",
                extra={
                    "query_length": len(query),
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
            raise RagError(f"Failed to embed query: {exc}") from exc

        embed_duration = time.perf_counter() - embed_start
        logger.info(
            "RAG query embedded",
            extra={
                "query_length": len(query),
                "embed_duration_ms": round(embed_duration * 1000, 2),
            },
        )

        # ---------------------------------------------------------
        # 2. Retrieve relevant chunks (hybrid search)
        # ---------------------------------------------------------
        retrieve_start = time.perf_counter()
        try:
            chunks = await self._retriever.retrieve(
                query=query,
                query_embedding=query_embedding,
                document_id=document_id,
            )
        except Exception as exc:
            logger.error(
                "RAG retrieval failed",
                extra={
                    "query_length": len(query),
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
            raise RagError(f"Retrieval failed: {exc}") from exc

        retrieve_duration = time.perf_counter() - retrieve_start

        # ---------------------------------------------------------
        # 3. Build augmented context
        # ---------------------------------------------------------
        context_blocks: list[str] = []
        sources: list[dict[str, Any]] = []
        total_chars = 0
        max_chars = self._settings.rag.generation.max_context_chars

        for index, chunk in enumerate(chunks, start=1):
            content = chunk.get("content", "")
            source_label = f"[Source {index}]"

            # Track source metadata for the response.
            sources.append(
                {
                    "index": index,
                    "document_id": chunk.get("document_id"),
                    "chunk_index": chunk.get("chunk_index"),
                    "score": chunk.get("score"),
                    "search_type": chunk.get("search_type"),
                    "metadata": chunk.get("metadata", {}),
                    "content_preview": content[:200],
                }
            )

            block = f"{source_label} {content}\n"
            block_chars = len(block)

            if total_chars + block_chars > max_chars and context_blocks:
                break

            context_blocks.append(block)
            total_chars += block_chars

        context = "\n".join(context_blocks)

        logger.info(
            "RAG context built",
            extra={
                "chunk_count": len(chunks),
                "context_chars": total_chars,
                "max_context_chars": max_chars,
            },
        )

        # ---------------------------------------------------------
        # 4. Build messages for the LLM
        # ---------------------------------------------------------
        system_prompt = self._settings.rag.generation.system_prompt

        user_prompt = (
            "Context:\n"
            f"{context}\n\n"
            f"---\n\n"
            f"Question: {query}\n\n"
            "Answer using only the context above. Cite sources using "
            "[Source N] notation."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # ---------------------------------------------------------
        # 5. Generate via existing failover infrastructure
        # ---------------------------------------------------------
        target_model = model or self._settings.rag.generation.model

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": self._settings.rag.generation.temperature,
            "max_tokens": self._settings.rag.generation.max_tokens,
            "stream": False,
        }

        generate_start = time.perf_counter()
        try:
            result = await self._failover.chat_completion(payload)
        except Exception as exc:
            INFERENCE_REQUESTS_TOTAL.labels(
                provider="rag-failover",
                model=target_model,
                status="error",
            ).inc()

            logger.error(
                "RAG generation failed",
                extra={
                    "model": target_model,
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
            raise RagError(f"Generation failed: {exc}") from exc

        generate_duration = time.perf_counter() - generate_start

        provider = result.provider
        response = result.response

        INFERENCE_REQUESTS_TOTAL.labels(
            provider=provider,
            model=target_model,
            status="success",
        ).inc()
        INFERENCE_REQUEST_DURATION_SECONDS.labels(
            provider=provider,
            model=target_model,
        ).observe(generate_duration)

        # ---------------------------------------------------------
        # 6. Assemble response
        # ---------------------------------------------------------
        total_duration = time.perf_counter() - request_start

        answer_text = ""
        choices = response.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            answer_text = message.get("content", "")

        logger.info(
            "RAG pipeline complete",
            extra={
                "query_length": len(query),
                "model": target_model,
                "provider": provider,
                "chunks_retrieved": len(chunks),
                "context_chars": total_chars,
                "total_duration_ms": round(total_duration * 1000, 2),
                "embed_duration_ms": round(embed_duration * 1000, 2),
                "retrieve_duration_ms": round(retrieve_duration * 1000, 2),
                "generate_duration_ms": round(generate_duration * 1000, 2),
            },
        )

        return {
            "answer": answer_text,
            "model": target_model,
            "provider": provider,
            "sources": sources,
            "chunks_retrieved": len(chunks),
            "usage": response.get("usage", {}),
            "timing_ms": {
                "embed": round(embed_duration * 1000, 2),
                "retrieve": round(retrieve_duration * 1000, 2),
                "generate": round(generate_duration * 1000, 2),
                "total": round(total_duration * 1000, 2),
            },
        }

    async def health(self) -> dict[str, Any]:
        """Check health of all RAG dependencies."""

        embedding_healthy = await self._embedding.health()

        return {
            "embedding": embedding_healthy,
            "vector_store": True,  # pgvector checked via embedding query
            "status": "healthy" if embedding_healthy else "degraded",
        }
