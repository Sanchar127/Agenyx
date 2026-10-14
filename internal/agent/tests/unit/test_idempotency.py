from __future__ import annotations

import asyncio

import pytest

from app.agent_runtime.idempotency import (
    IdempotencyRecord,
    InMemoryIdempotencyStore,
)


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_key() -> None:
    store = InMemoryIdempotencyStore()

    result = await store.get("unknown-key")

    assert result is None


@pytest.mark.asyncio
async def test_claim_succeeds_for_new_key() -> None:
    store = InMemoryIdempotencyStore()

    claimed = await store.claim("key-1")

    assert claimed is True


@pytest.mark.asyncio
async def test_claim_fails_for_already_claimed_key() -> None:
    store = InMemoryIdempotencyStore()

    first_claim = await store.claim("key-1")
    second_claim = await store.claim("key-1")

    assert first_claim is True
    assert second_claim is False


@pytest.mark.asyncio
async def test_put_stores_result() -> None:
    store = InMemoryIdempotencyStore()

    await store.claim("key-1")

    record = IdempotencyRecord(
        key="key-1",
        result={"success": True},
    )

    await store.put(record)

    result = await store.get("key-1")

    assert result is not None
    assert result.key == "key-1"
    assert result.result == {"success": True}


@pytest.mark.asyncio
async def test_completed_key_cannot_be_claimed_again() -> None:
    store = InMemoryIdempotencyStore()

    await store.claim("key-1")

    await store.put(
        IdempotencyRecord(
            key="key-1",
            result="completed",
        )
    )

    claimed = await store.claim("key-1")

    assert claimed is False


@pytest.mark.asyncio
async def test_release_allows_key_to_be_claimed_again() -> None:
    store = InMemoryIdempotencyStore()

    first_claim = await store.claim("key-1")

    await store.release("key-1")

    second_claim = await store.claim("key-1")

    assert first_claim is True
    assert second_claim is True


@pytest.mark.asyncio
async def test_release_does_not_delete_completed_result() -> None:
    store = InMemoryIdempotencyStore()

    await store.claim("key-1")

    record = IdempotencyRecord(
        key="key-1",
        result="completed",
    )

    await store.put(record)
    await store.release("key-1")

    result = await store.get("key-1")

    assert result is not None
    assert result.result == "completed"


@pytest.mark.asyncio
async def test_concurrent_claim_only_allows_one_caller() -> None:
    store = InMemoryIdempotencyStore()

    results = await asyncio.gather(
        store.claim("same-key"),
        store.claim("same-key"),
        store.claim("same-key"),
        store.claim("same-key"),
        store.claim("same-key"),
    )

    assert results.count(True) == 1
    assert results.count(False) == 4
