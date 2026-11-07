"""Dataset management for the Agenyx Evaluation Platform.

Handles dataset versioning, checksums, and S3-compatible storage for
evaluation datasets. Datasets are stored as JSONL files in S3, with
metadata tracked in PostgreSQL.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import httpx


class DatasetManager:
    """Manage evaluation datasets: versioning, checksums, S3 storage."""

    def __init__(
        self,
        *,
        s3_endpoint: str,
        s3_bucket: str,
        s3_access_key: str,
        s3_secret_key: str,
        s3_use_ssl: bool = False,
    ) -> None:
        self.s3_endpoint = s3_endpoint.rstrip("/")
        self.s3_bucket = s3_bucket
        self.s3_access_key = s3_access_key
        self.s3_secret_key = s3_secret_key
        self.s3_use_ssl = s3_use_ssl

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
        )

    def compute_checksum(self, content: bytes) -> str:
        """Compute SHA-256 checksum of dataset content."""

        return hashlib.sha256(content).hexdigest()

    def serialize_jsonl(self, records: list[dict[str, Any]]) -> bytes:
        """Serialize a list of dicts to JSONL bytes."""

        lines = [json.dumps(record, ensure_ascii=False) for record in records]
        return "\n".join(lines).encode("utf-8")

    def parse_jsonl(self, content: bytes) -> list[dict[str, Any]]:
        """Parse JSONL bytes into a list of dicts."""

        records: list[dict[str, Any]] = []
        for line in content.decode("utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    def s3_key(self, dataset_name: str, version: str) -> str:
        """Generate S3 key for a dataset version."""

        safe_name = dataset_name.replace("/", "_").replace(" ", "_")
        safe_version = version.replace("/", "_").replace(" ", "_")
        return f"datasets/{safe_name}/{safe_version}/data.jsonl"

    def s3_url(self, key: str) -> str:
        """Generate S3 URL for a key."""

        scheme = "https" if self.s3_use_ssl else "http"
        return f"{scheme}://{self.s3_endpoint}/{self.s3_bucket}/{key}"

    async def upload_dataset(
        self,
        *,
        dataset_name: str,
        version: str,
        records: list[dict[str, Any]],
        created_by: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Upload a dataset to S3 and return metadata."""

        content = self.serialize_jsonl(records)
        checksum = self.compute_checksum(content)
        key = self.s3_key(dataset_name, version)
        url = self.s3_url(key)

        # Upload to S3 via PUT
        response = await self._client.put(
            url,
            content=content,
            headers={
                "Content-Type": "application/jsonl",
                "x-amz-acl": "private",
            },
            auth=(self.s3_access_key, self.s3_secret_key),
        )
        response.raise_for_status()

        return {
            "name": dataset_name,
            "version": version,
            "checksum": checksum,
            "s3_uri": f"s3://{self.s3_bucket}/{key}",
            "s3_url": url,
            "row_count": len(records),
            "created_by": created_by,
            "description": description,
        }

    async def download_dataset(
        self,
        *,
        s3_uri: str,
    ) -> list[dict[str, Any]]:
        """Download a dataset from S3 and return parsed records."""

        # Convert s3://bucket/key to HTTP URL
        if s3_uri.startswith("s3://"):
            path = s3_uri[5:]  # Remove "s3://"
            bucket, _, key = path.partition("/")
            url = self.s3_url(key)
        else:
            url = s3_uri

        response = await self._client.get(
            url,
            auth=(self.s3_access_key, self.s3_secret_key),
        )
        response.raise_for_status()

        return self.parse_jsonl(response.content)

    async def health(self) -> bool:
        """Check whether S3 storage is reachable."""

        try:
            response = await self._client.get(
                self.s3_url(""),
                auth=(self.s3_access_key, self.s3_secret_key),
            )
            return response.status_code in (200, 403, 404)
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
