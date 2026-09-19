from app.config import Settings


def test_providers_parse_in_priority_order():
    settings = Settings(
        provider_names="ollama-local, vllm-local, openai"
    )

    assert settings.providers == [
        "ollama-local",
        "vllm-local",
        "openai",
    ]


def test_model_definitions_parse():
    settings = Settings(
        model_definitions=(
            "qwen2.5:7b=ollama-local,"
            "llama3.2:3b=ollama-local"
        )
    )

    assert settings.models == [
        ("qwen2.5:7b", "ollama-local"),
        ("llama3.2:3b", "ollama-local"),
    ]


def test_model_definition_rejects_missing_provider_separator():
    settings = Settings(
        model_definitions="qwen2.5:7b"
    )

    try:
        settings.models
    except ValueError as exc:
        assert "expected 'model_id=provider_name'" in str(exc)
    else:
        raise AssertionError(
            "Expected invalid model definition to fail"
        )


def test_model_definition_rejects_empty_model():
    settings = Settings(
        model_definitions="=ollama-local"
    )

    try:
        settings.models
    except ValueError as exc:
        assert "empty model_id" in str(exc)
    else:
        raise AssertionError(
            "Expected empty model_id to fail"
        )


def test_model_definition_rejects_empty_provider():
    settings = Settings(
        model_definitions="qwen2.5:7b="
    )

    try:
        settings.models
    except ValueError as exc:
        assert "empty provider_name" in str(exc)
    else:
        raise AssertionError(
            "Expected empty provider_name to fail"
        )
def test_tenant_model_access_parse():
    settings = Settings(
        tenant_model_access=(
            "tenant-a=qwen2.5:7b,llama3.2:3b;"
            "tenant-b=llama3.2:3b"
        )
    )

    assert settings.tenant_models == {
        "tenant-a": frozenset({
            "qwen2.5:7b",
            "llama3.2:3b",
        }),
        "tenant-b": frozenset({
            "llama3.2:3b",
        }),
    }

def test_tenant_model_access_rejects_missing_separator():
    settings = Settings(
        tenant_model_access="tenant-a"
    )

    try:
        settings.tenant_models
    except ValueError as exc:
        assert "expected 'tenant_id=model1|model2'" in str(exc)
    else:
        raise AssertionError(
            "Expected invalid tenant model definition to fail"
        )


def test_tenant_model_access_rejects_empty_models():
    settings = Settings(
        tenant_model_access="tenant-a="
    )

    try:
        settings.tenant_models
    except ValueError as exc:
        assert "has no authorized models" in str(exc)
    else:
        raise AssertionError(
            "Expected empty tenant model access to fail"
        )
