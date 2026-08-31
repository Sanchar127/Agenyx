# Agenyx

**A production-oriented distributed AI agent runtime with semantic model routing, asynchronous task execution, isolated tool execution, and highly available shared state.**

Agenyx is designed as a distributed runtime for building and executing AI agents that can reason, call tools, execute long-running tasks, and dynamically route LLM requests to the most appropriate model.

The architecture separates agent reasoning, semantic routing, inference, asynchronous execution, tool isolation, and infrastructure into independently deployable services.

---

# Architecture

```text
                                  ┌──────────────────────┐
                                  │        Client        │
                                  └──────────┬───────────┘
                                             │
                                             ▼
                                  ┌──────────────────────┐
                                  │       Gateway        │
                                  │        Nginx         │
                                  └──────────┬───────────┘
                                             │
                                             ▼
                                  ┌──────────────────────┐
                                  │        Agent         │
                                  │      FastAPI         │
                                  │   Agent Runtime      │
                                  └──────────┬───────────┘
                                             │
                                             │ LLM Request
                                             ▼
                                  ┌──────────────────────┐
                                  │   Semantic Router    │
                                  │                      │
                                  │ Intent Classification│
                                  │ Model Selection      │
                                  │ Session State        │
                                  │ Model Affinity       │
                                  └──────────┬───────────┘
                                             │
                              ┌──────────────┼──────────────┐
                              │              │              │
                              ▼              ▼              ▼
                           Model A        Model B        Model C
                              │              │              │
                              └──────────────┼──────────────┘
                                             │
                                             ▼
                                  ┌──────────────────────┐
                                  │      Inference       │
                                  │   OpenAI Compatible  │
                                  │       FastAPI        │
                                  └──────────┬───────────┘
                                             │
                                             ▼
                                  ┌──────────────────────┐
                                  │        Ollama        │
                                  │     Local Models     │
                                  └──────────────────────┘


                     Asynchronous Execution Pipeline
                     ────────────────────────────────

                                  ┌──────────────────────┐
                                  │        Agent         │
                                  └──────────┬───────────┘
                                             │
                                             ▼
                                  ┌──────────────────────┐
                                  │     Orchestrator     │
                                  │          Go          │
                                  └──────────┬───────────┘
                                             │
                                             ▼
                                  ┌──────────────────────┐
                                  │    Valkey Streams    │
                                  │   Consumer Groups    │
                                  └──────────┬───────────┘
                                             │
                              ┌──────────────┼──────────────┐
                              ▼              ▼              ▼
                           Worker 1       Worker 2       Worker 3
                              │              │              │
                              └──────────────┼──────────────┘
                                             │
                                             ▼
                                  ┌──────────────────────┐
                                  │    Task Execution    │
                                  └──────────────────────┘


                         Tool Execution Pipeline
                         ───────────────────────

                                  ┌──────────────────────┐
                                  │        Agent         │
                                  └──────────┬───────────┘
                                             │
                                             │ Tool Call
                                             ▼
                                  ┌──────────────────────┐
                                  │       Sandbox        │
                                  │       FastAPI        │
                                  └──────────┬───────────┘
                                             │
                                             ▼
                                  ┌──────────────────────┐
                                  │    gVisor / runsc    │
                                  │ Isolated Execution   │
                                  └──────────────────────┘


                         High Availability State
                         ────────────────────────

                              ┌─────────────────────┐
                              │   Valkey Sentinel   │
                              │                     │
                              │    Sentinel 0       │
                              │    Sentinel 1       │
                              │    Sentinel 2       │
                              └──────────┬──────────┘
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │   Valkey Primary    │
                              │     StatefulSet     │
                              └─────────────────────┘
```

---

# Core Components

