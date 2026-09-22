from unittest.mock import AsyncMock

import pytest

from app.failover.manager import FailoverManager
from app.providers.registry import ProviderRegistry
from app.reliability.manager import ReliabilityManager


class FakeProvider:
    def __init__(
        self,
        name: str,
        *,
        response: dict | None = None,
        error: Exception | None = None,
    ) -> None:
        self._name = name
        self.response = response or {
            "provider": name,
        }
        self.error = error
        self.chat_completion = AsyncMock(
            side_effect=self._chat_completion,
        )

    @property
    def name(self) -> str:
        return self._name

    async def _chat_completion(
        self,
        payload: dict,
    ) -> dict:
        if self.error is not None:
            raise self.error

        return self.response

    async def health(self) -> bool:
        return True

    async def close(self) -> None:
        return None


@pytest.fixture
def reliability() -> ReliabilityManager:
    return ReliabilityManager(
        degraded_failure_threshold=1,
        unhealthy_failure_threshold=3,
        recovery_timeout_seconds=10.0,
    )


def build_manager(
    providers: list[FakeProvider],
    reliability: ReliabilityManager,
    routes: dict[str, tuple[str, ...]],
    *,
    max_attempts: int = 3,
) -> FailoverManager:
    registry = ProviderRegistry()

    for provider in providers:
        registry.register(provider)
        reliability.register(provider.name)

    return FailoverManager(
        registry=registry,
        reliability=reliability,
        model_routes=routes,
        max_attempts=max_attempts,
    )


# =========================================================
# CONFIGURATION
# =========================================================


def test_rejects_empty_model_routes(
    reliability: ReliabilityManager,
):
    registry = ProviderRegistry()

    with pytest.raises(
        ValueError,
        match="model_routes must contain at least one model",
    ):
        FailoverManager(
            registry=registry,
            reliability=reliability,
            model_routes={},
        )


def test_rejects_invalid_max_attempts(
    reliability: ReliabilityManager,
):
    provider = FakeProvider("provider-a")
    registry = ProviderRegistry()
    registry.register(provider)
    reliability.register("provider-a")

    with pytest.raises(
        ValueError,
        match="max_attempts must be >= 1",
    ):
        FailoverManager(
            registry=registry,
            reliability=reliability,
            model_routes={
                "model-a": ("provider-a",),
            },
            max_attempts=0,
        )


def test_rejects_unknown_provider(
    reliability: ReliabilityManager,
):
    provider = FakeProvider("provider-a")
    registry = ProviderRegistry()
    registry.register(provider)
    reliability.register("provider-a")

    with pytest.raises(
        ValueError,
        match="references unregistered provider 'provider-b'",
    ):
        FailoverManager(
            registry=registry,
            reliability=reliability,
            model_routes={
                "model-a": ("provider-a", "provider-b"),
            },
        )


def test_rejects_unknown_model_route(
    reliability: ReliabilityManager,
):
    provider = FakeProvider("provider-a")

    manager = build_manager(
        [provider],
        reliability,
        {
            "model-a": ("provider-a",),
        },
    )

    with pytest.raises(
        KeyError,
        match="No failover route configured for model 'model-b'",
    ):
        await_completion(
            manager,
            {"model": "model-b"},
        )


# =========================================================
# SUCCESS
# =========================================================


@pytest.mark.asyncio
async def test_single_provider_success(
    reliability: ReliabilityManager,
):
    provider = FakeProvider(
        "provider-a",
        response={"id": "response-a"},
    )

    manager = build_manager(
        [provider],
        reliability,
        {
            "model-a": ("provider-a",),
        },
    )

    result = await manager.chat_completion(
        {"model": "model-a"},
    )

    assert result.response == {"id": "response-a"}
    assert result.provider == "provider-a"
    assert len(result.attempts) == 1
    assert result.attempts[0].success is True
    provider.chat_completion.assert_awaited_once_with(
        {"model": "model-a"},
    )


# =========================================================
# FAILOVER
# =========================================================


