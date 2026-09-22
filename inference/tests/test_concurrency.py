import pytest

from app.concurrency import InferenceConcurrencyLimiter


def test_acquire_until_limit():
    limiter = InferenceConcurrencyLimiter(2)

    assert limiter.try_acquire() is True
    assert limiter.active == 1

    assert limiter.try_acquire() is True
    assert limiter.active == 2

    assert limiter.try_acquire() is False
    assert limiter.active == 2


def test_release_allows_new_request():
    limiter = InferenceConcurrencyLimiter(1)

    assert limiter.try_acquire() is True
    assert limiter.try_acquire() is False

    limiter.release()

    assert limiter.active == 0
    assert limiter.try_acquire() is True


def test_release_without_acquire_raises():
    limiter = InferenceConcurrencyLimiter(1)

    with pytest.raises(RuntimeError, match="unacquired"):
        limiter.release()


@pytest.mark.parametrize("max_concurrency", [0, -1])
def test_invalid_limit(max_concurrency):
    with pytest.raises(ValueError, match="at least 1"):
        InferenceConcurrencyLimiter(max_concurrency)
