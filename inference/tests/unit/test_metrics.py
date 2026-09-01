from fastapi.testclient import TestClient

from app.main import app


# =========================================================
# CLIENT
# =========================================================


client = TestClient(app)


# =========================================================
# HELPERS
# =========================================================


def get_metric_value(
    metrics_text: str,
    metric_name: str,
    labels: dict[str, str] | None = None,
) -> float:
    """
    Extract a metric value from Prometheus exposition text.

    Example:

        metric_name{method="GET",route="/health",status_code="200"} 5.0
    """

    for line in metrics_text.splitlines():
        if not line.startswith(metric_name):
            continue

        if labels:
            for key, value in labels.items():
                expected = f'{key}="{value}"'

                if expected not in line:
                    break
            else:
                return float(line.rsplit(" ", 1)[1])

        else:
            return float(line.rsplit(" ", 1)[1])

    return 0.0


# =========================================================
# METRICS ENDPOINT
# =========================================================


def test_metrics_endpoint_returns_200():
    response = client.get("/metrics")

    assert response.status_code == 200


def test_metrics_endpoint_returns_prometheus_content_type():
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


def test_metrics_endpoint_contains_http_metrics():
    response = client.get("/metrics")

    body = response.text

    assert "agenyx_inference_http_requests_total" in body
    assert (
        "agenyx_inference_http_request_duration_seconds"
        in body
    )
    assert (
        "agenyx_inference_http_requests_in_progress"
        in body
    )
    assert "agenyx_inference_http_errors_total" in body


def test_metrics_endpoint_contains_inference_metrics():
    response = client.get("/metrics")

    body = response.text

    assert "agenyx_inference_requests_total" in body
    assert (
        "agenyx_inference_request_duration_seconds"
        in body
    )
    assert (
        "agenyx_inference_requests_in_progress"
        in body
    )


def test_metrics_endpoint_contains_provider_metrics():
    response = client.get("/metrics")

    body = response.text

    assert "agenyx_inference_provider_requests_total" in body
    assert (
        "agenyx_inference_provider_request_duration_seconds"
        in body
    )
    assert "agenyx_inference_provider_retries_total" in body
    assert "agenyx_inference_provider_errors_total" in body


def test_metrics_endpoint_contains_reliability_metrics():
    response = client.get("/metrics")

    body = response.text

    assert "agenyx_inference_provider_circuit_state" in body
    assert "agenyx_inference_provider_health_state" in body
    assert (
        "agenyx_inference_provider_consecutive_failures"
        in body
    )
    assert "agenyx_inference_provider_total_failures" in body
    assert "agenyx_inference_provider_total_successes" in body


# =========================================================
# HTTP REQUEST METRICS
# =========================================================


def test_health_request_increments_http_counter():
    before_response = client.get("/metrics")

    before = get_metric_value(
        before_response.text,
        "agenyx_inference_http_requests_total",
        {
            "method": "GET",
            "route": "/health",
            "status_code": "200",
        },
    )

    response = client.get("/health")

    assert response.status_code == 200

    after_response = client.get("/metrics")

    after = get_metric_value(
        after_response.text,
        "agenyx_inference_http_requests_total",
        {
            "method": "GET",
            "route": "/health",
            "status_code": "200",
        },
    )

    assert after >= before + 1


def test_health_request_records_duration():
    response = client.get("/metrics")

    before = get_metric_value(
        response.text,
        "agenyx_inference_http_request_duration_seconds_count",
        {
            "method": "GET",
            "route": "/health",
        },
    )

    health_response = client.get("/health")

    assert health_response.status_code == 200

    response = client.get("/metrics")

    after = get_metric_value(
        response.text,
        "agenyx_inference_http_request_duration_seconds_count",
        {
            "method": "GET",
            "route": "/health",
        },
    )

    assert after >= before + 1


def test_in_progress_requests_return_to_zero():
    response = client.get("/health")

    assert response.status_code == 200

    metrics_response = client.get("/metrics")

    value = get_metric_value(
        metrics_response.text,
        "agenyx_inference_http_requests_in_progress",
        {
            "method": "GET",
            "route": "/health",
        },
    )

    assert value == 0


# =========================================================
# HTTP ERROR METRICS
# =========================================================


def test_404_request_increments_http_error_counter():
    before_response = client.get("/metrics")

    before = get_metric_value(
        before_response.text,
        "agenyx_inference_http_errors_total",
        {
            "method": "GET",
            "route": "/does-not-exist",
            "status_code": "404",
        },
    )

    response = client.get("/does-not-exist")

    assert response.status_code == 404

    after_response = client.get("/metrics")

    after = get_metric_value(
        after_response.text,
        "agenyx_inference_http_errors_total",
        {
            "method": "GET",
            "route": "/does-not-exist",
            "status_code": "404",
        },
    )

    assert after >= before + 1


# =========================================================
# APPLICATION HEALTH
# =========================================================


def test_health_endpoint_still_works():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }


def test_models_endpoint_still_works():
    response = client.get("/v1/models")

    assert response.status_code == 200

    body = response.json()

    assert body["object"] == "list"
    assert "data" in body
    assert isinstance(body["data"], list)


def test_providers_endpoint_still_works():
    response = client.get("/v1/providers")

    assert response.status_code == 200

    body = response.json()

    assert body["object"] == "list"
    assert "data" in body
    assert isinstance(body["data"], list)