| Component         | Responsibility                                | Technology                                  |
| ----------------- | --------------------------------------------- | ------------------------------------------- |
| Gateway           | External API entry point and routing          | Nginx                                       |
| Agent             | Agent reasoning and tool orchestration        | Python / FastAPI                            |
| Semantic Router   | Semantic model selection and routing sessions | Go                                          |
| Inference         | OpenAI-compatible LLM interface               | Python / FastAPI                            |
| Model Backend     | Local LLM execution                           | Ollama                                      |
| Orchestrator      | Asynchronous task coordination                | Go                                          |
| Worker            | Background task processing                    | Python                                      |
| Sandbox           | Isolated tool/code execution                  | Python / FastAPI                            |
| Isolation Runtime | Secure execution boundary                     | gVisor / runsc                              |
| Task Queue        | Distributed task delivery                     | Valkey Streams                              |
| Shared State      | Execution and routing state                   | Valkey                                      |
| HA                | Primary discovery and failover                | Valkey Sentinel                             |
| Containerization  | Service packaging                             | Docker                                      |
| Deployment        | Production orchestration                      | Kubernetes                                  |
| Configuration     | Kubernetes resource management                | Kustomize                                   |
| Observability     | Metrics, logs and tracing                     | Prometheus / Grafana / Loki / OpenTelemetry |

---

# Why Agenyx?

Traditional AI agent implementations often look like:

```text
Request
   │
   ▼
Single Python Process
   │
   ├── LLM
   ├── Tools
   ├── State
   └── Background Tasks
```

This works for prototypes but becomes difficult to operate when:

* LLM requests become expensive
* Different requests require different models
* Agent tasks become long-running
* Workers need horizontal scaling
* A worker crashes during execution
* Generated code needs isolation
* Multiple router instances need shared state
* Model routing needs conversation awareness
* The application needs Kubernetes deployment

Agenyx separates these responsibilities:

```text
Gateway
   │
   ▼
Agent
   │
   ├──────────────► Semantic Router ───► Inference
   │
   ├──────────────► Sandbox
   │
   ▼
Orchestrator
   │
   ▼
Valkey Streams
   │
   ▼
Worker Pool
```

---

# Design Principles

## 1. Separate agent reasoning from infrastructure

The Agent focuses on the agent execution loop.

Infrastructure concerns such as:

* Model selection
* Asynchronous task processing
* Tool isolation
* Shared state
* Failover

are handled by dedicated components.

---

## 2. Semantic routing as a first-class component

Agenyx does not assume that every LLM request should use the same model.

The Semantic Router evaluates the request and selects an appropriate model according to the routing policy.

```text
Agent
  │
  ▼
Semantic Router
  │
  ├──► Fast model
  ├──► General model
  ├──► Reasoning model
  └──► Specialized model
```

This makes model selection an explicit part of the runtime rather than hardcoding a single model inside the Agent.

---

# Semantic Routing Pipeline

The semantic routing pipeline is one of the core components of Agenyx.

At a high level:

```text
User Request
     │
     ▼
Agent
     │
     ▼
Semantic Router
     │
     ├── Analyze request
     │
     ├── Determine semantic intent
     │
     ├── Evaluate routing policy
     │
     ├── Consider session state
     │
     ├── Consider model affinity
     │
     └── Select model
            │
            ▼
        Inference
            │
            ▼
        LLM Model
```

The router therefore acts as a decision layer between the Agent and the inference infrastructure.

---

# Session-Aware Semantic Routing

Agenyx supports routing decisions that are aware of the current conversation session.

A routing session can maintain telemetry such as:

```text
CurrentModel
TurnCount
SwitchCount
ModelTurns
LastDecisionName
```

This allows routing decisions to take previous turns into account.

For example:

```text
Turn 1
  │
  ▼
Router
  │
  └──► Model A

Turn 2
  │
  ▼
Router
  │
  └──► Model A

Turn 3
  │
  ▼
Router
  │
  └──► Model A

Turn 4
  │
  ▼
Router
  │
  └──► Model B
```

The router can maintain model affinity while still switching models when the routing policy determines that another model is more appropriate.

---

# Model Affinity

Model affinity reduces unnecessary model switching within a session.

For example:

```text
Session
   │
   ├── Request 1 ──► Model A
   │
   ├── Request 2 ──► Model A
   │
   ├── Request 3 ──► Model A
   │
   └── Request 4 ──► Model B
```

The router can continue using the current model when appropriate while allowing the semantic routing policy to switch models when the request characteristics change.

This can improve:

