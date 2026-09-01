from prometheus_client import Counter, Gauge, Histogram


# =========================================================
# HTTP METRICS
# =========================================================

HTTP_REQUESTS_TOTAL = Counter(
    "agenyx_inference_http_requests_total",
    "Total number of HTTP requests handled by the inference service.",
    labelnames=(
        "method",
        "route",
        "status_code",
    ),
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "agenyx_inference_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    labelnames=(
        "method",
        "route",
    ),
    # Explicit buckets make latency dashboards more useful
    # for inference workloads.
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
    ),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "agenyx_inference_http_requests_in_progress",
    "Number of HTTP requests currently being processed.",
    labelnames=(
        "method",
        "route",
    ),
)

HTTP_ERRORS_TOTAL = Counter(
    "agenyx_inference_http_errors_total",
    "Total number of HTTP requests resulting in an error.",
    labelnames=(
        "method",
        "route",
        "status_code",
    ),
)


# =========================================================
# INFERENCE METRICS
# =========================================================

INFERENCE_REQUESTS_TOTAL = Counter(
    "agenyx_inference_requests_total",
    "Total number of inference requests.",
    labelnames=(
        "provider",
        "model",
        "status",
    ),
)

INFERENCE_REQUEST_DURATION_SECONDS = Histogram(
    "agenyx_inference_request_duration_seconds",
    "Inference request duration in seconds.",
    labelnames=(
        "provider",
        "model",
    ),
    buckets=(
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
        120.0,
    ),
)

INFERENCE_REQUESTS_IN_PROGRESS = Gauge(
    "agenyx_inference_requests_in_progress",
    "Number of inference requests currently being processed.",
    labelnames=(
        "provider",
        "model",
    ),
)


# =========================================================
# PROVIDER METRICS
# =========================================================

PROVIDER_REQUESTS_TOTAL = Counter(
    "agenyx_inference_provider_requests_total",
    "Total number of requests sent to inference providers.",
    labelnames=(
        "provider",
        "model",
        "status",
    ),
)

PROVIDER_REQUEST_DURATION_SECONDS = Histogram(
    "agenyx_inference_provider_request_duration_seconds",
    "Inference provider request duration in seconds.",
    labelnames=(
        "provider",
        "model",
    ),
    buckets=(
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
        120.0,
    ),
)

PROVIDER_RETRIES_TOTAL = Counter(
    "agenyx_inference_provider_retries_total",
    "Total number of provider retry attempts.",
    labelnames=(
        "provider",
        "model",
        "reason",
    ),
)

PROVIDER_ERRORS_TOTAL = Counter(
    "agenyx_inference_provider_errors_total",
    "Total number of provider errors.",
    labelnames=(
        "provider",
        "model",
        "error_type",
    ),
)


# =========================================================
# RELIABILITY METRICS
# =========================================================

PROVIDER_CIRCUIT_STATE = Gauge(
    "agenyx_inference_provider_circuit_state",
    """
Current provider circuit-breaker state.

0 = CLOSED
1 = OPEN
2 = HALF_OPEN
""",
    labelnames=("provider",),
)

PROVIDER_HEALTH_STATE = Gauge(
    "agenyx_inference_provider_health_state",
    """
Current provider health state.

0 = UNHEALTHY
1 = DEGRADED
2 = HEALTHY
""",
    labelnames=("provider",),
)

PROVIDER_CONSECUTIVE_FAILURES = Gauge(
    "agenyx_inference_provider_consecutive_failures",
    "Current consecutive provider failures.",
    labelnames=("provider",),
)

PROVIDER_TOTAL_FAILURES = Gauge(
    "agenyx_inference_provider_total_failures",
    "Total provider failures recorded by the reliability manager.",
    labelnames=("provider",),
)

PROVIDER_TOTAL_SUCCESSES = Gauge(
    "agenyx_inference_provider_total_successes",
    "Total provider successes recorded by the reliability manager.",
    labelnames=("provider",),
)
