
#!/usr/bin/env bash

set -Eeuo pipefail

DAEMON_JSON="/etc/docker/daemon.json"
RUNSC="/usr/bin/runsc"
CONTAINER="agenyx-sandbox"

log() {
    echo "==> $1"
}

fail() {
    echo "✗ $1" >&2
    exit 1
}

[[ $EUID -eq 0 ]] && SUDO="" || SUDO="sudo"

# ─────────────────────────────────────────────
# Prerequisites
# ─────────────────────────────────────────────

command -v docker >/dev/null || fail "Docker is not installed."
command -v curl >/dev/null || fail "curl is not installed."
command -v gpg >/dev/null || fail "gpg is not installed."
command -v python3 >/dev/null || fail "python3 is not installed."

# ─────────────────────────────────────────────
# Install gVisor
# ─────────────────────────────────────────────

log "Installing gVisor..."

$SUDO mkdir -p /usr/share/keyrings

curl -fsSL https://gvisor.dev/archive.key |
    $SUDO gpg --dearmor --yes \
    -o /usr/share/keyrings/gvisor-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" |
    $SUDO tee /etc/apt/sources.list.d/gvisor.list >/dev/null

$SUDO apt-get update
$SUDO apt-get install -y runsc

[[ -x "$RUNSC" ]] || fail "runsc was not installed."

echo "runsc: $("$RUNSC" --version | head -n1)"

# ─────────────────────────────────────────────
# Configure Docker
# ─────────────────────────────────────────────

log "Configuring Docker runtime..."

$SUDO mkdir -p /etc/docker

TMP_CONFIG="$(mktemp)"
trap 'rm -f "$TMP_CONFIG"' EXIT

python3 - "$DAEMON_JSON" "$RUNSC" "$TMP_CONFIG" <<'PY'
import json
import os
import sys

daemon_json = sys.argv[1]
runsc = sys.argv[2]
tmp_config = sys.argv[3]

if os.path.exists(daemon_json):
    with open(daemon_json, encoding="utf-8") as f:
        config = json.load(f)
else:
    config = {}

if not isinstance(config, dict):
    raise SystemExit("daemon.json must contain a JSON object")

runtimes = config.setdefault("runtimes", {})

if not isinstance(runtimes, dict):
    raise SystemExit('"runtimes" must be a JSON object')

runtimes["runsc"] = {
    "path": runsc,
    "runtimeArgs": [
        "--network=none"
    ]
}

with open(tmp_config, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PY

# Validate generated configuration
python3 - "$TMP_CONFIG" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    config = json.load(f)

runsc = config.get("runtimes", {}).get("runsc")

if not runsc:
    raise SystemExit("runsc runtime is missing")

if runsc.get("path") != "/usr/bin/runsc":
    raise SystemExit("runsc path is incorrect")

if "--network=none" not in runsc.get("runtimeArgs", []):
    raise SystemExit("runsc network isolation is not configured")

print("Docker configuration is valid.")
PY

# Install with root permissions
$SUDO install -m 0644 "$TMP_CONFIG" "$DAEMON_JSON"

echo "✓ Docker runtime configured."

# ─────────────────────────────────────────────
# Restart Docker
# ─────────────────────────────────────────────

log "Restarting Docker..."

$SUDO systemctl restart docker
sleep 2

$SUDO systemctl is-active --quiet docker ||
    fail "Docker failed to start."

echo "✓ Docker is running."

# ─────────────────────────────────────────────
# Verify runtime
# ─────────────────────────────────────────────

log "Verifying Docker runtime..."

docker info --format '{{json .Runtimes}}' |
    grep -q '"runsc"' ||
    fail "Docker does not recognize runsc."

echo "✓ Docker recognizes runsc."

# ─────────────────────────────────────────────
# Test gVisor directly
# ─────────────────────────────────────────────

log "Testing gVisor..."

docker run --rm \
    --runtime=runsc \
    --network=none \
    alpine:latest \
    true

echo "✓ gVisor runtime works."

# ─────────────────────────────────────────────
# Build and start sandbox
# ─────────────────────────────────────────────

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_ROOT"

log "Building Agenyx sandbox..."
docker compose build sandbox

log "Starting Agenyx sandbox..."

docker compose rm -sf sandbox >/dev/null 2>&1 || true
docker compose up -d sandbox

# ─────────────────────────────────────────────
# Verify sandbox
# ─────────────────────────────────────────────

log "Verifying sandbox..."

for _ in {1..20}; do
    STATUS="$(docker inspect \
        --format '{{.State.Status}}' \
        "$CONTAINER" 2>/dev/null || true)"

    [[ "$STATUS" == "running" ]] && break

    sleep 1
done

STATUS="$(docker inspect \
    --format '{{.State.Status}}' \
    "$CONTAINER" 2>/dev/null || true)"

[[ "$STATUS" == "running" ]] ||
    fail "Sandbox container is not running."

RUNTIME="$(docker inspect \
    --format '{{.HostConfig.Runtime}}' \
    "$CONTAINER")"

[[ "$RUNTIME" == "runsc" ]] ||
    fail "Sandbox is not using runsc."

NETWORK="$(docker inspect \
    --format '{{.HostConfig.NetworkMode}}' \
    "$CONTAINER")"

[[ "$NETWORK" == "none" ]] ||
    fail "Sandbox network is not disabled: $NETWORK"

READ_ONLY="$(docker inspect \
    --format '{{.HostConfig.ReadonlyRootfs}}' \
    "$CONTAINER")"

[[ "$READ_ONLY" == "true" ]] ||
    fail "Sandbox root filesystem is not read-only."

CAP_DROP="$(docker inspect \
    --format '{{json .HostConfig.CapDrop}}' \
    "$CONTAINER")"

echo "$CAP_DROP" | grep -q '"ALL"' ||
    fail "Sandbox does not drop all capabilities."

SECURITY_OPT="$(docker inspect \
    --format '{{json .HostConfig.SecurityOpt}}' \
    "$CONTAINER")"

echo "$SECURITY_OPT" | grep -q "no-new-privileges" ||
    fail "no-new-privileges is not enabled."

# ─────────────────────────────────────────────
# Verify gVisor kernel
# ─────────────────────────────────────────────

log "Verifying gVisor kernel..."

docker exec "$CONTAINER" dmesg 2>/dev/null |
    grep -q "Starting gVisor" ||
    fail "gVisor kernel could not be verified."

# ─────────────────────────────────────────────
# Success
# ─────────────────────────────────────────────

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ Agenyx gVisor sandbox setup completed."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "Runtime:       $RUNTIME"
echo "Network:       $NETWORK"
echo "Read-only FS:  $READ_ONLY"
echo "Capabilities:  ALL dropped"
echo "Privileges:    no-new-privileges"
echo "gVisor:        ACTIVE"
echo
echo "Run:"
echo "  docker compose up -d"
echo
