# Agenyx

**A runtime for building, deploying, and running AI agents.**

Agenyx brings together AI agent orchestration, model inference, tool execution, and asynchronous task processing in one deployable platform. It is designed to make it easier to run and manage AI agents using configurable models and isolated execution environments.

## Quick Start

### Prerequisites

- Docker
- Docker Compose
- Git

### Clone the repository

```bash
git clone https://github.com/Sanchar127/Agenyx.git
cd Agenyx
```

### Configure environment

Configure your environment variables in the `.env` file.

### Start Agenyx

```bash
./agenyx serve
```

This command builds and starts the Agenyx services using Docker Compose.

### Check running services

```bash
docker compose ps
```

## Kubernetes Deployment (Production)

Agenyx includes a production-grade, consolidated Kubernetes deployment under
`deploy/kubernetes/`. All platform services (agent, inference, orchestrator,
router, worker, valkey) are declared in one place (`deploy/kubernetes/agenyx/`)
with ConfigMaps, Secrets, ServiceAccounts, Services, Deployments/StatefulSets,
HPAs, PDBs, NetworkPolicies, ServiceMonitors, and alerting rules.

Centralized observability (`deploy/kubernetes/monitoring/`) provides Prometheus
metrics, Loki logs, Tempo traces, and Grafana dashboards for **all** services.

### Prerequisites

- A running Kubernetes cluster (v1.25+)
- `kubectl` configured to the cluster
- A `StorageClass` (e.g. `local-path`) for Valkey/Prometheus persistence

### Deploy

```bash
# Deploy the platform + centralized monitoring
kubectl apply --kustomize deploy/kubernetes

# Verify the platform services
kubectl -n agenyx get deploy,sts,svc,hpa,pdb

# Verify monitoring
kubectl -n monitoring get prometheus,grafana,alertmanager,servicemonitor

# Access Grafana (port-forward)
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
# Open http://localhost:3000  (admin / prom-operator)
```

### Services (cluster-internal)

| Service | Port |
|---------|------|
| agenyx-agent | 8000 |
| agenyx-router | 8005 |
| agenyx-inference | 8004 |
| agenyx-orchestrator | 8002 |
| agenyx-worker | 8003 |
| valkey | 6379 |

### Environment

Create a `.env` file at the repository root with required secrets (see the
Kubernetes Secrets in `deploy/kubernetes/agenyx/secrets.yaml` — replace the
development placeholder values before production):

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENEYX_API_KEY` | Yes | Gateway API key |
| `INFERENCE_SERVICE_API_KEY` | Yes | Inference service API key |
| `AGENTYX_DATABASE_URL` | Yes | Agent PostgreSQL URL |
| `AGENEYX_MCP_GATEWAY_TOKEN` | Yes | MCP gateway token |
| `OPENAI_API_KEY` | No | OpenAI provider key |
| `AGENEYX_CORS_ORIGIN` | No | Allowed CORS origin |

## Resources

| Resource | Link |
|---|---|
| Documentation | Coming soon |
| Playground | Coming soon |
| GitHub Repository | [Agenyx](https://github.com/Sanchar127/Agenyx) |
| Issues & Feedback | [GitHub Issues](https://github.com/Sanchar127/Agenyx/issues) |


---

**Agenyx is under active development.** More documentation and examples will be added as the project evolves.