* Routing stability
* Latency
* Context continuity
* Model utilization

---

# Distributed Semantic Router

The Semantic Router is designed to support multiple router instances.

```text
                     Load Balancer
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
          Router 1     Router 2     Router 3
             │            │            │
             └────────────┼────────────┘
                          │
                          ▼
                   Shared Session State
                          │
                          ▼
                        Valkey
```

Router instances do not need to own permanent local session state.

Any router instance can retrieve the shared routing session and continue the decision process.

---

# Versioned Routing State

Concurrent router instances can potentially attempt to update the same routing session.

Agenyx uses versioned session state to prevent stale router decisions from silently overwriting newer state.

Conceptually:

```text
Session:

version = 10
current_model = model-a
turn_count = 5
```

A router reads the current state and attempts a conditional update:

```text
Read version 10
      │
      ▼
Make routing decision
      │
      ▼
Update only if version == 10
      │
      ├── Success
      │     │
      │     └── version = 11
      │
      └── Conflict
            │
            ▼
       Re-read state
```

This provides compare-and-swap style semantics for distributed routing updates.

---

# Inference Layer

The Inference service provides a stable OpenAI-compatible interface between the routing layer and model backends.

Current endpoints include:

```text
GET  /health
GET  /ready
GET  /v1/models
POST /v1/chat/completions
```

The architecture is:

```text
Agent
  │
  ▼
Semantic Router
  │
  ▼
Inference Service
  │
  ▼
Model Backend
  │
  ▼
Ollama
```

The Agent and Router therefore do not need to directly depend on Ollama's API.

This makes it possible to replace the model backend without redesigning the Agent runtime.

Potential future inference backends include:

* Ollama
* vLLM
* TGI
* Other OpenAI-compatible servers

---

# Ollama

Local development currently uses Ollama for model inference.

Ollama runs the actual local model while Agenyx provides the surrounding distributed runtime.

```text
Agenyx
   │
   ▼
Inference
   │
   ▼
Ollama
   │
   ▼
Local LLM
```

This allows Agenyx to be developed and tested locally without requiring a remote commercial LLM API.

---

# Agent Runtime

The Agent service implements the core agent execution loop.

Its responsibilities include:

* Receiving agent requests
* Building execution context
* Calling the semantic router
* Calling the inference layer
* Processing model responses
* Handling tool calls
* Sending tool requests to the sandbox
* Continuing the agent loop
* Returning the final response

The basic execution loop is:

```text
Request
   │
   ▼
Agent Runtime
   │
   ▼
Semantic Router
   │
   ▼
Inference
   │
   ▼
LLM
   │
   ├──────────────► Final response
   │
   └──────────────► Tool call
                         │
                         ▼
                      Sandbox
                         │
                         ▼
                    Tool result
                         │
                         ▼
                        LLM
```

---

# Tool Sandbox

Agenyx isolates tool execution from the main Agent process.

Instead of allowing generated code or potentially untrusted tools to execute directly inside the Agent container:

```text
Agent
  │
  ▼
Sandbox
  │
  ▼
gVisor / runsc
  │
  ▼
Isolated execution
```

The Sandbox is responsible for executing tools inside an isolated environment.

This creates a security boundary between:

```text
Agent Runtime
      │
      │ untrusted execution
      ▼
Sandbox
```

---

# gVisor

Agenyx uses **gVisor / runsc** for additional container-level isolation of sandbox workloads.

The sandbox can be configured with:

* Restricted Linux capabilities
* No privilege escalation
* Restricted networking
* Non-root execution
* Seccomp
* gVisor isolation

The goal is to avoid executing potentially untrusted generated code directly inside the Agent runtime.

---

# Asynchronous Task Processing

Long-running work is separated from synchronous request processing.

The asynchronous pipeline is:

```text
Agent
  │
  ▼
Orchestrator
  │
  ▼
Valkey Stream
  │
  ▼
Worker Pool
  │
  ▼
Task Execution
```

This allows the Worker layer to scale independently.

For example:

```text
                    Valkey Stream
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
          Worker 1    Worker 2    Worker 3
             │           │           │
             └───────────┼───────────┘
                         │
                         ▼
                    Task Execution
```

