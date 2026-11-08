"""Provider adapter registry for the Agenyx Evaluation Platform.

Maps provider IDs to provider adapter classes and provides lookup by ID.
"""

from app.eval.providers.base import EvaluationProvider
from app.eval.providers.ollama import OllamaProvider
from app.eval.providers.vllm import VLLMProvider
from app.eval.providers.openai import OpenAICompatibleProvider
from app.eval.providers.anthropic import AnthropicProvider

# Registry of provider ID -> provider class
PROVIDER_REGISTRY: dict[str, type[EvaluationProvider]] = {
    "ollama-local": OllamaProvider,
    "vllm-local": VLLMProvider,
    "openai-compatible": OpenAICompatibleProvider,
    "openai": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
}


def get_provider_class(provider_type: str) -> type[EvaluationProvider]:
    """Return the provider adapter class for a given provider type.

    Raises KeyError if the provider type is not registered.
    """
    if provider_type not in PROVIDER_REGISTRY:
        raise KeyError(f"Unknown provider type: {provider_type}")
    return PROVIDER_REGISTRY[provider_type]


def register_provider(
    provider_id: str,
    provider_class: type[EvaluationProvider],
) -> None:
    """Register a new provider adapter class (for extensibility)."""
    PROVIDER_REGISTRY[provider_id] = provider_class


def list_providers() -> list[str]:
    """Return all registered provider IDs."""
    return sorted(PROVIDER_REGISTRY.keys())
