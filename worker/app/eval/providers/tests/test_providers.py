"""Unit tests for evaluation provider adapters."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.eval.providers.base import EvaluationProvider
from app.eval.providers.ollama import OllamaProvider
from app.eval.providers.vllm import VLLMProvider
from app.eval.providers.openai import OpenAICompatibleProvider
from app.eval.providers.anthropic import AnthropicProvider
from app.eval.providers import get_provider_class, list_providers, register_provider


def test_provider_base_is_abstract():
    """EvaluationProvider cannot be instantiated directly."""
    with pytest.raises(TypeError):
        EvaluationProvider()


def test_ollama_provider_properties():
    provider = OllamaProvider(
        provider_id="ollama-local",
        endpoint_url="http://ollama:11434/v1",
        api_key="",
        timeout=60.0,
    )
    assert provider.provider_id == "ollama-local"
    assert provider.provider_type == "ollama"
    assert provider.endpoint_url == "http://ollama:11434/v1"


def test_vllm_provider_properties():
    provider = VLLMProvider(
        provider_id="vllm-local",
        endpoint_url="http://vllm:8000/v1",
        api_key="",
        timeout=60.0,
    )
    assert provider.provider_id == "vllm-local"
    assert provider.provider_type == "vllm"
    assert provider.endpoint_url == "http://vllm:8000/v1"


def test_openai_provider_properties():
    provider = OpenAICompatibleProvider(
        provider_id="openai-cloud",
        endpoint_url="https://api.openai.com/v1",
        api_key="sk-test",
        timeout=60.0,
    )
    assert provider.provider_id == "openai-cloud"
    assert provider.provider_type == "openai-compatible"
    assert provider.endpoint_url == "https://api.openai.com/v1"


def test_anthropic_provider_properties():
    provider = AnthropicProvider(
        provider_id="anthropic",
        endpoint_url="https://api.anthropic.com/v1",
        api_key="sk-ant-test",
        timeout=60.0,
    )
    assert provider.provider_id == "anthropic"
    assert provider.provider_type == "anthropic"
    assert provider.endpoint_url == "https://api.anthropic.com/v1"


def test_provider_registry_list():
    providers = list_providers()
    assert "ollama-local" in providers
    assert "vllm-local" in providers
    assert "openai-compatible" in providers
    assert "anthropic" in providers


def test_get_provider_class():
    cls = get_provider_class("ollama-local")
    assert cls is OllamaProvider
    cls = get_provider_class("anthropic")
    assert cls is AnthropicProvider


def test_get_provider_class_unknown():
    with pytest.raises(KeyError, match="Unknown provider type"):
        get_provider_class("nonexistent-provider")


def test_register_provider():
    class MyProvider(EvaluationProvider):
        @property
        def provider_id(self) -> str:
            return "my-provider"

        @property
        def provider_type(self) -> str:
            return "custom"

        @property
        def endpoint_url(self) -> str:
            return "http://example.com/v1"

        async def chat_completion(self, **kwargs):
            return {}

        async def embedding(self, **kwargs):
            return {}

        async def health(self) -> bool:
            return True

        async def close(self) -> None:
            pass

    register_provider("my-provider", MyProvider)
    assert get_provider_class("my-provider") is MyProvider


@pytest.mark.asyncio
async def test_ollama_chat_completion():
    provider = OllamaProvider(
        provider_id="ollama-local",
        endpoint_url="http://ollama:11434/v1",
        api_key="",
        timeout=10.0,
    )
    provider._client.post = AsyncMock(
        return_value=MagicMock(
            status_code=200,
            json=lambda: {
                "id": "chatcmpl-123",
                "model": "qwen2.5:7b",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hello!"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10},
            },
        )
    )
    response = await provider.chat_completion(
        model="qwen2.5:7b",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.2,
    )
    assert response["model"] == "qwen2.5:7b"
    assert response["choices"][0]["message"]["content"] == "Hello!"
    await provider.close()


@pytest.mark.asyncio
async def test_openai_chat_completion():
    provider = OpenAICompatibleProvider(
        provider_id="openai-cloud",
        endpoint_url="https://api.openai.com/v1",
        api_key="sk-test",
        timeout=10.0,
    )
    provider._client.post = AsyncMock(
        return_value=MagicMock(
            status_code=200,
            json=lambda: {
                "id": "chatcmpl-456",
                "model": "gpt-4",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hi!"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 8},
            },
        )
    )
    response = await provider.chat_completion(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hi"}],
    )
    assert response["choices"][0]["message"]["content"] == "Hi!"
    await provider.close()


@pytest.mark.asyncio
async def test_anthropic_chat_completion():
    provider = AnthropicProvider(
        provider_id="anthropic",
        endpoint_url="https://api.anthropic.com/v1",
        api_key="sk-ant-test",
        timeout=10.0,
    )
    provider._client.post = AsyncMock(
        return_value=MagicMock(
            status_code=200,
            json=lambda: {
                "id": "msg_123",
                "model": "claude-3-haiku-20240307",
                "content": [
                    {"type": "text", "text": "Anthropic response!"}
                ],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 8},
            },
        )
    )
    response = await provider.chat_completion(
        model="claude-3-haiku-20240307",
        messages=[{"role": "user", "content": "Hello"}],
    )
    assert response["choices"][0]["message"]["content"] == "Anthropic response!"
    await provider.close()


@pytest.mark.asyncio
async def test_anthropic_embedding_not_implemented():
    provider = AnthropicProvider(
        provider_id="anthropic",
        endpoint_url="https://api.anthropic.com/v1",
        api_key="sk-ant-test",
    )
    with pytest.raises(NotImplementedError):
        await provider.embedding(model="claude-3-haiku-20240307", input=["test"])
    await provider.close()


@pytest.mark.asyncio
async def test_provider_health_true():
    provider = OllamaProvider(
        provider_id="ollama-local",
        endpoint_url="http://ollama:11434/v1",
        api_key="",
    )
    provider._client.get = AsyncMock(return_value=MagicMock(status_code=200))
    assert await provider.health() is True
    await provider.close()


@pytest.mark.asyncio
async def test_provider_health_false():
    provider = OllamaProvider(
        provider_id="ollama-local",
        endpoint_url="http://ollama:11434/v1",
        api_key="",
    )
    provider._client.get = AsyncMock(side_effect=Exception("connection error"))
    assert await provider.health() is False
    await provider.close()
