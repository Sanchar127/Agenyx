from __future__ import annotations

from threading import Lock

from app.core.errors import ExecutionCancelled


class CancellationToken:
    """
    Cooperative cancellation signal for one Agent execution.

    The token is independent of asyncio so it can be checked at
    execution boundaries as well as from asynchronous operations.
    """

    def __init__(self) -> None:
        self._cancelled = False
        self._lock = Lock()

    @property
    def is_cancelled(self) -> bool:
        """
        Return True when cancellation has been requested.
        """
        with self._lock:
            return self._cancelled

    def cancel(self) -> None:
        """
        Mark this execution as cancelled.

        Calling cancel() multiple times is safe.
        """
        with self._lock:
            self._cancelled = True

    def raise_if_cancelled(self) -> None:
        """
        Raise ExecutionCancelled if cancellation was requested.
        """
        if self.is_cancelled:
            raise ExecutionCancelled(
                "Agent execution was cancelled"
            )
