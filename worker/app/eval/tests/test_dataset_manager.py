"""Unit tests for dataset manager."""

import hashlib
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.eval.dataset_manager import DatasetManager


def test_dataset_manager_init():
    manager = DatasetManager(
        s3_endpoint="minio:9000",
        s3_bucket="agenyx-eval",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin",
        s3_use_ssl=False,
    )
    assert manager.s3_endpoint == "minio:9000"
    assert manager.s3_bucket == "agenyx-eval"


def test_compute_checksum():
    manager = DatasetManager(
        s3_endpoint="minio:9000",
        s3_bucket="agenyx-eval",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin",
    )
    content = b'{"key": "value"}\n'
    checksum = manager.compute_checksum(content)
    assert len(checksum) == 64  # SHA-256 hex digest
    assert checksum == hashlib.sha256(content).hexdigest()


def test_serialize_jsonl():
    manager = DatasetManager(
        s3_endpoint="minio:9000",
        s3_bucket="agenyx-eval",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin",
    )
    records = [{"id": 1, "text": "hello"}, {"id": 2, "text": "world"}]
    content = manager.serialize_jsonl(records)
    lines = content.decode("utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"id": 1, "text": "hello"}
    assert json.loads(lines[1]) == {"id": 2, "text": "world"}


def test_parse_jsonl():
    manager = DatasetManager(
        s3_endpoint="minio:9000",
        s3_bucket="agenyx-eval",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin",
    )
    content = b'{"id": 1, "text": "hello"}\n{"id": 2, "text": "world"}\n'
    records = manager.parse_jsonl(content)
    assert len(records) == 2
    assert records[0] == {"id": 1, "text": "hello"}
    assert records[1] == {"id": 2, "text": "world"}


def test_s3_key():
    manager = DatasetManager(
        s3_endpoint="minio:9000",
        s3_bucket="agenyx-eval",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin",
    )
    key = manager.s3_key("my dataset", "1.0")
    assert key == "datasets/my_dataset/1.0/data.jsonl"


def test_s3_url():
    manager = DatasetManager(
        s3_endpoint="minio:9000",
        s3_bucket="agenyx-eval",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin",
    )
    url = manager.s3_url("datasets/test/1.0/data.jsonl")
    assert url == "http://minio:9000/agenyx-eval/datasets/test/1.0/data.jsonl"


def test_s3_url_https():
    manager = DatasetManager(
        s3_endpoint="s3.amazonaws.com",
        s3_bucket="my-bucket",
        s3_access_key="key",
        s3_secret_key="secret",
        s3_use_ssl=True,
    )
    url = manager.s3_url("datasets/test/1.0/data.jsonl")
    assert url == "https://s3.amazonaws.com/my-bucket/datasets/test/1.0/data.jsonl"


@pytest.mark.asyncio
async def test_upload_dataset():
    manager = DatasetManager(
        s3_endpoint="minio:9000",
        s3_bucket="agenyx-eval",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin",
    )
    manager._client.put = AsyncMock(return_value=MagicMock(status_code=200))

    result = await manager.upload_dataset(
        dataset_name="test-dataset",
        version="1.0",
        records=[{"id": 1, "text": "hello"}],
        created_by="test-user",
        description="Test dataset",
    )

    assert result["name"] == "test-dataset"
    assert result["version"] == "1.0"
    assert len(result["checksum"]) == 64
    assert result["row_count"] == 1
    assert result["created_by"] == "test-user"
    assert result["description"] == "Test dataset"
    assert result["s3_uri"].startswith("s3://agenyx-eval/")
    await manager.close()


@pytest.mark.asyncio
async def test_download_dataset():
    manager = DatasetManager(
        s3_endpoint="minio:9000",
        s3_bucket="agenyx-eval",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin",
    )
    content = b'{"id": 1, "text": "hello"}\n{"id": 2, "text": "world"}\n'
    manager._client.get = AsyncMock(return_value=MagicMock(status_code=200, content=content))

    records = await manager.download_dataset(s3_uri="s3://agenyx-eval/datasets/test/1.0/data.jsonl")
    assert len(records) == 2
    assert records[0] == {"id": 1, "text": "hello"}
    assert records[1] == {"id": 2, "text": "world"}
    await manager.close()


@pytest.mark.asyncio
async def test_health_true():
    manager = DatasetManager(
        s3_endpoint="minio:9000",
        s3_bucket="agenyx-eval",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin",
    )
    manager._client.get = AsyncMock(return_value=MagicMock(status_code=200))
    assert await manager.health() is True
    await manager.close()


@pytest.mark.asyncio
async def test_health_false():
    manager = DatasetManager(
        s3_endpoint="minio:9000",
        s3_bucket="agenyx-eval",
        s3_access_key="minioadmin",
        s3_secret_key="minioadmin",
    )
    manager._client.get = AsyncMock(side_effect=Exception("connection error"))
    assert await manager.health() is False
    await manager.close()