---

# Orchestrator

The Orchestrator coordinates asynchronous task execution.

It is responsible for:

* Receiving asynchronous work
* Creating execution records
* Publishing tasks
* Coordinating task lifecycle
* Communicating through Valkey
* Tracking task state

The Orchestrator does not need to execute every long-running task itself.

Instead, it publishes work to the distributed Worker pool.

---

# Worker

Workers are long-running task consumers.

Each Worker:

1. Connects to Valkey
2. Ensures the consumer group exists
3. Reads tasks from the stream
4. Executes tasks
5. Updates execution state
6. Acknowledges successfully handled tasks
7. Recovers abandoned pending tasks
8. Applies retry behavior
9. Sends permanently failed tasks to the dead-letter stream
10. Handles graceful shutdown

Workers use Valkey Streams consumer groups:

```text
Stream:
agenyx:tasks

Consumer Group:
agenyx-workers
```

Each Kubernetes worker pod receives its own consumer name.

---

# Pending Task Recovery

Valkey Streams maintain pending entries for messages that have been delivered but not acknowledged.

If a Worker crashes:

```text
Worker A
   │
   ▼
Task received
   │
   X
Worker crashes
   │
   ▼
Pending Entry
   │
   ▼
Worker B
   │
   ▼
Task reclaimed
```

Agenyx workers periodically reclaim abandoned pending tasks.

The behavior is configurable through:

```text
PENDING_IDLE_MS
PENDING_BATCH_SIZE
```

This provides crash recovery without requiring a separate distributed recovery system.

---

# Retry Handling

Agenyx supports configurable task retries.

Important configuration values include:

```text
MAX_ATTEMPTS
RETRY_BASE_DELAY_SECONDS
RETRY_MAX_DELAY_SECONDS
```

A task can move through:

```text
pending
   │
   ▼
processing
   │
   ├──────────────► completed
   │
   ├──────────────► retrying
   │                    │
   │                    ▼
   │                processing
   │
   └──────────────► failed
                         │
                         ▼
                        DLQ
```

Retry timing is stored as execution state rather than relying only on local Worker memory.

---

# Dead-Letter Queue

Tasks that cannot be successfully processed after the configured retry limit are moved to a dead-letter stream.

Default stream:

```text
agenyx:tasks:dead-letter
```

Dead-letter records contain information such as:

```text
execution_id
intent
attempt
original_message_id
error
consumer
```

This provides a durable location for permanently failed tasks.

---

# Valkey

Valkey is a central infrastructure component in Agenyx.

It is used for:

* Streams
* Consumer groups
* Pending task tracking
* Execution state
* Shared routing session state
* Model affinity state
* Distributed coordination

The task stream is:

```text
agenyx:tasks
```

The Worker consumer group is:

```text
agenyx-workers
```

---

# Valkey Sentinel

Agenyx uses Valkey Sentinel for high availability and primary discovery.

The Kubernetes deployment contains:

```text
Valkey
└── StatefulSet
    └── Primary

Sentinel
├── Sentinel 0
├── Sentinel 1
└── Sentinel 2
```

Sentinel monitors the Valkey primary and provides failover coordination.

Applications should discover the current primary through Sentinel rather than relying on a permanently fixed primary address.

Configuration is supplied through environment variables such as:

```text
VALKEY_SENTINEL_HOSTS
VALKEY_MASTER_NAME
VALKEY_PASSWORD
```

Example:

```text
VALKEY_MASTER_NAME=mymaster
```

The actual Kubernetes service and Sentinel addresses are supplied through Kubernetes configuration.

---

# Configuration

Agenyx avoids hardcoding environment-specific infrastructure addresses in application logic.

Configuration is provided through environment variables and Kubernetes ConfigMaps/Secrets.

Examples include:

```text
VALKEY_SENTINEL_HOSTS
VALKEY_MASTER_NAME
VALKEY_PASSWORD

TASK_STREAM
CONSUMER_GROUP
CONSUMER_NAME

AGENT_URL
AGENT_TIMEOUT_SECONDS

MAX_ATTEMPTS
RETRY_BASE_DELAY_SECONDS
RETRY_MAX_DELAY_SECONDS

PENDING_IDLE_MS
PENDING_BATCH_SIZE
```

