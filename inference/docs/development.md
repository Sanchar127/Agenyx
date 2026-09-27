# Development

## Project layout

```
inference/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── main.py               # FastAPI app, routes, request lifecycle
│   ├── config.py             # Settings (env-driven configuration)
│   ├── auth.py                # Service-to-service auth dependency
│   ├── concurrency.py         # In-process concurrency limiter
│   ├── backend.py             # HTTP backend client (retries, backoff)
│   ├── logger.py              # Structured logging setup
│   ├── metrics.py             # Prometheus metric definitions
│   ├── telemetry.py           # OpenTelemetry setup
│   ├── providers/
│   │   ├── base.py            # InferenceProvider ABC
│   │   ├── openai_compatible.py
│   │   └── registry.py        # ProviderRegistry
│   ├── models/
│   │   ├── definition.py      # ModelDefinition dataclass
│   │   └── registry.py        # ModelRegistry
│   ├── failover/
│   │   └── manager.py         # FailoverManager
│   ├── reliability/
│   │   ├── manager.py         # ReliabilityManager (circuit breaker)
│   │   └── state.py           # ProviderHealthState, enums
│   └── tenancy/
│       └── authorizer.py      # TenantAuthorizer (not yet wired into main.py)
└── tests/
    ├── conftest.py             # Shared `client` fixture (async ASGI test client)
    ├── test_concurrency.py
    ├── unit/                   # Unit tests, one file per module roughly
    │   ├── test_auth.py
    │   ├── test_backend.py
    │   ├── test_config.py
    │   ├── test_failover.py
    │   ├── test_main.py
    │   ├── test_metrics.py
    │   ├── test_models.py
    │   ├── test_provider.py
    │   ├── test_provider_registry.py
    │   ├── test_reliability.py
    │   └── test_tenant_authorizer.py
    └── integration/            # Integration tests exercising the ASGI app end-to-end
        ├── test_inference_api.py
        ├── test_lifecycle.py
        ├── test_metrics.py
        ├── test_provider_backend.py
        └── test_reliability_flow.py
```

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` includes both runtime dependencies (FastAPI, uvicorn, httpx, pydantic-settings, prometheus-client, the OpenTelemetry packages) and test dependencies (`pytest`, `pytest-asyncio`).

## Running tests

```bash
pytest
```

Run only unit or only integration tests:

```bash
pytest tests/unit
pytest tests/integration
```

Run a single file or test:

```bash
pytest tests/unit/test_failover.py
pytest tests/unit/test_reliability.py -k half_open
```

### Test fixtures

`tests/conftest.py` sets `INFERENCE_SERVICE_API_KEY=test-service-key` **before** importing `app.main` (import order matters here, since `Settings` is read once at import time via `get_settings()`), and exposes an async `client` fixture — an `httpx.AsyncClient` wired to the FastAPI app via `ASGITransport`, pre-populated with a valid `X-Agenyx-Service-Key` header.

Because `app/config.py` uses `@lru_cache` on `get_settings()`, and several module-level objects in `app/main.py` (registries, the failover manager, etc.) are constructed once at import time from those settings, tests that need different configuration typically set environment variables and re-import, or construct the relevant classes (`ReliabilityManager`, `FailoverManager`, `ProviderRegistry`, ...) directly rather than going through the FastAPI app — see the `unit/` tests for examples of testing components in isolation.

## Code style notes

The codebase consistently uses:

- Keyword-only constructor arguments (`*,`) for most classes with more than one or two parameters.
- Explicit, multi-line argument formatting even for short calls — this is a deliberate style choice throughout the repo, not an artifact of auto-formatting.
- Section-comment banners (`# === SECTION ===`) to delineate logical regions within larger files like `app/main.py` and `app/config.py`.
- Structured logging via `logger.<level>(message, extra={...})` at every meaningful state transition or rejected request, rather than only on error paths.

## Adding a new provider backend type

Today, `OpenAICompatibleBackend` is the only concrete `InferenceBackend`. To add a new backend type (e.g. a native SDK-based backend instead of a generic OpenAI-compatible HTTP client):

1. Implement `InferenceBackend` (`app/backend.py`) — `chat_completion`, `chat_completion_stream`, `health`, `close`.
2. Implement or extend `InferenceProvider` (`app/providers/base.py`) to wrap it, following the pattern in `app/providers/openai_compatible.py`.
3. Wire it up in `app/main.py`'s provider construction loop, likely gated by a new setting (e.g. a `backend_type` field per provider) in `app/config.py`.

## Known gaps to be aware of when contributing

- **Streaming** (`chat_completion_stream` on the backend) is implemented at the backend layer but never called — `app/main.py` rejects any request with `"stream": true` with `501`. Wiring this up end-to-end (through `FailoverManager` and the HTTP route) is open work.
- **Tenant authorization** (`app/tenancy/authorizer.py`) is implemented and unit-tested but not called anywhere in `app/main.py`. There is currently no tenant identification on inbound requests either (no tenant header/claim is read).
- **Per-provider backend URLs**: `Settings.provider_backend_configs` parses `INFERENCE_PROVIDER_BACKENDS` into a per-provider mapping, but the provider construction loop in `app/main.py` currently builds every provider from the single `settings.backend_base_url` / `settings.backend_api_key` fields instead of looking each provider up in `provider_backend_configs`. Check `app/main.py` before assuming multi-backend configuration is fully wired.
- **Circuit breaker thresholds** (`degraded_failure_threshold`, `unhealthy_failure_threshold`, `recovery_timeout_seconds`) are hardcoded in `app/main.py` rather than exposed as environment variables.
