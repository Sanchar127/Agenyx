"""Document processing for evaluation workloads.

Splits evaluation documents into overlapping chunks for embedding and
vector store storage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class Chunk:
    """A single document chunk ready for embedding and storage."""

    content: str
    chunk_index: int
    metadata: dict[str, Any]


class DocumentProcessor:
    """Splits documents into overlapping chunks."""

    def __init__(
        self,
        *,
        chunk_size: int = 1_000,
        chunk_overlap: int = 200,
        separators: list[str] | None = None,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")

        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_overlap must be >= 0 and < chunk_size"
            )

        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._separators = separators or [
            "\n\n",
            "\n",
            ". ",
            "? ",
            "! ",
            "; ",
            ", ",
            " ",
        ]

    def chunk_text(
        self,
        *,
        text: str,
        document_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        """Split ``text`` into overlapping chunks."""

        if not text.strip():
            return []

        metadata = metadata or {}
        chunks: list[Chunk] = []
        index = 0

        segments = self._split_by_separators(text)

        current = ""
        for segment in segments:
            candidate = current + segment if current else segment

            if len(candidate) > self._chunk_size and current:
                chunks.append(
                    Chunk(
                        content=current.strip(),
                        chunk_index=index,
                        metadata=dict(metadata),
                    )
                )
                index += 1
                current = self._tail(current, self._chunk_overlap) + segment
            else:
                current = candidate

        if current.strip():
            chunks.append(
                Chunk(
                    content=current.strip(),
                    chunk_index=index,
                    metadata=dict(metadata),
                )
            )

        return chunks

    def _split_by_separators(self, text: str) -> list[str]:
        """Split text hierarchically by separators, largest first."""

        segments = [text]

        for separator in self._separators:
            new_segments: list[str] = []
            for segment in segments:
                if len(segment) <= self._chunk_size:
                    new_segments.append(segment)
                    continue

                parts = segment.split(separator)
                for i, part in enumerate(parts):
                    if i < len(parts) - 1:
                        new_segments.append(part + separator)
                    else:
                        new_segments.append(part)

            segments = new_segments

        return segments

    @staticmethod
    def _tail(text: str, length: int) -> str:
        """Return the last ``length`` characters of ``text``."""

        if length <= 0:
            return ""
        return text[-length:]

    def parse_document(
        self,
        *,
        content: str,
        content_type: str = "text/plain",
        document_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        """Parse a document and return chunks."""

        return self.chunk_text(
            text=content,
            document_id=document_id,
            metadata={
                **(metadata or {}),
                "content_type": content_type,
            },
        )