Secrets such as Valkey passwords are stored in Kubernetes Secrets rather than ConfigMaps.

---

# Kubernetes

Agenyx is designed to run as independently deployable Kubernetes workloads.

Current deployment structure:

```text
deploy/
└── kubernetes/
    ├── agent/
    ├── worker/
    ├── orchestrator/
    ├── inference/
    ├── gateway/
    ├── sandbox/
    └── valkey/
```

The Kubernetes deployment uses Kustomize.

---

# Valkey Kubernetes Resources

The Valkey deployment includes:

```text
deploy/kubernetes/valkey/

├── kustomization.yaml
├── secret.yaml
├── service.yaml
├── statefulset.yaml
├── networkpolicy.yaml
├── sentinel-configmap.yaml
├── sentinel-statefulset.yaml
└── sentinel-networkpolicy.yaml
```

The Valkey primary runs as a StatefulSet.

Sentinel runs as a separate StatefulSet with three replicas.

---

# Worker Kubernetes Deployment

Workers run as Kubernetes Deployment replicas.

Example:

```text
agenyx-worker
├── Worker Pod
├── Worker Pod
└── Worker Pod
```

Workers are configured to:

* Run as non-root
* Drop Linux capabilities
* Disable privilege escalation
* Use RuntimeDefault seccomp
* Use resource requests and limits
* Gracefully terminate
* Spread replicas across nodes when possible

The Worker receives its Kubernetes pod name as its consumer identity:

```text
CONSUMER_NAME = metadata.name
```

This ensures that each Worker has a unique consumer name.

---

# Kubernetes Security

Agenyx applies security controls at multiple layers.

## Container security

Services use:

```text
runAsNonRoot
allowPrivilegeEscalation: false
capabilities:
  drop:
    - ALL
seccompProfile:
  type: RuntimeDefault
```

Where appropriate, containers use:

```text
readOnlyRootFilesystem: true
```

---

## Service accounts

Worker pods use dedicated Kubernetes service accounts.

Where Kubernetes API access is not required:

```text
automountServiceAccountToken: false
```

This reduces unnecessary access to Kubernetes credentials.

---

## Network policies

Kubernetes NetworkPolicies are used to control communication between services.

The goal is to avoid exposing every service to every other service.

---

# Docker

Each Agenyx service can be packaged as a Docker image.

Example Worker image:

```dockerfile
FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "app.main"]
```

Images are then deployed to the Kubernetes container runtime.

---

# Local Development

## Prerequisites

Install:

* Docker
* Docker Compose
* Python 3.12+
* Go
* Ollama
* kubectl
* A local or remote Kubernetes cluster

Agenyx does not require Kind specifically.

Any Kubernetes cluster capable of running the required workloads can be used.

---

# Start with Docker Compose

Build and start the services:

```bash
docker compose up -d --build
```

Check services:

```bash
docker compose ps
```

Follow logs:

```bash
docker compose logs -f
```

---

# Kubernetes Deployment

Apply the Kubernetes configuration using Kustomize:

```bash
kubectl apply -k deploy/kubernetes
```

Check the namespace:

```bash
kubectl get pods -n agenyx
```

Check services:

```bash
kubectl get svc -n agenyx
```

Check deployments:

```bash
kubectl get deployments -n agenyx
```

Check StatefulSets:

```bash
kubectl get statefulsets -n agenyx
```

---

# Building Images for Kubernetes

Build a service image:

```bash
docker build -t agenyx-worker:0.1.0 ./worker
```

For Kubernetes clusters using the local container runtime, ensure the image is available to the runtime used by the cluster.

Verify the image through the container runtime.

Then restart the deployment:

```bash
kubectl -n agenyx rollout restart deployment/agenyx-worker
```

Check rollout:

```bash
kubectl -n agenyx rollout status deployment/agenyx-worker
```

Check pods:

```bash
kubectl -n agenyx get pods -l app.kubernetes.io/name=agenyx-worker -o wide
```

---

