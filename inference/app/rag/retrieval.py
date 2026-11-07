"""Hybrid retrieval for RAG.

Combines semantic (vector) search and keyword (full-text) search using
Reciprocal Rank Fusion (RRF), then applies per-document caps and
minimum-score filtering.
"""

from __future__ import annotations

from typing import Any

from app.logger import logger
from app.rag.config import RetrievalConfig
from app.rag.vector_store import VectorStore


def _rrf_score(rank: int, k: int = 60) -> float:
    """Reciprocal Rank Fusion score for a result at 1-based ``rank``."""

    return 1.0 / (k + rank)


def fuse_results(
    semantic: list[dict[str, Any]],
    keyword: list[dict[str, Any]],
    *,
    semantic_weight: float,
    keyword_weight: float,
    top_k: int,
) -> list[dict[str, Any]]:
    """Merge semantic and keyword results using weighted RRF.

    Each result carries a ``search_type`` field. Results are deduplicated
    by ``id``; fused scores combine the RRF ranks from both lists.
    """

    # Build rank maps keyed by result id.
    semantic_ranks: dict[str, int] = {}
    for rank, item in enumerate(semantic, start=1):
        semantic_ranks[item["id"]] = rank

    keyword_ranks: dict[str, int] = {}
    for rank, item in enumerate(keyword, start=1):
        keyword_ranks[item["id"]] = rank

    # Collect all unique ids, preferring semantic metadata when both exist.
    all_items: dict[str, dict[str, Any]] = {}
    for item in semantic + keyword:
        all_items[item["id"]] = item

    fused: list[tuple[str, float]] = []
    for item_id, item in all_items.items():
        s_rank = semantic_ranks.get(item_id)
        k_rank = keyword_ranks.get(item_id)

        s_score = _rrf_score(s_rank) if s_rank is not None else 0.0
        k_score = _rrf_score(k_rank) if k_rank is not None else 0.0

        fused_score = (semantic_weight * s_score) + (
            keyword_weight * k_score
        )
        fused.append((item_id, fused_score))

    fused.sort(key=lambda x: x[1], reverse=True)

    results: list[dict[str, Any]] = []
    for item_id, score in fused[:top_k]:
        item = dict(all_items[item_id])
        item["fused_score"] = score
        # Normalize score field for downstream consumers.
        item["score"] = score
        results.append(item)

    logger.debug(
        "RRF fusion complete",
        extra={
            "semantic_count": len(semantic),
            "keyword_count": len(keyword),
            "fused_count": len(results),
            "top_k": top_k,
        },
    )

    return results


def apply_per_document_cap(
    results: list[dict[str, Any]],
    *,
    max_chunks_per_document: int,
) -> list[dict[str, Any]]:
    """Limit the number of chunks returned per document."""

    counts: dict[str, int] = {}
    capped: list[dict[str, Any]] = []

    for item in results:
        doc_id = item.get("document_id", "unknown")
        count = counts.get(doc_id, 0)
        if count >= max_chunks_per_document:
            continue
        counts[doc_id] = count + 1
        capped.append(item)

    return capped


class HybridRetriever:
    """Orchestrates semantic + keyword search and fuses results."""

    def __init__(
        self,
        *,
        vector_store: VectorStore,
        config: RetrievalConfig,
    ) -> None:
        self._store = vector_store
        self._config = config

    async def retrieve(
        self,
        *,
        query: str,
        query_embedding: list[float],
        document_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run hybrid retrieval for a query.

        Returns the top-k fused chunks, each with content, metadata,
        score, and search provenance.
        """

        semantic = await self._store.semantic_search(
            query_embedding=query_embedding,
            top_k=self._config.hybrid_top_k,
            document_id=document_id,
            min_score=self._config.min_score,
        )

        keyword = await self._store.keyword_search(
            query=query,
            top_k=self._config.hybrid_top_k,
            document_id=document_id,
        )

        fused = fuse_results(
            semantic,
            keyword,
            semantic_weight=self._config.semantic_weight,
            keyword_weight=self._config.keyword_weight,
            top_k=self._config.top_k,
        )

        capped = apply_per_document_cap(
            fused,
            max_chunks_per_document=self._config.max_chunks_per_document,
        )

        logger.info(
            "Hybrid retrieval complete",
            extra={
                "query_length": len(query),
                "semantic_results": len(semantic),
                "keyword_results": len(keyword),
                "returned": len(capped),
            },
        )

        return capped
