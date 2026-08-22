# Distributed AI Agent Runtime

A production-oriented runtime for running distributed, tool-using AI agents at scale. It separates request handling, task orchestration, agent execution, tool sandboxing, and model inference into independently scalable services, with shared infrastructure for state, messaging, and observability.

## Why this exists

Most agent demos run a single process: prompt in, tool call out, response back. That falls over fast once you need to run many agents concurrently, isolate untrusted tool execution, recover from mid-task crashes, or control LLM inference cost. This runtime is built around those production concerns from the start, while staying simple enough to run locally with a handful of services.

## Architecture overview

```
Client → API Gateway → Orchestrator → Agent Worker Pool → Tool Sandbox
                                                          → LLM Inference Cluster
                                                          → Response Aggregator
```

Every stage above is backed by shared infrastructure:

| Layer | Responsibility | Default implementation |
|---|---|---|
| API Gateway | Auth, routing, rate limiting | Kong / Istio |
| Orchestrator | Task planning, scheduling, checkpointing | Custom control plane |
| Agent Worker Pool | Distributed, stateless agent execution | Kubernetes-scheduled pods |
| Tool Sandbox | Isolated execution of tool/function calls | gVisor / Firecracker |
| Inference Serving | Batched, GPU-backed LLM serving | vLLM / TGI |
| Message Bus | Async task distribution | Kafka / NATS |
| State Store | Task checkpoints, agent state | Redis / PostgreSQL |
| Vector Store | Retrieval and long-term memory | Pinecone / Weaviate |
| Observability | Tracing, metrics, logs | OpenTelemetry, Prometheus, Grafana |

See [`docs/architecture.md`](docs/architecture.md) for the full diagram and design rationale.

## Design principles

- **Stateless workers, stateful store.** Agent workers hold no durable state — all progress is checkpointed to the state store, so a crashed worker's task can resume on another worker.
- **Isolate before you extend.** Any tool call that touches an external API, runs generated code, or leaves the trust boundary of the runtime goes through the sandbox layer — no exceptions, no "just this once."
- **Inference is a first-class service.** LLM calls go through a dedicated batched serving layer, not ad hoc API calls scattered across the codebase. This is usually the largest cost and latency lever in the system.
- **Add infrastructure when a bottleneck demands it, not before.** The default stack is intentionally minimal — one message bus, one state store, one vector store. Additional data stores or queues get added when a real access pattern justifies them.

## Getting started

### Prerequisites

- Docker and Docker Compose
- Kubernetes cluster (for production deployment) — Kind or Minikube for local development
- Python 3.11+ / Node 20+ (depending on which service components you're running)

### Local development

```bash
git clone https://github.com/<your-org>/<your-repo>.git
cd <your-repo>
cp .env.example .env
docker compose up
```

This brings up the gateway, orchestrator, a single agent worker, Redis, and a local inference stub. See [`docs/local-dev.md`](docs/local-dev.md) for service-by-service instructions and how to point the inference layer at a real model.

### Running your first agent task

```bash
curl -X POST http://localhost:8080/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"task": "Summarize the latest release notes and file a ticket for any breaking changes."}'
```

Task status and results can be polled at `GET /v1/tasks/{task_id}`.

## Project structure

```
.
├── gateway/           # API gateway config and auth
├── orchestrator/      # Task planning, scheduling, checkpointing
├── agent-worker/      # Agent execution loop
├── tool-sandbox/      # Isolated tool execution environment
├── inference/         # Model serving configuration
├── infra/             # Kubernetes manifests, Terraform, Helm charts
├── docs/              # Architecture docs and diagrams
└── tests/             # Integration and load tests
```

## Roadmap

- [ ] Single-agent execution loop (planning, tool calling, retries)
- [ ] Gateway with auth and rate limiting
- [ ] Orchestrator with task queue
- [ ] Tool sandbox with allowlisted API calls
- [ ] Dedicated inference serving (vLLM)
- [ ] State checkpointing and crash recovery
- [ ] Distributed tracing
- [ ] Vector store integration for retrieval/memory
- [ ] Multi-tenant isolation
- [ ] CI/CD pipeline and model registry

Build order and rationale are described in [`docs/build-order.md`](docs/build-order.md).

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## License

[MIT](LICENSE) — update this section if you choose a different license.

## Status

This project is under active development. APIs and architecture may change without notice until the first tagged release.
