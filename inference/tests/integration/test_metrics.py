import pytest

from app.metrics import (
    HTTP_ERRORS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
    INFERENCE_REQUEST_DURATION_SECONDS,
    INFERENCE_REQUESTS_IN_PROGRESS,
    INFERENCE_REQUESTS_TOTAL,
    PROVIDER_CIRCUIT_STATE,
    PROVIDER_CONSECUTIVE_FAILURES,
    PROVIDER_ERRORS_TOTAL,
    PROVIDER_HEALTH_STATE,
    PROVIDER_REQUEST_DURATION_SECONDS,
    PROVIDER_REQUESTS_TOTAL,
    PROVIDER_RETRIES_TOTAL,
    PROVIDER_TOTAL_FAILURES,
    PROVIDER_TOTAL_SUCCESSES,
)


# =========================================================
# METRIC DEFINITIONS
# =========================================================


def test_http_metrics_are_defined():
    assert HTTP_REQUESTS_TOTAL is not None
    assert HTTP_REQUEST_DURATION_SECONDS is not None
    assert HTTP_REQUESTS_IN_PROGRESS is not None
    assert HTTP_ERRORS_TOTAL is not None


def test_inference_metrics_are_defined():
    assert INFERENCE_REQUESTS_TOTAL is not None
    assert INFERENCE_REQUEST_DURATION_SECONDS is not None
    assert INFERENCE_REQUESTS_IN_PROGRESS is not None


def test_provider_metrics_are_defined():
    assert PROVIDER_REQUESTS_TOTAL is not None
    assert PROVIDER_REQUEST_DURATION_SECONDS is not None
    assert PROVIDER_RETRIES_TOTAL is not None
    assert PROVIDER_ERRORS_TOTAL is not None


def test_reliability_metrics_are_defined():
    assert PROVIDER_CIRCUIT_STATE is not None
    assert PROVIDER_HEALTH_STATE is not None
    assert PROVIDER_CONSECUTIVE_FAILURES is not None
    assert PROVIDER_TOTAL_FAILURES is not None
    assert PROVIDER_TOTAL_SUCCESSES is not None


# =========================================================
# HTTP METRICS
# =========================================================


def test_http_request_counter_can_be_incremented():
    labels = {
        "method": "GET",
        "route": "/unit-test",
        "status_code": "200",
    }

    before = HTTP_REQUESTS_TOTAL.labels(**labels)._value.get()

    HTTP_REQUESTS_TOTAL.labels(**labels).inc()

    after = HTTP_REQUESTS_TOTAL.labels(**labels)._value.get()

    assert after == before + 1


def test_http_error_counter_can_be_incremented():
    labels = {
        "method": "GET",
        "route": "/unit-test",
        "status_code": "500",
    }

    before = HTTP_ERRORS_TOTAL.labels(**labels)._value.get()

    HTTP_ERRORS_TOTAL.labels(**labels).inc()

    after = HTTP_ERRORS_TOTAL.labels(**labels)._value.get()

    assert after == before + 1


def test_http_in_progress_gauge_can_increment_and_decrement():
    labels = {
        "method": "GET",
        "route": "/unit-test",
    }

    gauge = HTTP_REQUESTS_IN_PROGRESS.labels(**labels)

    before = gauge._value.get()

    gauge.inc()

    assert gauge._value.get() == before + 1

    gauge.dec()

    assert gauge._value.get() == before


def test_http_duration_histogram_can_observe():
    labels = {
        "method": "GET",
        "route": "/unit-test",
    }

    histogram = HTTP_REQUEST_DURATION_SECONDS.labels(**labels)

    before = histogram._sum.get()

    histogram.observe(0.05)

    after = histogram._sum.get()

    assert after >= before + 0.05


# =========================================================
# INFERENCE METRICS
# =========================================================


def test_inference_request_counter_can_be_incremented():
    labels = {
        "provider": "unit-test-provider",
        "model": "unit-test-model",
        "status": "success",
    }

    before = INFERENCE_REQUESTS_TOTAL.labels(**labels)._value.get()

    INFERENCE_REQUESTS_TOTAL.labels(**labels).inc()

    after = INFERENCE_REQUESTS_TOTAL.labels(**labels)._value.get()

    assert after == before + 1


