"""Unit tests for evaluation document chunking."""

import pytest

from app.eval.processor import Chunk, DocumentProcessor


def test_chunk_text_basic():
    """A short document returns a single chunk."""

    processor = DocumentProcessor(chunk_size=100, chunk_overlap=20)
    chunks = processor.chunk_text(
        text="Hello world. This is a test document.",
        document_id="doc-1",
    )

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content == "Hello world. This is a test document."


def test_chunk_text_splits_long_document():
    """A long document is split into multiple overlapping chunks."""

    processor = DocumentProcessor(chunk_size=50, chunk_overlap=10)
    text = "Sentence one. Sentence two. Sentence three. Sentence four."

    chunks = processor.chunk_text(
        text=text,
        document_id="doc-1",
    )

    assert len(chunks) > 1
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_chunk_text_empty():
    """Empty text returns no chunks."""

    processor = DocumentProcessor()
    chunks = processor.chunk_text(text="", document_id="doc-1")
    assert chunks == []


def test_chunk_text_metadata():
    """Metadata is attached to each chunk."""

    processor = DocumentProcessor(chunk_size=100, chunk_overlap=20)
    chunks = processor.chunk_text(
        text="Hello world.",
        document_id="doc-1",
        metadata={"source": "upload.pdf", "author": "alice"},
    )

    assert chunks[0].metadata["source"] == "upload.pdf"
    assert chunks[0].metadata["author"] == "alice"


def test_chunk_text_rejects_invalid_overlap():
    """chunk_overlap >= chunk_size is rejected."""

    with pytest.raises(ValueError):
        DocumentProcessor(chunk_size=100, chunk_overlap=100)


def test_chunk_dataclass():
    """Chunk dataclass fields are accessible."""

    chunk = Chunk(
        content="hello",
        chunk_index=0,
        metadata={"key": "value"},
    )
    assert chunk.content == "hello"
    assert chunk.chunk_index == 0
    assert chunk.metadata == {"key": "value"}
