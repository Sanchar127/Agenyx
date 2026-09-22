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

def test_provider_backends_parse():
    settings = Settings(
        provider_backends=(
            "ollama-local=http://localhost:11434/v1|ollama,"
            "vllm-local=http://localhost:8001/v1|vllm-key"
        )
    )

    assert settings.provider_backend_configs == {
        "ollama-local": {
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
        },
        "vllm-local": {
            "base_url": "http://localhost:8001/v1",
            "api_key": "vllm-key",
        },
    }


def test_provider_backends_parse_without_api_key():
    settings = Settings(
        provider_backends=(
            "ollama-local=http://localhost:11434/v1|,"
            "vllm-local=http://localhost:8001/v1|"
        )
    )

    assert settings.provider_backend_configs == {
        "ollama-local": {
            "base_url": "http://localhost:11434/v1",
            "api_key": "",
        },
        "vllm-local": {
            "base_url": "http://localhost:8001/v1",
            "api_key": "",
        },
    }


def test_provider_backends_reject_missing_separator():
    settings = Settings(
        provider_backends="ollama-local"
    )

    try:
        settings.provider_backend_configs
    except ValueError as exc:
        assert "expected 'provider_name=base_url|api_key'" in str(exc)
    else:
        raise AssertionError(
            "Expected invalid provider backend definition to fail"
        )


def test_provider_backends_reject_empty_provider():
    settings = Settings(
        provider_backends="=http://localhost:11434/v1|ollama"
    )

    try:
        settings.provider_backend_configs
    except ValueError as exc:
        assert "empty provider_name" in str(exc)
    else:
        raise AssertionError(
            "Expected empty provider name to fail"
        )


def test_provider_backends_reject_empty_base_url():
    settings = Settings(
        provider_backends="ollama-local=|ollama"
    )

    try:
        settings.provider_backend_configs
    except ValueError as exc:
        assert "empty base_url" in str(exc)
    else:
        raise AssertionError(
            "Expected empty provider base URL to fail"
        )


def test_model_failover_routes_parse():
    settings = Settings(
        model_failover_routes=(
            "qwen2.5:7b=ollama-local,vllm-local;"
            "llama3.2:3b=ollama-local,vllm-local"
        )
    )

    assert settings.model_failover_providers == {
        "qwen2.5:7b": (
            "ollama-local",
            "vllm-local",
        ),
        "llama3.2:3b": (
            "ollama-local",
            "vllm-local",
        ),
    }


def test_model_failover_routes_reject_missing_separator():
    settings = Settings(
        model_failover_routes="qwen2.5:7b"
    )

    try:
        settings.model_failover_providers
    except ValueError as exc:
        assert "expected 'model_id=provider1,provider2'" in str(exc)
    else:
        raise AssertionError(
            "Expected invalid model failover route to fail"
        )


def test_model_failover_routes_reject_empty_model():
    settings = Settings(
        model_failover_routes="=ollama-local,vllm-local"
    )

    try:
        settings.model_failover_providers
    except ValueError as exc:
        assert "empty model_id" in str(exc)
    else:
        raise AssertionError(
            "Expected empty model ID to fail"
        )


def test_model_failover_routes_reject_empty_providers():
    settings = Settings(
        model_failover_routes="qwen2.5:7b="
    )

    try:
        settings.model_failover_providers
    except ValueError as exc:
        assert "has no providers" in str(exc)
    else:
        raise AssertionError(
            "Expected empty provider list to fail"
        )
