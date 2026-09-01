import pytest

from app.models import ModelDefinition, ModelRegistry


def test_register_and_get_model():
    registry = ModelRegistry()

    model = ModelDefinition(
        model_id="qwen2.5:7b",
        provider_name="ollama-local",
    )

    registry.register(model)

    result = registry.get("qwen2.5:7b")

    assert result == model
    assert result.model_id == "qwen2.5:7b"
    assert result.provider_name == "ollama-local"


def test_duplicate_model_registration_fails():
    registry = ModelRegistry()

    model = ModelDefinition(
        model_id="qwen2.5:7b",
        provider_name="ollama-local",
    )

    registry.register(model)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(model)


def test_unknown_model_fails():
    registry = ModelRegistry()

    with pytest.raises(
        KeyError,
        match="Model is not registered",
    ):
        registry.get("does-not-exist")


def test_empty_model_id_fails():
    registry = ModelRegistry()

    model = ModelDefinition(
        model_id="",
        provider_name="ollama-local",
    )

    with pytest.raises(
        ValueError,
        match="model_id must not be empty",
    ):
        registry.register(model)


def test_empty_provider_name_fails():
    registry = ModelRegistry()

    model = ModelDefinition(
        model_id="qwen2.5:7b",
        provider_name="",
    )

    with pytest.raises(
        ValueError,
        match="provider_name must not be empty",
    ):
        registry.register(model)


def test_model_exists():
    registry = ModelRegistry()

    registry.register(
        ModelDefinition(
            model_id="qwen2.5:7b",
            provider_name="ollama-local",
        )
    )

    assert registry.exists("qwen2.5:7b")
    assert not registry.exists("missing")


def test_remove_model():
    registry = ModelRegistry()

    registry.register(
        ModelDefinition(
            model_id="qwen2.5:7b",
            provider_name="ollama-local",
        )
    )

    registry.remove("qwen2.5:7b")

    assert not registry.exists("qwen2.5:7b")
    assert registry.count() == 0


def test_list_models():
    registry = ModelRegistry()

    registry.register(
        ModelDefinition(
            model_id="qwen2.5:7b",
            provider_name="ollama-local",
        )
    )

    registry.register(
        ModelDefinition(
            model_id="llama3.2:3b",
            provider_name="ollama-local",
        )
    )

    models = registry.list_models()

    assert len(models) == 2
    assert {
        model.model_id
        for model in models
    } == {
        "qwen2.5:7b",
        "llama3.2:3b",
    }
