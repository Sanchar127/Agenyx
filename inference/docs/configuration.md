# Configuration Reference

All configuration is provided via environment variables, parsed by `app/config.py` using `pydantic-settings`. Every variable is prefixed with **`INFERENCE_`** and matching is case-insensitive (`env_prefix="INFERENCE_"`, `case_sensitive=False`).

For example, the `provider_names` field is set via the `INFERENCE_PROVIDER_NAMES` environment variable.

## General

| Env var | Type | Default | Description |
|---|---|---|---|
| `INFERENCE_APP_NAME` | string | `agenyx-inference` | Service name, used as the FastAPI app title and in startup logs |
| `INFERENCE_APP_VERSION` | string | `0.1.0` | Service version, shown in the FastAPI app / OpenAPI schema |
| `INFERENCE_LOG_LEVEL` | string | `INFO` | Python logging level name (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `INFERENCE_LOG_JSON` | bool | `true` | If `true`, logs are emitted as structured JSON; if `false`, a human-readable plain formatter is used |

## Authentication

| Env var | Type | Default | Description |
|---|---|---|---|
| `INFERENCE_SERVICE_API_KEY` | string | `""` (empty) | Shared secret required in the `X-Agenyx-Service-Key` header on every `/v1/chat/completions` request. **If left empty, all such requests are rejected with `503 SERVICE_AUTH_NOT_CONFIGURED`** — there is no "auth disabled" mode. |

## Providers

| Env var | Type | Default | Description |
|---|---|---|---|
| `INFERENCE_PROVIDER_NAMES` | comma-separated string | `ollama-local` | The list of provider names to register, in priority order |
| `INFERENCE_PROVIDER_BACKENDS` | string | `ollama-local=http://localhost:11434/v1\|ollama` | Per-provider backend connection info. Format below |
| `INFERENCE_BACKEND_BASE_URL` | string | `http://localhost:11434/v1` | Fallback default base URL (currently every provider in `settings.providers` is constructed using `backend_base_url` / `backend_api_key` at startup — see note below) |
| `INFERENCE_BACKEND_API_KEY` | string | `ollama` | Fallback default API key (see note below) |

**Provider backend format** (`INFERENCE_PROVIDER_BACKENDS`):

```
provider_name=base_url|api_key
```

Multiple providers are comma-separated:

```
INFERENCE_PROVIDER_BACKENDS="ollama-local=http://localhost:11434/v1|ollama,vllm-local=http://localhost:8001/v1|"
```

> **Note on current wiring:** `Settings.provider_backend_configs` parses `INFERENCE_PROVIDER_BACKENDS` into a `provider_name → {base_url, api_key}` mapping, but as of this version, the provider construction loop in `app/main.py` builds every `OpenAICompatibleProvider` using the single `settings.backend_base_url` / `settings.backend_api_key` values rather than looking up each provider's individual entry in `provider_backend_configs`. If you configure multiple providers with different backend URLs via `INFERENCE_PROVIDER_BACKENDS`, be aware that (in the current code) they will all be constructed against the same `backend_base_url`/`backend_api_key` unless that wiring is updated. Confirm this against `app/main.py` before relying on per-provider URLs in production.

## Models

| Env var | Type | Default | Description |
|---|---|---|---|
| `INFERENCE_MODEL_DEFINITIONS` | string | `qwen2.5:7b=ollama-local,llama3.2:3b=ollama-local` | Comma-separated `model_id=provider_name` pairs. Each model's *primary* provider |
| `INFERENCE_DEFAULT_MODEL` | string | `qwen2.5:7b` | Model used when a request omits the `model` field |

**Format:**

```
INFERENCE_MODEL_DEFINITIONS="model_id=provider_name,model_id2=provider_name2"
```

Every `provider_name` referenced here must also appear in `INFERENCE_PROVIDER_NAMES`, or the service will fail to start with a `ValueError`.

## Failover routing

| Env var | Type | Default | Description |
|---|---|---|---|
| `INFERENCE_MODEL_FAILOVER_ROUTES` | string | `""` | Per-model ordered failover provider list. Overrides the single-provider route from `INFERENCE_MODEL_DEFINITIONS` for the given model |
| `INFERENCE_MAX_FAILOVER_ATTEMPTS` | int | `3` | Maximum number of providers to actually attempt per request (providers skipped due to an open circuit don't count against this) |

**Format** (semicolon-separated models, comma-separated providers within a model):

```
INFERENCE_MODEL_FAILOVER_ROUTES="qwen2.5:7b=ollama-local,vllm-local;llama3.2:3b=ollama-local"
```

If a model has no entry in `INFERENCE_MODEL_FAILOVER_ROUTES`, its failover route is just the single provider from `INFERENCE_MODEL_DEFINITIONS`.

See [reliability-and-failover.md](reliability-and-failover.md) for how this route is walked at request time.

## HTTP client / retry behavior

| Env var | Type | Default | Description |
|---|---|---|---|
| `INFERENCE_MAX_RETRIES` | int | `2` | Retries per provider attempt on `5xx`, timeout, or network error (does not apply to streaming) |
| `INFERENCE_REQUEST_TIMEOUT_SECONDS` | float | `120.0` | Per-request timeout to the backend (connect timeout is `min(timeout, 10.0)`) |
| `INFERENCE_MAX_CONNECTIONS` | int | `100` | Max total HTTP connections per provider's `httpx` client |
| `INFERENCE_MAX_KEEPALIVE_CONNECTIONS` | int | `20` | Max keepalive connections per provider's `httpx` client |
| `INFERENCE_MAX_CONCURRENCY` | int | `10` | Max number of concurrently in-flight `/v1/chat/completions` requests across all models/providers (see `app/concurrency.py`) |

## Request validation / limits

| Env var | Type | Default | Description |
|---|---|---|---|
| `INFERENCE_MAX_REQUEST_BODY_BYTES` | int | `1048576` (1 MiB) | Max raw request body size |
| `INFERENCE_MAX_MESSAGES` | int | `100` | Max number of items in `messages` |
| `INFERENCE_MAX_MESSAGE_CONTENT_CHARS` | int | `100000` | Max characters in a single message's `content` |
| `INFERENCE_MAX_TOTAL_MESSAGE_CONTENT_CHARS` | int | `500000` | Max combined characters across all messages' `content` |

## Tenancy (scaffolded, not yet enforced)

| Env var | Type | Default | Description |
|---|---|---|---|
| `INFERENCE_TENANT_MODEL_ACCESS` | string | `tenant-a=qwen2.5:7b, llama3.2:3b;tenant-b=llama3.2:3b` | Semicolon-separated `tenant_id=model1,model2` pairs, parsed into `Settings.tenant_models`. Consumed by `TenantAuthorizer` (`app/tenancy/authorizer.py`), which is not currently invoked from `app/main.py`. Set this if/when tenant enforcement is wired in |

## OpenTelemetry

| Env var | Type | Default | Description |
|---|---|---|---|
| `INFERENCE_OTEL_SERVICE_NAME` | string | `agenyx-inference` | `service.name` resource attribute |
| `INFERENCE_OTEL_SERVICE_NAMESPACE` | string | `agenyx` | `service.namespace` resource attribute |
| `INFERENCE_OTEL_EXPORTER_OTLP_ENDPOINT` | string | `http://agenyx-otel-collector.monitoring.svc.cluster.local:4317` | OTLP gRPC collector endpoint. The exporter is configured with `insecure=True` (plaintext gRPC) |

See [observability.md](observability.md) for what gets traced/exported.

## Full example `.env`

```bash
INFERENCE_APP_NAME=agenyx-inference
INFERENCE_LOG_LEVEL=INFO
INFERENCE_LOG_JSON=true

INFERENCE_SERVICE_API_KEY=change-me

INFERENCE_PROVIDER_NAMES=ollama-local,vllm-local
INFERENCE_PROVIDER_BACKENDS="ollama-local=http://ollama:11434/v1|ollama,vllm-local=http://vllm:8001/v1|"

INFERENCE_MODEL_DEFINITIONS="qwen2.5:7b=ollama-local,llama3.2:3b=ollama-local"
INFERENCE_DEFAULT_MODEL=qwen2.5:7b

INFERENCE_MODEL_FAILOVER_ROUTES="qwen2.5:7b=ollama-local,vllm-local"
INFERENCE_MAX_FAILOVER_ATTEMPTS=3

INFERENCE_MAX_RETRIES=2
INFERENCE_REQUEST_TIMEOUT_SECONDS=120
INFERENCE_MAX_CONCURRENCY=10

INFERENCE_MAX_REQUEST_BODY_BYTES=1048576
INFERENCE_MAX_MESSAGES=100
INFERENCE_MAX_MESSAGE_CONTENT_CHARS=100000
INFERENCE_MAX_TOTAL_MESSAGE_CONTENT_CHARS=500000

INFERENCE_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```
