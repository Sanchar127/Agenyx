"""Unit tests for RAG hybrid retrieval (RRF fusion)."""

from app.rag.retrieval import (
    apply_per_document_cap,
    fuse_results,
)


def test_fuse_results_deduplicates_by_id():
    """Results appearing in both lists are merged once with combined RRF score."""

    semantic = [
        {"id": "a", "content": "alpha", "score": 0.9, "search_type": "semantic"},
        {"id": "b", "content": "beta", "score": 0.8, "search_type": "semantic"},
    ]
    keyword = [
        {"id": "b", "content": "beta", "score": 0.7, "search_type": "keyword"},
        {"id": "c", "content": "gamma", "score": 0.6, "search_type": "keyword"},
    ]

    fused = fuse_results(
        semantic,
        keyword,
        semantic_weight=0.7,
        keyword_weight=0.3,
        top_k=10,
    )

    ids = [r["id"] for r in fused]
    assert len(ids) == len(set(ids)), "no duplicate ids"
    # 'b' appears in both lists, so it gets the highest combined RRF score.
    assert ids == ["b", "a", "c"]


def test_fuse_results_semantic_weighted_higher():
    """A result ranked #1 semantically outranks #1 keyword-only when
    semantic_weight > keyword_weight."""

    semantic = [
        {"id": "a", "content": "a", "score": 0.9, "search_type": "semantic"},
    ]
    keyword = [
        {"id": "b", "content": "b", "score": 0.9, "search_type": "keyword"},
    ]

    fused_semantic = fuse_results(
        semantic, keyword, semantic_weight=0.9, keyword_weight=0.1, top_k=10
    )
    assert fused_semantic[0]["id"] == "a"

    fused_keyword = fuse_results(
        semantic, keyword, semantic_weight=0.1, keyword_weight=0.9, top_k=10
    )
    assert fused_keyword[0]["id"] == "b"


def test_fuse_results_top_k_limits():
    """top_k caps the number of results."""

    semantic = [
        {"id": f"s{i}", "content": f"s{i}", "score": 0.9, "search_type": "semantic"}
        for i in range(10)
    ]
    keyword = [
        {"id": f"k{i}", "content": f"k{i}", "score": 0.8, "search_type": "keyword"}
        for i in range(10)
    ]

    fused = fuse_results(
        semantic, keyword, semantic_weight=0.7, keyword_weight=0.3, top_k=5
    )
    assert len(fused) == 5


def test_apply_per_document_cap():
    """Max chunks per document is enforced."""

    results = [
        {"id": "1", "document_id": "doc-a", "content": "a1", "score": 0.9},
        {"id": "2", "document_id": "doc-a", "content": "a2", "score": 0.8},
        {"id": "3", "document_id": "doc-a", "content": "a3", "score": 0.7},
        {"id": "4", "document_id": "doc-b", "content": "b1", "score": 0.6},
    ]

    capped = apply_per_document_cap(
        results, max_chunks_per_document=2
    )

    doc_a_count = sum(1 for r in capped if r["document_id"] == "doc-a")
    doc_b_count = sum(1 for r in capped if r["document_id"] == "doc-b")

    assert doc_a_count == 2
    assert doc_b_count == 1
    assert len(capped) == 3
