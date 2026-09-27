# Observability

Agenyx Inference ships with structured logging, Prometheus metrics, and OpenTelemetry tracing out of the box.

## Logging (`app/logger.py`)

Logging is configured once at import time (`configure_logging()` runs when `app.logger` is first imported) and writes to stdout.

- **`INFERENCE_LOG_JSON=true` (default):** every log line is a single JSON object via `JsonFormatter`:

  ```json
  {
    "timestamp": "2026-09-27T09:00:00.123456+00:00",
    "level": "INFO",
    "service": "agenyx-inference",
    "logger": "agenyx.inference",
    "message": "Inference request completed",
    "model": "qwen2.5:7b",
    "provider": "ollama-local",
    "latency_ms": 842.11
  }
  ```

  Any keyword passed via `logger.info(msg, extra={...})` is merged into the top-level JSON object (values that aren't JSON-serializable are coerced with `str()`). Exceptions logged with `exc_info=True` get an `"exception": {"type": ..., "message": ...}` field.

- **`INFERENCE_LOG_JSON=false`:** a plain formatter is used instead — `%(asctime)s %(levelname)s %(name)s %(message)s`, useful for local development.

- **Level** is controlled by `INFERENCE_LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`; defaults to `INFO`, falls back to `INFO` if an unrecognized value is given).

The application logger is `logging.getLogger("agenyx.inference")`, exported as `app.logger.logger` and used throughout the codebase.

### What gets logged

Every stage of the request lifecycle logs at an appropriate level: `debug` for routine lookups (health checks, provider/model listing), `info` for request start/finish and state transitions, `warning` for rejected/invalid requests and degraded providers, `error` for unhandled exceptions and exhausted failover.

## Prometheus metrics (`app/metrics.py`, exposed at `GET /metrics`)

### HTTP-level (recorded by the `prometheus_http_metrics` middleware for every request)

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agenyx_inference_http_requests_total` | Counter | `method`, `route`, `status_code` | Total HTTP requests |
| `agenyx_inference_http_request_duration_seconds` | Histogram | `method`, `route` | Request duration |
| `agenyx_inference_http_requests_in_progress` | Gauge | `method`, `route` | Requests currently being handled |
| `agenyx_inference_http_errors_total` | Counter | `method`, `route`, `status_code` | Requests with status `>= 400` |

`route` is the normalized FastAPI route path (e.g. `/v1/chat/completions`), not the raw URL, to avoid high-cardinality labels.

### Inference-level (recorded around the failover call in `app/main.py`)

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agenyx_inference_requests_total` | Counter | `provider`, `model`, `status` | Total logical inference requests (`provider="failover"` while in-flight; the winning provider's name once resolved) |
| `agenyx_inference_request_duration_seconds` | Histogram | `provider`, `model` | End-to-end inference duration (through the failover layer) |
| `agenyx_inference_requests_in_progress` | Gauge | `provider`, `model` | In-flight inference requests |

### Provider-level (recorded inside `OpenAICompatibleBackend`)

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agenyx_inference_provider_requests_total` | Counter | `provider`, `model`, `status` | Requests to a specific backend (`status`: `success`, `client_error`, `retryable_error`, `error`) |
| `agenyx_inference_provider_request_duration_seconds` | Histogram | `provider`, `model` | Duration of a single backend HTTP call |
| `agenyx_inference_provider_retries_total` | Counter | `provider`, `model`, `reason` | Retry attempts (`reason`: `http_<status>`, `timeout`, `network_error`) |
| `agenyx_inference_provider_errors_total` | Counter | `provider`, `model`, `error_type` | Backend errors by type |

### Reliability / circuit breaker (recorded by `ReliabilityManager`)

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agenyx_inference_provider_circuit_state` | Gauge | `provider` | `0`=closed, `1`=open, `2`=half_open |
| `agenyx_inference_provider_health_state` | Gauge | `provider` | `0`=unhealthy, `1`=degraded, `2`=healthy |
| `agenyx_inference_provider_consecutive_failures` | Gauge | `provider` | Current consecutive failure streak |
| `agenyx_inference_provider_total_failures` | Gauge | `provider` | Cumulative failures |
| `agenyx_inference_provider_total_successes` | Gauge | `provider` | Cumulative successes |

All histograms use explicit bucket boundaries tuned for inference workloads (see `app/metrics.py`) rather than the Prometheus client's default buckets.

## OpenTelemetry tracing (`app/telemetry.py`)

At startup, `configure_telemetry(settings)`:

1. Builds a `Resource` with `service.name` = `INFERENCE_OTEL_SERVICE_NAME` and `service.namespace` = `INFERENCE_OTEL_SERVICE_NAMESPACE`.
2. Creates a `TracerProvider` with that resource.
3. Adds a `BatchSpanProcessor` exporting via `OTLPSpanExporter` (gRPC, **`insecure=True`** i.e. plaintext) to `INFERENCE_OTEL_EXPORTER_OTLP_ENDPOINT`.
4. Sets it as the global tracer provider.

`instrument_app(app)` then auto-instruments:

- **FastAPI** (`FastAPIInstrumentor`) — every inbound HTTP request becomes a span.
- **httpx** (`HTTPXClientInstrumentor`) — every outbound call to a provider backend becomes a child span.

This means a single `/v1/chat/completions` request produces a trace containing the inbound FastAPI span plus one child span per backend HTTP call (including retries and failover attempts across providers), which is useful for visualizing exactly where time was spent and which providers were tried.

On shutdown, the app's `lifespan` handler calls `tracer_provider.shutdown()` to flush any pending spans.

> **Note:** the OTLP endpoint defaults to a Kubernetes-internal DNS name (`agenyx-otel-collector.monitoring.svc.cluster.local:4317`). For local development, either run a local OTLP collector on that port or override `INFERENCE_OTEL_EXPORTER_OTLP_ENDPOINT`. There is currently no way to fully disable tracing via configuration — the exporter is always constructed, and requests to an unreachable endpoint will simply fail to export in the background without affecting request handling.