@pytest.mark.asyncio
async def test_first_provider_failure_second_provider_success(
    reliability: ReliabilityManager,
):
    provider_a = FakeProvider(
        "provider-a",
        error=RuntimeError("provider-a failed"),
    )
    provider_b = FakeProvider(
        "provider-b",
        response={"id": "response-b"},
    )

    manager = build_manager(
        [provider_a, provider_b],
        reliability,
        {
            "model-a": ("provider-a", "provider-b"),
        },
    )

    result = await manager.chat_completion(
        {"model": "model-a"},
    )

    assert result.response == {"id": "response-b"}
    assert result.provider == "provider-b"

    assert [
        attempt.provider
        for attempt in result.attempts
    ] == ["provider-a", "provider-b"]

    assert result.attempts[0].success is False
    assert result.attempts[0].error == "provider-a failed"
    assert result.attempts[1].success is True

    provider_a.chat_completion.assert_awaited_once()
    provider_b.chat_completion.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_providers_fail(
    reliability: ReliabilityManager,
):
    provider_a = FakeProvider(
        "provider-a",
        error=RuntimeError("failure-a"),
    )
    provider_b = FakeProvider(
        "provider-b",
        error=RuntimeError("failure-b"),
    )

    manager = build_manager(
        [provider_a, provider_b],
        reliability,
        {
            "model-a": ("provider-a", "provider-b"),
        },
    )

    with pytest.raises(
        RuntimeError,
        match="All failover providers failed for model 'model-a'",
    ) as exc_info:
        await manager.chat_completion(
            {"model": "model-a"},
        )

    assert isinstance(
        exc_info.value.__cause__,
        RuntimeError,
    )
    assert str(exc_info.value.__cause__) == "failure-b"

    provider_a.chat_completion.assert_awaited_once()
    provider_b.chat_completion.assert_awaited_once()


# =========================================================
# MODEL-SPECIFIC ROUTING
# =========================================================


@pytest.mark.asyncio
async def test_model_specific_routes(
    reliability: ReliabilityManager,
):
    provider_a = FakeProvider(
        "provider-a",
        response={"provider": "a"},
    )
    provider_b = FakeProvider(
        "provider-b",
        response={"provider": "b"},
    )
    provider_c = FakeProvider(
        "provider-c",
        response={"provider": "c"},
    )

    manager = build_manager(
        [provider_a, provider_b, provider_c],
        reliability,
        {
            "model-a": ("provider-a", "provider-b"),
            "model-b": ("provider-c",),
        },
    )

    result_a = await manager.chat_completion(
        {"model": "model-a"},
    )

    result_b = await manager.chat_completion(
        {"model": "model-b"},
    )

    assert result_a.provider == "provider-a"
    assert result_b.provider == "provider-c"

    provider_a.chat_completion.assert_awaited_once()
    provider_b.chat_completion.assert_not_awaited()
    provider_c.chat_completion.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_cross_model_fallback(
    reliability: ReliabilityManager,
):
    provider_a = FakeProvider(
        "provider-a",
        error=RuntimeError("model-a provider failed"),
    )
    provider_b = FakeProvider(
        "provider-b",
        response={"provider": "b"},
    )
    provider_c = FakeProvider(
        "provider-c",
        response={"provider": "c"},
    )

    manager = build_manager(
        [provider_a, provider_b, provider_c],
        reliability,
        {
            "model-a": ("provider-a", "provider-b"),
            "model-b": ("provider-c",),
        },
    )

    result = await manager.chat_completion(
        {"model": "model-a"},
    )

    assert result.provider == "provider-b"

    provider_a.chat_completion.assert_awaited_once()
    provider_b.chat_completion.assert_awaited_once()
    provider_c.chat_completion.assert_not_awaited()


# =========================================================
# ORDERING
# =========================================================


