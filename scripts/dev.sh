#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"
OLLAMA_MODEL="${AGENTYX_LLM_MODEL:-qwen2.5:7b}"
OLLAMA_URL="http://localhost:11434"

log() {
    printf '[Agenyx] %s\n' "$*"
}

fail() {
    printf '[Agenyx] ERROR: %s\n' "$*" >&2
    exit 1
}

cleanup() {
    if [[ -n "${OLLAMA_PID:-}" ]] && kill -0 "$OLLAMA_PID" 2>/dev/null; then
        log "Stopping Ollama..."
        kill "$OLLAMA_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

command -v docker >/dev/null 2>&1 \
    || fail "Docker is not installed."

command -v ollama >/dev/null 2>&1 \
    || fail "Ollama is not installed. Install Ollama first."

docker info >/dev/null 2>&1 \
    || fail "Docker daemon is not running."

if ! curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    log "Ollama is not running."
    log "Starting Ollama on ${OLLAMA_HOST}..."

    OLLAMA_HOST="$OLLAMA_HOST" ollama serve >/tmp/agenyx-ollama.log 2>&1 &
    OLLAMA_PID=$!

    for _ in {1..30}; do
        if curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
            break
        fi

        if ! kill -0 "$OLLAMA_PID" 2>/dev/null; then
            cat /tmp/agenyx-ollama.log >&2
            fail "Ollama failed to start."
        fi

        sleep 1
    done

    curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1 \
        || fail "Ollama did not become ready."
else
    log "Ollama is already running."
fi

if ! curl -fsS "$OLLAMA_URL/api/tags" \
    | grep -q "\"name\":\"${OLLAMA_MODEL}\""; then

    log "Model ${OLLAMA_MODEL} is not installed."
    log "Pulling ${OLLAMA_MODEL}..."

    ollama pull "$OLLAMA_MODEL"
fi

log "Ollama is ready."
log "Model: ${OLLAMA_MODEL}"

log "Starting Agenyx..."

docker compose up -d --build

log "Waiting for Agenyx..."

for _ in {1..30}; do
    if curl -fsSk https://localhost:8443/health >/dev/null 2>&1; then
        break
    fi

    sleep 1
done

curl -fsSk https://localhost:8443/health >/dev/null 2>&1 \
    || fail "Agenyx gateway did not become ready."

log "Agenyx is ready."
log "Gateway: https://localhost:8443"
log "Health:  https://localhost:8443/health"

docker compose ps
