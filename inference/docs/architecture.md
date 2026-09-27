# Architecture

## Overview

Agenyx Inference is a single FastAPI application (`app/main.py`) composed of a small set of focused modules. There is no database — all state (provider registry, model registry, reliability/circuit-breaker state) lives in memory for the lifetime of the process.

```
                         ┌─────────────────────────┐
  client / agent  ──────▶│  FastAPI app (main.py)  │
  (X-Agenyx-Service-Key) │  auth · validation ·    │
                         │  concurrency admission  │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │     FailoverManager      │
                         │  model → ordered         │
                         │  provider route          │
                         └────────────┬────────────┘
                                      │ consults
                     ┌────────────────┼────────────────┐
                     ▼                                 ▼
        ┌─────────────────────┐          ┌──────────────────────────┐
        │  ProviderRegistry    │          │   ReliabilityManager     │
        │  name → provider      │          │  circuit breaker state   │
        └──────────┬───────────┘          │  per provider            │
                    │                      └──────────────────────────┘
                    ▼
        ┌───────────────────────────┐
        │ OpenAICompatibleProvider   │
        │  (wraps a backend)         │
        └──────────┬─────────────────┘
                    ▼
        ┌───────────────────────────┐
        │ OpenAICompatibleBackend    │
        │  httpx.AsyncClient         │
        │  retries + backoff         │
        └──────────┬─────────────────┘
                    ▼
          Ollama / vLLM / OpenAI /
          any OpenAI-compatible API
```

## Module map

| Module | Responsibility |
|---|---|
| `app/main.py` | FastAPI app, routes, request validation, HTTP middleware, wiring of every other component at import time |
| `app/config.py` | `Settings` (pydantic-settings), all environment variables and their parsed representations |
| `app/auth.py` | `require_service_auth` FastAPI dependency — validates the `X-Agenyx-Service-Key` header |
| `app/concurrency.py` | `InferenceConcurrencyLimiter` — a non-blocking, in-process admission limiter |
| `app/backend.py` | `InferenceBackend` (ABC) and `OpenAICompatibleBackend` — the actual HTTP client to a backend, with retry/backoff logic |
| `app/providers/` | `InferenceProvider` (ABC), `OpenAICompatibleProvider` (concrete provider wrapping a backend), `ProviderRegistry` |
| `app/models/` | `ModelDefinition` (dataclass), `ModelRegistry` — maps a model ID to the provider that serves it |
| `app/failover/` | `FailoverManager` — for a given model, walks an ordered list of providers and retries against the next one on failure |
| `app/reliability/` | `ReliabilityManager`, `ProviderHealthState`, `CircuitState`, `ProviderStatus` — the circuit breaker |
| `app/tenancy/` | `TenantAuthorizer` — maps tenant IDs to the set of models they may use. **Implemented and unit-tested, but not yet called from `app/main.py`.** |
| `app/metrics.py` | All `prometheus_client` metric definitions used across the service |
| `app/logger.py` | JSON/plain structured logging configuration |
| `app/telemetry.py` | OpenTelemetry tracer setup and FastAPI/httpx auto-instrumentation |

## Request lifecycle (`POST /v1/chat/completions`)

1. **Auth** — `require_service_auth` checks the `X-Agenyx-Service-Key` header against `INFERENCE_SERVICE_API_KEY`. If the server has no key configured, every request is rejected with `503`; if the header doesn't match, `401`.
2. **Body limits** — the raw body is read and rejected with `413` if it exceeds `max_request_body_bytes`.
3. **JSON parsing** — invalid JSON or a non-object body is rejected with `400`.
4. **Message validation** — `messages` must be a non-empty list, no longer than `max_messages`; each message must be an object; `content`, if present, must be a string no longer than `max_message_content_chars`; the sum of all message content lengths must not exceed `max_total_message_content_chars`.
5. **Model resolution** — `model` defaults to `default_model` if omitted, must be a string, and must exist in the `ModelRegistry` (`404 MODEL_NOT_FOUND` otherwise).
6. **Streaming rejection** — if `"stream": true` is set, the request is rejected with `501 STREAMING_NOT_IMPLEMENTED`.
7. **Concurrency admission** — `InferenceConcurrencyLimiter.try_acquire()` must succeed or the request is rejected with `429 INFERENCE_CONCURRENCY_LIMIT`.
8. **Failover execution** — `FailoverManager.chat_completion(payload)` walks the model's configured provider route (see [reliability-and-failover.md](reliability-and-failover.md)).
9. **Response** — on success, the raw provider JSON response is returned with `X-Agenyx-Provider` and `X-Agenyx-Model` headers. On failure, a `503` is returned (`MODEL_UNAVAILABLE` if no route is configured, `INFERENCE_FAILED` if every provider in the route failed).

Throughout, HTTP-level metrics are recorded by the `prometheus_http_metrics` middleware, and inference-level metrics are recorded around the failover call.

## Design notes

- **Providers vs. models are decoupled.** A *provider* is a backend connection (e.g. `ollama-local` pointing at `http://localhost:11434/v1`). A *model* (e.g. `qwen2.5:7b`) is registered against one *default* provider, and can additionally have an ordered failover route across multiple providers. This means one provider can serve many models, and one model can fail over across many providers.
- **All backends currently speak the OpenAI chat-completions wire format.** `OpenAICompatibleBackend` is the only `InferenceBackend` implementation today; new backend types (e.g. a native Anthropic or Bedrock backend) would implement the same `InferenceBackend` ABC.
- **State is process-local.** The `ProviderRegistry`, `ModelRegistry`, and `ReliabilityManager` are all plain in-memory objects built once at import time in `app/main.py`. Running multiple replicas means each replica tracks its own circuit-breaker state independently — there is no shared/distributed state store.
- **Tenancy is scaffolded but not enforced yet.** `app/tenancy/authorizer.py` and the `INFERENCE_TENANT_MODEL_ACCESS` setting exist and are unit-tested, but `chat_completions()` in `main.py` does not currently look up a tenant or call `TenantAuthorizer.is_allowed`. Anyone with a valid service key can request any registered model.
