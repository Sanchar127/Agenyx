# Agenyx Inference

Agenyx Inference is the inference gateway component of the **Agenyx** project. It exposes a single, OpenAI-compatible `/v1/chat/completions` endpoint and routes each request to one of several configured backend providers (Ollama, vLLM, OpenAI, or any other OpenAI-compatible server), with per-model failover, circuit breakers, and Prometheus/OpenTelemetry observability built in.

It is a [FastAPI](https://fastapi.tiangolo.com/) service, intended to run as an internal microservice behind a service-to-service API key, not to be exposed directly to end users.

## Why this service exists

Agents in the broader Agenyx system need to call an LLM without knowing or caring which backend is actually serving that model, or what to do when that backend is slow, down, or rate-limited. Agenyx Inference sits between agents and the actual model backends and provides:

- **One stable API** (`/v1/chat/completions`) regardless of which backend serves the model.
- **Provider failover** — a model can be routed to a prioritized list of providers; if one fails, the next is tried automatically.
- **Circuit breaking** — a provider that keeps failing is temporarily taken out of rotation instead of being hammered with more requests.
- **Concurrency control** — a simple in-process admission limiter protects the service (and the backends) from being overwhelmed.
- **Structured observability** — JSON logs, Prometheus metrics, and OpenTelemetry traces out of the box.

## Documentation

Detailed documentation lives in [`docs/`](docs/):

| Document | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Component overview, request lifecycle, module map |
| [`docs/configuration.md`](docs/configuration.md) | Every environment variable, with format and examples |
| [`docs/api-reference.md`](docs/api-reference.md) | Every HTTP endpoint, request/response shape, error codes |
| [`docs/reliability-and-failover.md`](docs/reliability-and-failover.md) | Circuit breaker state machine and failover routing in detail |
| [`docs/observability.md`](docs/observability.md) | Logging, Prometheus metrics, OpenTelemetry tracing |
| [`docs/deployment.md`](docs/deployment.md) | Docker image, running locally, Kubernetes probes |
| [`docs/development.md`](docs/development.md) | Project layout, running tests, contribution notes |

## Quickstart

### Run locally

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Point at a local Ollama instance and set a service credential
export INFERENCE_SERVICE_API_KEY=dev-secret
export INFERENCE_PROVIDER_NAMES=ollama-local
export INFERENCE_PROVIDER_BACKENDS="ollama-local=http://localhost:11434/v1|ollama"
export INFERENCE_MODEL_DEFINITIONS="qwen2.5:7b=ollama-local,llama3.2:3b=ollama-local"

uvicorn app.main:app --host 0.0.0.0 --port 8004 --reload
```

### Run with Docker

```bash
docker build -t agenyx-inference .
docker run -p 8004:8004 \
  -e INFERENCE_SERVICE_API_KEY=dev-secret \
  -e INFERENCE_PROVIDER_BACKENDS="ollama-local=http://host.docker.internal:11434/v1|ollama" \
  agenyx-inference
```

### Send a request

```bash
curl http://localhost:8004/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Agenyx-Service-Key: dev-secret" \
  -d '{
        "model": "qwen2.5:7b",
        "messages": [{"role": "user", "content": "Hello!"}]
      }'
```

See [`docs/api-reference.md`](docs/api-reference.md) for the full set of endpoints, and [`docs/configuration.md`](docs/configuration.md) for every setting used above.

## Project status

- ✅ Non-streaming chat completions with provider failover and circuit breaking
- ✅ Prometheus metrics, structured JSON logging, OpenTelemetry tracing
- ✅ Docker image with Kubernetes-friendly liveness/readiness probes
- 🚧 Streaming responses (`"stream": true`) are rejected with `501 Not Implemented` — not yet built
- 🚧 Tenant-based model authorization (`app/tenancy/`) exists as a standalone, unit-tested component but is **not yet wired into** the request path in `app/main.py`

## Running the tests

```bash
pip install -r requirements.txt
pytest
```

See [`docs/development.md`](docs/development.md) for details on the unit vs. integration test layout.

## License

No license file is included in this package. Treat this project as proprietary/internal to Agenyx unless a license is added.
