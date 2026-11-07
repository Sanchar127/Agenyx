"""Unit tests for the evaluation engine."""

import asyncio
import datetime as dt
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.eval.api_client import EvalAPIClient
from app.eval.dataset_manager import DatasetManager
from app.eval.engine import EvaluationEngine
from app.eval.models import Evaluation, EvaluationRun


@pytest.fixture
def mock_api_client():
    client = AsyncMock(spec=EvalAPIClient)
    return client


@pytest.fixture
def mock_dataset_manager():
    dm = AsyncMock(spec=DatasetManager)
    return dm


@pytest.fixture
def sample_evaluation():
    return Evaluation(
        id=uuid.uuid4(),
        name="test-eval",
        evaluation_type="llm",
        dataset_id=uuid.uuid4(),
        status="queued",
        progress=0,
        priority="normal",
        timeout_seconds=3600,
        max_concurrency=5,
        config_snapshot={
            "scorers": ["task_completion", "answer_correctness"],
        },
        created_by="test",
        created_at=dt.datetime.now(dt.timezone.utc),
    )


@pytest.mark.asyncio
async def test_engine_init(mock_api_client, mock_dataset_manager):
    engine = EvaluationEngine(
        api_client=mock_api_client,
        dataset_manager=mock_dataset_manager,
    )
    assert engine._api is mock_api_client
    assert engine._dataset_manager is mock_dataset_manager
    assert engine._providers == {}