# Debugging Kubernetes

Check pod details:

```bash
kubectl -n agenyx describe pod <pod-name>
```

View logs:

```bash
kubectl -n agenyx logs <pod-name>
```

Follow logs:

```bash
kubectl -n agenyx logs -f <pod-name>
```

View logs from the previous crashed container:

```bash
kubectl -n agenyx logs <pod-name> --previous
```

Check recent events:

```bash
kubectl -n agenyx get events --sort-by=.lastTimestamp
```

---

# Health Checks

Services expose health/readiness endpoints where appropriate.

Typical checks include:

```text
/health
/ready
```

Kubernetes readiness and liveness probes are used to prevent unhealthy instances from receiving traffic.

---

# Observability

Agenyx is designed to integrate with a production observability stack.

The planned/used observability components include:

```text
OpenTelemetry
      │
      ├──► Traces
      │
      ▼
Prometheus
      │
      ▼
Grafana


Application Logs
      │
      ▼
Loki
      │
      ▼
Grafana
```

Important observability signals include:

* Request latency
* Task processing latency
* Task success/failure counts
* Retry counts
* Pending tasks
* Worker health
* Model routing decisions
* Model switching
* Inference latency
* Sandbox execution failures

---

# Project Structure

Agenyx is organized around independent services:

```text
.
├── agent/
│   ├── app/
│   ├── tests/
│   └── Dockerfile
│
├── orchestrator/
│   ├── ...
│   └── Dockerfile
│
├── worker/
│   ├── app/
│   ├── tests/
│   └── Dockerfile
│
├── inference/
│   ├── app/
│   │   ├── backend.py
│   │   ├── config.py
│   │   └── main.py
│   └── Dockerfile
│
├── sandbox/
│   ├── ...
│   └── Dockerfile
│
├── gateway/
│   └── ...
│
├── deploy/
│   └── kubernetes/
│       ├── agent/
│       ├── worker/
│       ├── orchestrator/
│       ├── inference/
│       ├── gateway/
│       ├── sandbox/
│       └── valkey/
│
├── scripts/
│   └── setup-gvisor.sh
│
├── docs/
│   └── ...
│
└── docker-compose.yml
```

---

# End-to-End Request Flow

A normal agent request follows this path:

```text
Client
  │
  ▼
Gateway
  │
  ▼
Agent
  │
  ▼
Semantic Router
  │
  ├── Session state
  ├── Model affinity
  ├── Semantic decision
  └── Model selection
          │
          ▼
      Inference
          │
          ▼
        Ollama
          │
          ▼
      Model Response
          │
          ├──────────────► Final Answer
          │
          └──────────────► Tool Call
                                │
                                ▼
                             Sandbox
                                │
                                ▼
                         Tool Execution
                                │
                                ▼
                            Tool Result
                                │
                                ▼
                               Agent
```

---

# End-to-End Asynchronous Flow

Long-running work follows a separate pipeline:

```text
Client
  │
  ▼
Gateway
  │
  ▼
Agent / Orchestrator
  │
  ▼
Execution Record
  │
  ▼
Valkey Stream
  │
  ▼
Consumer Group
  │
  ├──────────────┐
  ▼              ▼
Worker 1       Worker 2
  │              │
  └───────┬──────┘
          │
          ▼
      Task Execution
          │
          ├── Success
          │
          ├── Retry
          │
          └── Dead Letter
```

---

# Failure Recovery

Agenyx is designed around failure as a normal operating condition.

Examples:

## Worker crash

```text
Worker A
   │
   X crash
   │
   ▼
Pending task
   │
   ▼
Worker B
   │
   ▼
Task recovery
```

## LLM failure

```text
Inference failure
       │
       ▼
Agent / Worker
       │
       ▼
Retry policy
       │
       ├── Retry
       │
       └── Permanent failure
```

## Valkey primary failure

```text
Valkey Primary
      │
      X
      │
      ▼
Sentinel detects failure
      │
      ▼
Failover
      │
      ▼
New Primary
```

## Router replica failure

```text
Router 1
   │
   X
   │
   ▼
Router 2
   │
   ▼
Shared routing session
   │
   ▼
Continue routing
```