@pytest.mark.asyncio
async def test_provider_order_is_preserved(
    reliability: ReliabilityManager,
):
    calls: list[str] = []

    provider_a = FakeProvider(
        "provider-a",
        error=RuntimeError("failure-a"),
    )
    provider_b = FakeProvider(
        "provider-b",
        error=RuntimeError("failure-b"),
    )
    provider_c = FakeProvider(
        "provider-c",
        response={"provider": "c"},
    )

    async def record_a(payload: dict) -> dict:
        calls.append("provider-a")
        raise RuntimeError("failure-a")

    async def record_b(payload: dict) -> dict:
        calls.append("provider-b")
        raise RuntimeError("failure-b")

    async def record_c(payload: dict) -> dict:
        calls.append("provider-c")
        return {"provider": "c"}

    provider_a.chat_completion.side_effect = record_a
    provider_b.chat_completion.side_effect = record_b
    provider_c.chat_completion.side_effect = record_c

    manager = build_manager(
        [provider_a, provider_b, provider_c],
        reliability,
        {
            "model-a": (
                "provider-a",
                "provider-b",
                "provider-c",
            ),
        },
    )

    result = await manager.chat_completion(
        {"model": "model-a"},
    )

    assert result.provider == "provider-c"
    assert calls == [
        "provider-a",
        "provider-b",
        "provider-c",
    ]


# =========================================================
# ATTEMPT LIMIT
# =========================================================


@pytest.mark.asyncio
async def test_max_attempts_limits_provider_calls(
    reliability: ReliabilityManager,
):
    provider_a = FakeProvider(
        "provider-a",
        error=RuntimeError("failure-a"),
    )
    provider_b = FakeProvider(
        "provider-b",
        error=RuntimeError("failure-b"),
    )
    provider_c = FakeProvider(
        "provider-c",
        response={"provider": "c"},
    )

    manager = build_manager(
        [provider_a, provider_b, provider_c],
        reliability,
        {
            "model-a": (
                "provider-a",
                "provider-b",
                "provider-c",
            ),
        },
        max_attempts=2,
    )

    with pytest.raises(
        RuntimeError,
        match="All failover providers failed",
    ):
        await manager.chat_completion(
            {"model": "model-a"},
        )

    provider_a.chat_completion.assert_awaited_once()
    provider_b.chat_completion.assert_awaited_once()
    provider_c.chat_completion.assert_not_awaited()


# =========================================================
# CIRCUIT BREAKER
# =========================================================


@pytest.mark.asyncio
async def test_open_circuit_is_skipped(
    reliability: ReliabilityManager,
):
    provider_a = FakeProvider(
        "provider-a",
        response={"provider": "a"},
    )
    provider_b = FakeProvider(
        "provider-b",
        response={"provider": "b"},
    )

    manager = build_manager(
        [provider_a, provider_b],
        reliability,
        {
            "model-a": (
                "provider-a",
                "provider-b",
            ),
        },
    )

    for _ in range(3):
        reliability.record_failure("provider-a")

    result = await manager.chat_completion(
        {"model": "model-a"},
    )

    assert result.provider == "provider-b"

    provider_a.chat_completion.assert_not_awaited()
    provider_b.chat_completion.assert_awaited_once()

    assert result.attempts[0].provider == "provider-a"
    assert result.attempts[0].success is False
    assert result.attempts[0].error == "Provider circuit is open"


# =========================================================
# PAYLOAD VALIDATION
# =========================================================


@pytest.mark.asyncio
async def test_missing_model_rejected(
    reliability: ReliabilityManager,
):
    provider = FakeProvider("provider-a")

    manager = build_manager(
        [provider],
        reliability,
        {
            "model-a": ("provider-a",),
        },
    )

    with pytest.raises(
        ValueError,
        match="non-empty string 'model'",
    ):
        await manager.chat_completion({})


@pytest.mark.asyncio
async def test_empty_model_rejected(
    reliability: ReliabilityManager,
):
    provider = FakeProvider("provider-a")

    manager = build_manager(
        [provider],
        reliability,
        {
            "model-a": ("provider-a",),
        },
    )

    with pytest.raises(
        ValueError,
        match="non-empty string 'model'",
    ):
        await manager.chat_completion(
            {"model": ""},
        )


def await_completion(
    manager: FailoverManager,
    payload: dict,
):
    """Helper used by the synchronous unknown-model test."""

    import asyncio

    return asyncio.run(
        manager.chat_completion(payload),
    )
