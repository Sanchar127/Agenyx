# Reliability & Failover

Agenyx Inference combines two cooperating components to keep serving requests when a backend degrades: the **`ReliabilityManager`** (a per-provider circuit breaker) and the **`FailoverManager`** (per-model provider routing).

## Circuit breaker (`app/reliability/manager.py`)

Every registered provider has a `ProviderHealthState` tracked in memory:

```python
status: healthy | degraded | unhealthy
circuit_state: closed | open | half_open
consecutive_failures: int
total_failures: int
total_successes: int
last_failure_at / last_success_at: datetime | None
circuit_opened_at / circuit_half_opened_at: datetime | None
```

The manager is constructed in `app/main.py` with:

```python
ReliabilityManager(
    degraded_failure_threshold=1,
    unhealthy_failure_threshold=3,
    recovery_timeout_seconds=10.0,
)
```

These three thresholds are currently **hardcoded** in `main.py` rather than exposed as environment variables.

### State machine

```
                 success
      ┌────────────────────────────────────────┐
      │                                          │
      ▼                                          │
  ┌────────┐  consecutive_failures        ┌───────────┐
  │ CLOSED │ ─────  >= unhealthy_ ───────▶ │   OPEN    │
  │        │        threshold (3)          │           │
  └────────┘                               └─────┬─────┘
      ▲                                            │ recovery_timeout_seconds
      │                                            │ (10s) elapses
      │            failed probe                    ▼
      │        ┌───────────────────────────┐ ┌────────────┐
      └────────┤        reopen circuit      │ HALF_OPEN  │
               └─────────────────────────────┘ (1 probe)  │
                                              └──────┬──────┘
                                                     │ successful probe
                                                     ▼
                                                  CLOSED
```

- **CLOSED** — normal traffic. `allow_request()` returns `True`.
- Each failure increments `consecutive_failures`.
  - At `>= degraded_failure_threshold` (default **1**) failures, `status` becomes `degraded` (circuit stays `closed`).
  - At `>= unhealthy_failure_threshold` (default **3**) consecutive failures, `status` becomes `unhealthy` and `circuit_state` becomes `open`. `allow_request()` now returns `False` for this provider.
- **OPEN** — requests are rejected immediately (fail fast) until `recovery_timeout_seconds` (default **10s**) has elapsed since the circuit opened.
- Once the timeout elapses, the *next* `allow_request()` call transitions the circuit to **HALF_OPEN** and allows exactly **one** probe request through (tracked via an internal `_half_open_probe` set so concurrent callers don't all get let through at once).
- If that probe **succeeds**, `record_success()` resets `consecutive_failures` to `0`, sets `status = healthy`, and closes the circuit.
- If that probe **fails**, `record_failure()` immediately reopens the circuit (`circuit_opened_at` is reset to now), and the timeout starts again.

All of this is thread-safe (`threading.Lock`) since it can be touched by multiple concurrent async request handlers.

### Metrics

Every state transition updates these Prometheus gauges (see [observability.md](observability.md)):

- `agenyx_inference_provider_circuit_state` (`0`=closed, `1`=open, `2`=half_open)
- `agenyx_inference_provider_health_state` (`0`=unhealthy, `1`=degraded, `2`=healthy)
- `agenyx_inference_provider_consecutive_failures`
- `agenyx_inference_provider_total_failures`
- `agenyx_inference_provider_total_successes`

### Inspecting state

`GET /v1/reliability` returns a live snapshot for every provider — see [api-reference.md](api-reference.md#get-v1reliability).

## Failover routing (`app/failover/manager.py`)

Each model has an **ordered tuple of provider names** — its failover route — built at startup in `app/main.py`:

1. Start with the model's single primary provider from `INFERENCE_MODEL_DEFINITIONS` (`model_id=provider_name`).
2. If the model has an entry in `INFERENCE_MODEL_FAILOVER_ROUTES`, that ordered provider list **replaces** the single-provider default entirely.

Example:

```bash
INFERENCE_MODEL_DEFINITIONS="qwen2.5:7b=ollama-local,llama3.2:3b=ollama-local"
INFERENCE_MODEL_FAILOVER_ROUTES="qwen2.5:7b=ollama-local,vllm-local"
```

results in:

```
qwen2.5:7b  -> (ollama-local, vllm-local)
llama3.2:3b -> (ollama-local,)               # unchanged, no failover entry
```

At startup, `FailoverManager._validate_routes()` raises `ValueError` if any route references an unregistered provider, or if a model has an empty provider list.

### Request-time behavior

For a `chat_completion(payload)` call:

1. Read `payload["model"]`; look up its provider route.
2. Walk the route in order. For each provider, up to `INFERENCE_MAX_FAILOVER_ATTEMPTS` (default **3**) providers are actually *attempted*:
   - If `ReliabilityManager.allow_request(provider)` is `False` (circuit open), the provider is **skipped** — this does *not* count toward `max_attempts`, it's just recorded as a failed attempt with `error="Provider circuit is open"`.
   - Otherwise, the provider is attempted (counts toward `max_attempts`). On success: `record_success()` is called and the response is returned immediately (later providers in the route are not tried). On exception: `record_failure()` is called, the error is recorded, and the loop continues to the next provider.
3. If every attempted provider failed, `RuntimeError("All failover providers failed for model '...'")` is raised, chained from the last error. `app/main.py` turns this into `503 INFERENCE_FAILED`.
4. If the route is exhausted with no providers ever attempted (e.g. all circuits open), `RuntimeError("No failover providers are currently available for model '...'")` is raised, also surfaced as `503 INFERENCE_FAILED`.
5. If the model has no configured route at all, `FailoverManager` raises `KeyError`, which `app/main.py` turns into `503 MODEL_UNAVAILABLE`.

Every attempt (successful or not) is recorded in a `FailoverResult.attempts` list of `FailoverAttempt(provider, success, error)` — this is returned internally but not currently exposed on the HTTP response; only the winning `provider` name is surfaced via the `X-Agenyx-Provider` response header.

## Retries vs. failover — two different layers

It's worth distinguishing two retry mechanisms that operate at different layers:

| Layer | Component | Retries... | Config |
|---|---|---|---|
| HTTP transport | `OpenAICompatibleBackend.chat_completion` | ...the *same* provider on `5xx`, timeout, or network error, with exponential backoff + jitter | `INFERENCE_MAX_RETRIES` (default 2) |
| Routing | `FailoverManager.chat_completion` | ...*different* providers for the same model, in priority order | `INFERENCE_MAX_FAILOVER_ATTEMPTS` (default 3) |

A single client request can therefore trigger up to `(max_retries + 1) × max_failover_attempts` backend HTTP calls in the worst case before ultimately failing.

Backoff formula used by the backend layer (`_backoff`):

```
delay = min(0.5 * 2^attempt, 10.0) + uniform(0, 0.25)
```