---

# Current Technology Stack

### Backend

* Python
* FastAPI
* Go

### AI / LLM

* Ollama
* OpenAI-compatible inference API
* Semantic model routing
* Session-aware routing

### Distributed Systems

* Valkey
* Valkey Streams
* Consumer Groups
* Valkey Sentinel
* Kubernetes

### Security

* gVisor
* runsc
* Kubernetes NetworkPolicies
* Linux capabilities
* Seccomp

### Infrastructure

* Docker
* Docker Compose
* Kubernetes
* Kustomize

### Observability

* OpenTelemetry
* Prometheus
* Grafana
* Loki

---

# Roadmap

The architecture is designed to evolve toward a larger distributed AI platform.

Potential future improvements include:

* [ ] More advanced semantic routing policies
* [ ] Additional model providers
* [ ] GPU-backed inference with vLLM
* [ ] Dynamic model health scoring
* [ ] Routing based on latency and model availability
* [ ] More sophisticated model affinity policies
* [ ] Multi-tenant isolation
* [ ] Authentication and authorization
* [ ] API rate limiting
* [ ] Distributed tracing across all services
* [ ] Advanced task scheduling
* [ ] Task prioritization
* [ ] DLQ replay tooling
* [ ] Persistent database for execution history
* [ ] Vector-based retrieval and long-term memory
* [ ] Automated CI/CD
* [ ] Production model registry
* [ ] Kubernetes autoscaling based on workload metrics
* [ ] GPU inference cluster

---

# Development Philosophy

Agenyx intentionally separates infrastructure responsibilities instead of placing everything into one application.

The core architecture is:

```text
             ┌─────────────────────┐
             │       Gateway       │
             └──────────┬──────────┘
                        │
                        ▼
             ┌─────────────────────┐
             │       Agent         │
             └──────┬──────┬───────┘
                    │      │
                    │      └───────────────┐
                    ▼                      ▼
          Semantic Router              Sandbox
                    │
                    ▼
               Inference
                    │
                    ▼
                 Ollama


                    Agent
                      │
                      ▼
                Orchestrator
                      │
                      ▼
                Valkey Streams
                      │
              ┌───────┼───────┐
              ▼       ▼       ▼
           Worker  Worker  Worker
```

The goal is not to add infrastructure simply for the sake of complexity.

Each component exists because it solves a specific distributed-system problem:

| Problem                 | Agenyx Component                            |
| ----------------------- | ------------------------------------------- |
| External API access     | Gateway                                     |
| Agent reasoning         | Agent                                       |
| Model selection         | Semantic Router                             |
| LLM execution           | Inference                                   |
| Local model backend     | Ollama                                      |
| Long-running tasks      | Orchestrator                                |
| Distributed execution   | Worker Pool                                 |
| Tool isolation          | Sandbox                                     |
| Secure execution        | gVisor                                      |
| Task distribution       | Valkey Streams                              |
| Shared routing state    | Valkey                                      |
| High availability       | Valkey Sentinel                             |
| Container orchestration | Kubernetes                                  |
| Observability           | OpenTelemetry / Prometheus / Grafana / Loki |

---

# Status

Agenyx is under active development.

The core architecture currently focuses on:

* Distributed Agent execution
* Semantic model routing
* Session-aware routing
* Model affinity
* Versioned routing state
* OpenAI-compatible inference
* Ollama integration
* Asynchronous task execution
* Valkey Streams
* Consumer groups
* Pending task recovery
* Retry handling
* Dead-letter processing
* Valkey Sentinel
* gVisor sandbox isolation
* Kubernetes deployment

APIs, internal protocols, and deployment configuration may continue to evolve as the system moves toward production readiness.

---

# gVisor Sandbox Setup

Linux developers can configure gVisor using:

```bash
./scripts/setup-gvisor.sh
```

Verify that `runsc` is available:

```bash
docker info | grep -A10 Runtimes
```

`runsc` should appear in the available Docker runtimes.

Then start Agenyx:

```bash
docker compose up -d --build
```

---

# License

This project is currently under active development.

Add the appropriate license here when the project is ready for public distribution.
