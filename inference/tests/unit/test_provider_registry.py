
from unittest.mock import AsyncMock

import pytest

from app.providers.registry import ProviderRegistry


class FakeProvider:
    def __init__(
        self,
        name: str,
        healthy: bool = True,
    ) -> None:
        self._name = name
        self._healthy = healthy
        self.close = AsyncMock()

    @property
    def name(self) -> str:
        return self._name

    async def chat_completion(self, payload):
        return {"ok": True}

    async def health(self) -> bool:
        return self._healthy


# =========================================================
# REGISTER
# =========================================================


def test_register_provider():
    registry = ProviderRegistry()

    provider = FakeProvider("provider-a")

    registry.register(provider)

    assert registry.get("provider-a") is provider


def test_register_duplicate_provider_raises():
    registry = ProviderRegistry()

    provider = FakeProvider("provider-a")

    registry.register(provider)

    with pytest.raises(
        ValueError,
        match="Provider already registered",
    ):
        registry.register(provider)


# =========================================================
# GET
# =========================================================


def test_get_unknown_provider_raises():
    registry = ProviderRegistry()

    with pytest.raises(
        KeyError,
        match="Unknown provider",
    ):
        registry.get("missing-provider")


def test_get_error_lists_available_providers():
    registry = ProviderRegistry()

    registry.register(
        FakeProvider("provider-b")
    )

    registry.register(
        FakeProvider("provider-a")
    )

    with pytest.raises(
        KeyError,
        match="Available providers: provider-a, provider-b",
    ):
        registry.get("missing-provider")


# =========================================================
# LIST
# =========================================================


def test_list_returns_sorted_provider_names():
    registry = ProviderRegistry()

    registry.register(
        FakeProvider("provider-c")
    )

    registry.register(
        FakeProvider("provider-a")
    )

    registry.register(
        FakeProvider("provider-b")
    )

    assert registry.list() == [
        "provider-a",
        "provider-b",
        "provider-c",
    ]


def test_list_empty_registry():
    registry = ProviderRegistry()

    assert registry.list() == []


# =========================================================
# HEALTH
# =========================================================


@pytest.mark.asyncio
async def test_health_returns_provider_health():
    registry = ProviderRegistry()

    registry.register(
        FakeProvider(
            "healthy-provider",
            healthy=True,
        )
    )

    registry.register(
        FakeProvider(
            "unhealthy-provider",
            healthy=False,
        )
    )

    result = await registry.health()

    assert result == {
        "healthy-provider": True,
        "unhealthy-provider": False,
    }


@pytest.mark.asyncio
async def test_health_empty_registry():
    registry = ProviderRegistry()

    result = await registry.health()

    assert result == {}


# =========================================================
# CLOSE
# =========================================================


@pytest.mark.asyncio
async def test_close_closes_all_providers():
    registry = ProviderRegistry()

    provider_a = FakeProvider("provider-a")
    provider_b = FakeProvider("provider-b")

    registry.register(provider_a)
    registry.register(provider_b)

    await registry.close()

    provider_a.close.assert_awaited_once()
    provider_b.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_empty_registry():
    registry = ProviderRegistry()

    await registry.close()
