-- Enable pgvector extension for the RAG vector store.
-- This runs automatically on PostgreSQL startup via
-- docker-entrypoint-initdb.d.

CREATE EXTENSION IF NOT EXISTS vector;