def test_inference_in_progress_gauge_can_increment_and_decrement():
    labels = {
        "provider": "unit-test-provider",
        "model": "unit-test-model",
    }

    gauge = INFERENCE_REQUESTS_IN_PROGRESS.labels(**labels)

    before = gauge._value.get()

    gauge.inc()

    assert gauge._value.get() == before + 1

    gauge.dec()

    assert gauge._value.get() == before


def test_inference_duration_histogram_can_observe():
    labels = {
        "provider": "unit-test-provider",
        "model": "unit-test-model",
    }

    histogram = INFERENCE_REQUEST_DURATION_SECONDS.labels(**labels)

    before = histogram._sum.get()

    histogram.observe(0.1)

    after = histogram._sum.get()

    assert after >= before + 0.1


# =========================================================
# PROVIDER METRICS
# =========================================================


def test_provider_request_counter_can_be_incremented():
    labels = {
        "provider": "unit-test-provider",
        "model": "unit-test-model",
        "status": "success",
    }

    before = PROVIDER_REQUESTS_TOTAL.labels(**labels)._value.get()

    PROVIDER_REQUESTS_TOTAL.labels(**labels).inc()

    after = PROVIDER_REQUESTS_TOTAL.labels(**labels)._value.get()

    assert after == before + 1


def test_provider_duration_histogram_can_observe():
    labels = {
        "provider": "unit-test-provider",
        "model": "unit-test-model",
    }

    histogram = PROVIDER_REQUEST_DURATION_SECONDS.labels(**labels)

    before = histogram._sum.get()

    histogram.observe(0.2)

    after = histogram._sum.get()

    assert after >= before + 0.2


def test_provider_retry_counter_can_be_incremented():
    labels = {
        "provider": "unit-test-provider",
        "model": "unit-test-model",
        "reason": "timeout",
    }

    before = PROVIDER_RETRIES_TOTAL.labels(**labels)._value.get()

    PROVIDER_RETRIES_TOTAL.labels(**labels).inc()

    after = PROVIDER_RETRIES_TOTAL.labels(**labels)._value.get()

    assert after == before + 1


def test_provider_error_counter_can_be_incremented():
    labels = {
        "provider": "unit-test-provider",
        "model": "unit-test-model",
        "error_type": "TimeoutError",
    }

    before = PROVIDER_ERRORS_TOTAL.labels(**labels)._value.get()

    PROVIDER_ERRORS_TOTAL.labels(**labels).inc()

    after = PROVIDER_ERRORS_TOTAL.labels(**labels)._value.get()

    assert after == before + 1


# =========================================================
# RELIABILITY METRICS
# =========================================================


def test_provider_circuit_state_gauge_can_be_set():
    gauge = PROVIDER_CIRCUIT_STATE.labels(
        provider="unit-test-provider",
    )

    gauge.set(0)

    assert gauge._value.get() == 0

    gauge.set(1)

    assert gauge._value.get() == 1


def test_provider_health_state_gauge_can_be_set():
    gauge = PROVIDER_HEALTH_STATE.labels(
        provider="unit-test-provider",
    )

    gauge.set(0)

    assert gauge._value.get() == 0

    gauge.set(2)

    assert gauge._value.get() == 2


def test_provider_consecutive_failures_gauge_can_be_set():
    gauge = PROVIDER_CONSECUTIVE_FAILURES.labels(
        provider="unit-test-provider",
    )

    gauge.set(3)

    assert gauge._value.get() == 3


def test_provider_total_failures_gauge_can_be_set():
    gauge = PROVIDER_TOTAL_FAILURES.labels(
        provider="unit-test-provider",
    )

    gauge.set(10)

    assert gauge._value.get() == 10


def test_provider_total_successes_gauge_can_be_set():
    gauge = PROVIDER_TOTAL_SUCCESSES.labels(
        provider="unit-test-provider",
    )

    gauge.set(20)

    assert gauge._value.get() == 20
