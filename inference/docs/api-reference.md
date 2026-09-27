# API Reference

Base path: none (routes are mounted at root). Default port: `8004`.

All error responses share this shape:

```json
{
  "detail": {
    "code": "SOME_ERROR_CODE",
    "message": "Human readable message"
  }
}
```

---

## `POST /v1/chat/completions`

OpenAI-compatible chat completion endpoint. This is the only inference-executing endpoint in the service.

### Authentication

Requires header:

```
X-Agenyx-Service-Key: <INFERENCE_SERVICE_API_KEY>
```

| Condition | Status | Code |
|---|---|---|
| `INFERENCE_SERVICE_API_KEY` not set on the server | `503` | `SERVICE_AUTH_NOT_CONFIGURED` |
| Header missing or does not match | `401` | `INVALID_SERVICE_CREDENTIAL` |

### Request body

```json
{
  "model": "qwen2.5:7b",
  "messages": [
    { "role": "user", "content": "Hello!" }
  ],
  "stream": false
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `model` | string | No | Defaults to `INFERENCE_DEFAULT_MODEL`. Must reference a registered model |
| `messages` | array of objects | Yes | Non-empty. Each item's `content`, if present, must be a string |
| `stream` | bool | No | Must be `false` or omitted — `true` is rejected (streaming is not implemented) |

Any other OpenAI-style fields (e.g. `temperature`, `max_tokens`) are passed through to the backend as-is; the service does not currently validate or strip them.

### Validation errors (`400`)

| Code | Cause |
|---|---|
| `REQUEST_BODY_READ_FAILED` | The request body could not be read |
| `INVALID_JSON` | Body is not valid JSON |
| `INVALID_REQUEST_BODY` | Body is valid JSON but not a JSON object |
| `INVALID_MESSAGES` | `messages` missing, not a list, or empty |
| `TOO_MANY_MESSAGES` | `messages` longer than `INFERENCE_MAX_MESSAGES` |
| `INVALID_MESSAGE` | An item in `messages` is not a JSON object |
| `INVALID_MESSAGE_CONTENT` | A message's `content` is present but not a string |
| `MESSAGE_CONTENT_TOO_LARGE` | A single message's `content` exceeds `INFERENCE_MAX_MESSAGE_CONTENT_CHARS` |
| `TOTAL_MESSAGE_CONTENT_TOO_LARGE` | Combined `content` across all messages exceeds `INFERENCE_MAX_TOTAL_MESSAGE_CONTENT_CHARS` |
| `INVALID_MODEL` | `model` field present but not a string |

### Other errors

| Status | Code | Cause |
|---|---|---|
| `413` | `REQUEST_BODY_TOO_LARGE` | Body exceeds `INFERENCE_MAX_REQUEST_BODY_BYTES` |
| `404` | `MODEL_NOT_FOUND` | Requested `model` is not registered |
| `501` | `STREAMING_NOT_IMPLEMENTED` | `"stream": true` was requested |
| `429` | `INFERENCE_CONCURRENCY_LIMIT` | Server is at `INFERENCE_MAX_CONCURRENCY` in-flight requests |
| `503` | `MODEL_UNAVAILABLE` | Model has no configured failover route |
| `503` | `INFERENCE_FAILED` | Every provider in the model's failover route failed |
| `500` | `INTERNAL_SERVER_ERROR` | Unhandled exception (details are logged server-side only) |

### Success response

`200 OK`, body is the raw JSON response returned by the upstream provider (OpenAI chat-completion response shape), passed through unmodified. Response headers:

| Header | Description |
|---|---|
| `X-Agenyx-Provider` | Name of the provider that actually served the request (useful when failover occurred) |
| `X-Agenyx-Model` | The resolved model ID |

### Example

```bash
curl http://localhost:8004/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Agenyx-Service-Key: dev-secret" \
  -d '{
        "model": "qwen2.5:7b",
        "messages": [
          {"role": "user", "content": "Say hi in five words."}
        ]
      }'
```

---

## `GET /v1/models`

Lists every model registered via `INFERENCE_MODEL_DEFINITIONS`. No authentication required.

**Response `200`:**

```json
{
  "object": "list",
  "data": [
    { "id": "qwen2.5:7b", "object": "model", "owned_by": "agenyx" },
    { "id": "llama3.2:3b", "object": "model", "owned_by": "agenyx" }
  ]
}
```

---

## `GET /v1/providers`

Lists every registered provider name. No authentication required.

**Response `200`:**

```json
{
  "object": "list",
  "data": [
    { "id": "ollama-local", "object": "provider" }
  ]
}
```

---

## `GET /v1/reliability`

Returns the current circuit-breaker / health state for every registered provider. No authentication required. Useful for dashboards and debugging failover behavior.

**Response `200`:**

```json
{
  "object": "reliability",
  "providers": [
    {
      "provider": "ollama-local",
      "status": "healthy",
      "circuit_state": "closed",
      "consecutive_failures": 0,
      "total_failures": 2,
      "total_successes": 148,
      "last_failure_at": "2026-09-20T10:15:03.120000+00:00",
      "last_success_at": "2026-09-27T08:02:11.884000+00:00",
      "circuit_opened_at": null,
      "circuit_half_opened_at": null
    }
  ]
}
```

`status` is one of `healthy`, `degraded`, `unhealthy`. `circuit_state` is one of `closed`, `open`, `half_open`. See [reliability-and-failover.md](reliability-and-failover.md) for what drives these transitions.

---

## `GET /health`

Liveness probe. Always returns `200` as long as the process is running — does not check any backend.

```json
{ "status": "ok" }
```

---

## `GET /ready`

Readiness probe. Iterates configured providers and returns `200` as soon as one responds healthy to a live check against its backend.

**Response `200`:**

```json
{ "status": "ready", "provider": "ollama-local" }
```

**Response `503`** (`NO_PROVIDERS_AVAILABLE`) if no configured provider is reachable.

---

## `GET /metrics`

Prometheus text-format metrics endpoint (`Content-Type: text/plain; version=0.0.4`). Excluded from the OpenAPI schema. See [observability.md](observability.md) for the full metric list.

---

## OpenAPI / interactive docs

Because this is a standard FastAPI app, interactive docs are available (when the server is running) at:

- `/docs` — Swagger UI
- `/redoc` — ReDoc
- `/openapi.json` — raw OpenAPI schema
