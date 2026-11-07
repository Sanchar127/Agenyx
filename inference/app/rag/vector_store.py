"""Vector store backed by pgvector on PostgreSQL.

Stores document chunks with their embedding vectors and supports
semantic similarity search (cosine / L2 / inner product) plus
full-text keyword search for hybrid retrieval.

Tables are created automatically on startup via :meth:`init_schema`.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import (
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.logger import logger
from app.rag.config import VectorStoreConfig


try:  # pgvector is optional at import time; required at runtime.
    from pgvector.sqlalchemy import Vector

    _HAS_PGVECTOR = True
except ImportError:  # pragma: no cover - handled at startup
    _HAS_PGVECTOR = False

    class Vector:  # type: ignore[no-redef]
        """Stub so the module imports without pgvector installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pgvector is not installed")


metadata = MetaData()

rag_documents = None  # type: ignore[assignment]


def _build_table(embedding_dimensions: int) -> Any:
    """Build the SQLAlchemy Table with the given embedding dimensions."""

    if not _HAS_PGVECTOR:
        raise ImportError(
            "pgvector is required for the vector store. "
            "Install it with: pip install pgvector"
        )

    Table = __import__("sqlalchemy", fromlist=["Table"]).Table
    Column = __import__("sqlalchemy", fromlist=["Column"]).Column

    table = Table(
        "rag_documents",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("document_id", String(255), nullable=False, index=True),
        Column("chunk_index", Integer, nullable=False),
        Column("content", Text, nullable=False),
        Column(
            "metadata",
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
        Column("embedding", Vector(embedding_dimensions), nullable=False),
        Column(
            "created_at",
            String,
            nullable=False,
            server_default=func.now(),
        ),
    )

    # GIN index for full-text search on content.
    # Use text() for the to_tsvector expression because SQLAlchemy
    # cannot render the 'english' regconfig literal in this version.
    Index(
        "ix_rag_documents_content_fts",
        text("to_tsvector('english', content)"),
        postgresql_using="gin",
    )

    # NOTE: The HNSW vector index is NOT defined here as a SQLAlchemy
    # Index because pgvector requires an explicit operator class
    # (vector_cosine_ops / vector_l2_ops / vector_ip_ops) that this
    # SQLAlchemy version cannot render. It is created via raw SQL in
    # init_schema() instead.
    return table


class VectorStore:
    """Async pgvector store for document chunks."""

    def __init__(
        self,
        *,
        config: VectorStoreConfig,
    ) -> None:
        if not _HAS_PGVECTOR:
            raise ImportError(
                "pgvector is required for VectorStore. "
                "Install it with: pip install pgvector"
            )

        self._config = config
        self._engine = create_async_engine(
            config.database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Build the table with the configured embedding dimensions.
        global rag_documents
        rag_documents = _build_table(config.embedding_dimensions)

        logger.info(
            "Vector store initialized",
            extra={
                "table": config.table_name,
                "dimensions": config.embedding_dimensions,
                "distance": config.distance_metric,
            },
        )

    async def init_schema(self) -> None:
        """Create the pgvector extension and tables if they don't exist."""

        distance_opclass = {
            "cosine": "vector_cosine_ops",
            "l2": "vector_l2_ops",
            "ip": "vector_ip_ops",
        }[self._config.distance_metric]

        async with self._engine.begin() as conn:
            # Enable pgvector extension.
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

            # Create all tables (including the placeholder HNSW index
            # without an opclass).
            await conn.run_sync(metadata.create_all)

            # Drop the placeholder index and recreate with the correct
            # opclass for the configured distance metric.
            await conn.execute(
                text("DROP INDEX IF EXISTS ix_rag_documents_embedding")
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rag_documents_embedding "
                    "ON rag_documents USING hnsw (embedding "
                    f"{distance_opclass}) "
                    "WITH (m = 16, ef_construction = 64)"
                )
            )

        logger.info("Vector store schema initialized")

    async def upsert_chunks(
        self,
        *,
        document_id: str,
        chunks: list[dict[str, Any]],
    ) -> list[int]:
        """Insert document chunks and return their primary keys.

        Each chunk dict must contain: ``content``, ``embedding`` (list of
        floats), ``chunk_index`` (int), and optional ``metadata`` (dict).
        """

        if not chunks:
            return []

        async with self._session_factory() as session:
            rows = []
            for chunk in chunks:
                rows.append(
                    {
                        "document_id": document_id,
                        "chunk_index": int(chunk["chunk_index"]),
                        "content": str(chunk["content"]),
                        "metadata": json.dumps(
                            chunk.get("metadata", {})
                        ),
                        "embedding": chunk["embedding"],
                    }
                )

            result = await session.execute(
                rag_documents.insert().returning(rag_documents.c.id),
                rows,
            )
            await session.commit()

            ids = [row[0] for row in result.fetchall()]

            logger.info(
                "Chunks upserted",
                extra={
                    "document_id": document_id,
                    "chunk_count": len(chunks),
                    "ids": ids,
                },
            )

            return ids

    async def delete_document(
        self,
        *,
        document_id: str,
    ) -> int:
        """Delete all chunks for a document. Returns number deleted."""

        async with self._session_factory() as session:
            result = await session.execute(
                rag_documents.delete().where(
                    rag_documents.c.document_id == document_id
                )
            )
            await session.commit()

            deleted = result.rowcount or 0

            logger.info(
                "Document chunks deleted",
                extra={
                    "document_id": document_id,
                    "deleted": deleted,
                },
            )

            return deleted

    def _distance_expression(
        self,
        query_embedding: list[float],
    ):
        """Return the SQLAlchemy distance expression for the configured metric."""

        embedding_col = rag_documents.c.embedding

        if self._config.distance_metric == "cosine":
            # cosine_distance: 0 = identical, 2 = opposite.
            # Similarity score = 1 - cosine_distance.
            return embedding_col.cosine_distance(query_embedding)
        if self._config.distance_metric == "l2":
            return embedding_col.l2_distance(query_embedding)
        # ip = inner product (higher = more similar)
        return embedding_col.max_inner_product(query_embedding)

    def _score_expression(
        self,
        distance_expr: Any,
    ) -> Any:
        """Convert a distance expression into a similarity score expression."""

        if self._config.distance_metric == "cosine":
            return (1 - distance_expr).label("score")
        if self._config.distance_metric == "l2":
            return (1 / (1 + distance_expr)).label("score")
        # inner product is already a similarity score
        return distance_expr.label("score")

    async def semantic_search(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        document_id: str | None = None,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Semantic similarity search using the configured distance metric."""

        distance_expr = self._distance_expression(query_embedding)
        score_expr = self._score_expression(distance_expr)

        stmt = (
            select(
                rag_documents.c.id,
                rag_documents.c.document_id,
                rag_documents.c.chunk_index,
                rag_documents.c.content,
                rag_documents.c.metadata,
                score_expr,
            )
            .where(score_expr >= min_score)
            .order_by(score_expr.desc())
            .limit(top_k)
        )

        if document_id:
            stmt = stmt.where(
                rag_documents.c.document_id == document_id
            )

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            rows = result.fetchall()

        return [
            {
                "id": row[0],
                "document_id": row[1],
                "chunk_index": row[2],
                "content": row[3],
                "metadata": row[4] or {},
                "score": float(row[5]),
                "search_type": "semantic",
            }
            for row in rows
        ]

    async def keyword_search(
        self,
        *,
        query: str,
        top_k: int,
        document_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Full-text keyword search using PostgreSQL tsvector.

        Uses text() expressions for the to_tsvector / plainto_tsquery
        calls because SQLAlchemy cannot render the 'english' regconfig
        literal in this version.
        """

        from sqlalchemy import literal_column

        ts_query = text(
            "plainto_tsquery('english', :query)"
        ).bindparams(query=query)
        tsvector = literal_column("to_tsvector('english', content)")
        score_expr = func.ts_rank(tsvector, ts_query).label("score")

        where_clause = text(
            "to_tsvector('english', content) @@ "
            "plainto_tsquery('english', :query)"
        ).bindparams(query=query)

        stmt = (
            select(
                rag_documents.c.id,
                rag_documents.c.document_id,
                rag_documents.c.chunk_index,
                rag_documents.c.content,
                rag_documents.c.metadata,
                score_expr,
            )
            .where(where_clause)
            .order_by(text("score DESC"))
            .limit(top_k)
        )

        if document_id:
            stmt = stmt.where(
                rag_documents.c.document_id == document_id
            )

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            rows = result.fetchall()

        return [
            {
                "id": row[0],
                "document_id": row[1],
                "chunk_index": row[2],
                "content": row[3],
                "metadata": row[4] or {},
                "score": float(row[5]),
                "search_type": "keyword",
            }
            for row in rows
        ]

    async def close(self) -> None:
        """Dispose of the engine and connection pool."""

        await self._engine.dispose()
