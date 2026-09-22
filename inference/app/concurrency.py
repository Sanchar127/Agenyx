class InferenceConcurrencyLimiter:
    """Non-blocking concurrency limiter for inference execution."""

    def __init__(self, max_concurrency: int) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")

        self._max_concurrency = max_concurrency
        self._active = 0

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    @property
    def active(self) -> int:
        return self._active

    def try_acquire(self) -> bool:
        """Acquire a slot without waiting."""
        if self._active >= self._max_concurrency:
            return False

        self._active += 1
        return True

    def release(self) -> None:
        """Release a previously acquired slot."""
        if self._active <= 0:
            raise RuntimeError(
                "Cannot release an unacquired concurrency slot"
            )

        self._active -= 1
