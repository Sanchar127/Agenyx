# Deployment

## Docker image

The provided `Dockerfile`:

- Base image: `python:3.14-slim`
- Installs `requirements.txt` first (for layer caching), then copies `app/` only — **test files and other project files are not copied into the image**
- Runs as a non-root user (`uid`/`gid` `10001`, no home directory)
- Exposes port **`8004`**
- Entrypoint: `uvicorn app.main:app --host 0.0.0.0 --port 8004`

Build and run:

```bash
docker build -t agenyx-inference .

docker run -d \
  --name agenyx-inference \
  -p 8004:8004 \
  -e INFERENCE_SERVICE_API_KEY=change-me \
  -e INFERENCE_PROVIDER_NAMES=ollama-local \
  -e INFERENCE_PROVIDER_BACKENDS="ollama-local=http://host.docker.internal:11434/v1|ollama" \
  -e INFERENCE_MODEL_DEFINITIONS="qwen2.5:7b=ollama-local,llama3.2:3b=ollama-local" \
  agenyx-inference
```

> On Linux, `host.docker.internal` may need `--add-host=host.docker.internal:host-gateway`, or point the provider at the actual host/container network address of your Ollama/vLLM instance.

## Kubernetes

### Probes

The service exposes two purpose-built endpoints for Kubernetes probes:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8004
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /ready
    port: 8004
  periodSeconds: 10
```

- `/health` only confirms the process is alive — it does not check any backend, so it should not flap due to backend issues.
- `/ready` actively checks configured providers and returns `503` if none are reachable, which is appropriate for taking a pod out of the load-balancing pool without restarting it.

### Suggested environment

Because circuit-breaker and reliability state is held in-process (see [architecture.md](architecture.md)), running multiple replicas means **each replica maintains its own view of provider health independently**. This is generally fine (each replica will independently open its own circuit against a failing provider) but is worth knowing if you're trying to reason about aggregate failure behavior across replicas — there's no shared circuit-breaker state or leader election involved.

A minimal deployment needs, at least:

```yaml
env:
  - name: INFERENCE_SERVICE_API_KEY
    valueFrom:
      secretKeyRef:
        name: agenyx-inference-secrets
        key: service-api-key
  - name: INFERENCE_PROVIDER_NAMES
    value: "ollama-local"
  - name: INFERENCE_PROVIDER_BACKENDS
    value: "ollama-local=http://ollama.inference.svc.cluster.local:11434/v1|"
  - name: INFERENCE_MODEL_DEFINITIONS
    value: "qwen2.5:7b=ollama-local,llama3.2:3b=ollama-local"
  - name: INFERENCE_OTEL_EXPORTER_OTLP_ENDPOINT
    value: "http://otel-collector.monitoring.svc.cluster.local:4317"
```

### Scraping metrics

Point your Prometheus scrape config (or a `ServiceMonitor`/`PodMonitor` if using the Prometheus Operator) at `GET /metrics` on port `8004`. The endpoint is unauthenticated and excluded from the OpenAPI schema.

## Graceful shutdown

The FastAPI `lifespan` handler (`app/main.py`) runs on shutdown:

1. Logs `"Inference service shutting down"`.
2. Calls `provider_registry.close()`, which closes every provider's underlying `httpx.AsyncClient`.
3. Calls `tracer_provider.shutdown()`, flushing any pending OpenTelemetry spans.

Ensure your orchestrator gives the container a reasonable termination grace period (the default Kubernetes `terminationGracePeriodSeconds: 30` is generally sufficient) so in-flight requests and the shutdown sequence can complete.

## Configuration

See [configuration.md](configuration.md) for the full list of environment variables required/available at deploy time.
