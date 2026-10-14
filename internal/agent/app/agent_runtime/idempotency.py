from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IdempotencyRecord:
    """
    Stores the result of a completed idempotent operation.
    """

    key: str
    result: Any


class IdempotencyStore:
    """
    Abstraction for storing idempotency records.
    """

    async def get(
        self,
        key: str,
    ) -> IdempotencyRecord | None:
        raise NotImplementedError

    async def claim(
        self,
        key: str,
    ) -> bool:
        raise NotImplementedError

    async def put(
        self,
        record: IdempotencyRecord,
    ) -> None:
        raise NotImplementedError

    async def release(
        self,
        key: str,
    ) -> None:
        raise NotImplementedError

    async def wait(
        self,
        key: str,
    ) -> IdempotencyRecord:
        raise NotImplementedError


class InMemoryIdempotencyStore(IdempotencyStore):
    """
    In-memory idempotency store.

    Used to establish and test idempotency semantics.
    """

    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}
        self._claimed: set[str] = set()
        self._events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    async def get(
        self,
        key: str,
    ) -> IdempotencyRecord | None:
        async with self._lock:
            return self._records.get(key)

    async def claim(
        self,
        key: str,
    ) -> bool:
        """
        Atomically claim a key.

        Returns True if this caller owns execution.

        Returns False if another caller already owns or
        completed the operation.
        """

        async with self._lock:
            if key in self._claimed:
                return False

            if key in self._records:
                return False

            self._claimed.add(key)
            self._events[key] = asyncio.Event()

            return True

    async def put(
        self,
        record: IdempotencyRecord,
    ) -> None:
        async with self._lock:
            self._records[record.key] = record
            self._claimed.discard(record.key)

            event = self._events.get(record.key)

            if event is not None:
                event.set()

    async def release(
        self,
        key: str,
    ) -> None:
        async with self._lock:
            self._claimed.discard(key)

            event = self._events.get(key)

            if event is not None:
                event.set()

    async def wait(
        self,
        key: str,
    ) -> IdempotencyRecord:
        """
        Wait for another caller to finish the operation.
        """

        async with self._lock:
            record = self._records.get(key)

            if record is not None:
                return record

            event = self._events.get(key)

            if event is None:
                raise RuntimeError(
                    f"No in-flight operation exists for key: {key}"
                )

        await event.wait()

        async with self._lock:
            record = self._records.get(key)

            if record is None:
                raise RuntimeError(
                    f"Idempotency operation did not produce "
                    f"a result for key: {key}"
                )

            return record