@pytest.mark.asyncio
async def test_run_single_model_basic(mock_api_client, mock_dataset_manager, sample_evaluation):
    """Test running a single model evaluation with mocked provider."""

    mock_dataset_manager.download_dataset = AsyncMock(
        return_value=[
            {"text": "What is 2+2?", "expected": "4"},
            {"text": "What is 3+3?", "expected": "6"},
        ]
    )

    import app.eval.engine as engine_module
    original_get = engine_module.get_provider_class

    def fake_get_provider_class(provider_id):
        if provider_id == "ollama-local":
            class FakeProvider:
                def __init__(self, provider_id, endpoint_url, api_key):
                    self.provider_id = provider_id
                    self.provider_type = "ollama"
                    self.endpoint_url = endpoint_url
                    self.api_key = api_key

                async def chat_completion(self, **kwargs):
                    return {
                        "id": "chatcmpl-1",
                        "model": "qwen2.5:7b",
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": "4"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                    }

                async def embedding(self, **kwargs):
                    return {}

                async def health(self):
                    return True

                async def close(self):
                    pass

            return FakeProvider
        raise KeyError(f"Unknown provider: {provider_id}")

    engine_module.get_provider_class = fake_get_provider_class

    try:
        engine = EvaluationEngine(
            api_client=mock_api_client,
            dataset_manager=mock_dataset_manager,
        )

        mock_api_client.list_datasets = AsyncMock(
            return_value=[
                {
                    "id": str(sample_evaluation.dataset_id),
                    "name": "test-dataset",
                    "version": "1.0",
                    "checksum": "abc123",
                    "s3_uri": "s3://bucket/dataset.jsonl",
                    "row_count": 2,
                }
            ]
        )
        mock_api_client.list_providers = AsyncMock(
            return_value=[
                {
                    "provider_id": "ollama-local",
                    "provider_type": "ollama",
                    "endpoint_url": "http://ollama:11434/v1",
                    "auth_ref": "",
                    "capabilities": ["chat"],
                    "health_status": "healthy",
                }
            ]
        )

        run = await engine._run_single_model(
            evaluation=sample_evaluation,
            model_config={
                "model_id": "qwen2.5:7b",
                "provider_id": "ollama-local",
                "generation_params": {},
            },
            records=[
                {"text": "What is 2+2?", "expected": "4"},
                {"text": "What is 3+3?", "expected": "6"},
            ],
        )

        assert run.model_id == "qwen2.5:7b"
        assert run.provider_id == "ollama-local"
        assert run.status == "completed"
        assert run.success_rate == 1.0  # 2/2 correct
        assert run.total_tokens > 0

        await engine.close()
    finally:
        engine_module.get_provider_class = original_get


@pytest.mark.asyncio
async def test_run_evaluation_integration(mock_api_client, mock_dataset_manager, sample_evaluation):
    """Test full evaluation run with mocked components."""

    mock_dataset_manager.download_dataset = AsyncMock(
        return_value=[{"text": "Hello", "expected": "Hi"}]
    )

    mock_api_client.list_datasets = AsyncMock(
        return_value=[
            {
                "id": str(sample_evaluation.dataset_id),
                "name": "test-dataset",
                "version": "1.0",
                "checksum": "abc",
                "s3_uri": "s3://bucket/d.jsonl",
                "row_count": 1,
            }
        ]
    )
    mock_api_client.list_providers = AsyncMock(
        return_value=[
            {
                "provider_id": "test-provider",
                "provider_type": "test",
                "endpoint_url": "http://test:8000/v1",
                "auth_ref": "",
                "capabilities": ["chat"],
                "health_status": "healthy",
            }
        ]
    )

    import app.eval.engine as engine_module

    def fake_get_provider_class(provider_id):
        class FakeProvider:
            def __init__(self, provider_id, endpoint_url, api_key):
                self.provider_id = provider_id
                self.provider_type = "test"
                self.endpoint_url = endpoint_url
                self.api_key = api_key

            async def chat_completion(self, **kwargs):
                return {
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Hi"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                }

            async def embedding(self, **kwargs):
                return {}

            async def health(self):
                return True

            async def close(self):
                pass

        return FakeProvider

    engine_module.get_provider_class = fake_get_provider_class

    try:
        engine = EvaluationEngine(
            api_client=mock_api_client,
            dataset_manager=mock_dataset_manager,
        )

        runs = await engine.run_evaluation(
            evaluation=sample_evaluation,
            models=[
                {
                    "model_id": "test-model",
                    "provider_id": "test-provider",
                    "generation_params": {},
                }
            ],
        )

        assert len(runs) == 1
        assert runs[0].model_id == "test-model"
        assert runs[0].status == "completed"

        await engine.close()
    finally:
        from app.eval.providers import get_provider_class as real_get
        engine_module.get_provider_class = real_get


@pytest.mark.asyncio
async def test_engine_close(mock_api_client, mock_dataset_manager):
    engine = EvaluationEngine(
        api_client=mock_api_client,
        dataset_manager=mock_dataset_manager,
    )
    await engine.close()


@pytest.mark.asyncio
async def test_run_single_model_no_dataset(mock_api_client, mock_dataset_manager):
    engine = EvaluationEngine(
        api_client=mock_api_client,
        dataset_manager=mock_dataset_manager,
    )

    eval_no_dataset = Evaluation(
        id=uuid.uuid4(),
        name="no-dataset",
        evaluation_type="llm",
        dataset_id=None,
        status="queued",
        progress=0,
        priority="normal",
        timeout_seconds=3600,
        max_concurrency=5,
        config_snapshot={},
        created_by="test",
        created_at=dt.datetime.now(dt.timezone.utc),
    )

    with pytest.raises(ValueError, match="has no dataset_id"):
        await engine._run_single_model(
            evaluation=eval_no_dataset,
            model_config={
                "model_id": "test",
                "provider_id": "test",
            },
            records=[],
        )
    await engine.close()


@pytest.mark.asyncio
async def test_engine_close_with_providers(mock_api_client, mock_dataset_manager):
    """Test close() calls provider close()."""
    engine = EvaluationEngine(
        api_client=mock_api_client,
        dataset_manager=mock_dataset_manager,
    )

    fake_provider = AsyncMock()
    engine._providers["test:http://test"] = fake_provider

    await engine.close()
    fake_provider.close.assert_awaited_once()
    assert engine._providers == {}
    mock_dataset_manager.close.assert_awaited_once()
