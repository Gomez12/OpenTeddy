#!/usr/bin/env bash
#
# Start all OpenTeddy services.
# Press Ctrl-C to shut down everything cleanly.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env
set -a
source .env 2>/dev/null || true
set +a

PIDS=()

cleanup() {
    echo ""
    echo "Shutting down services..."
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
        fi
    done
    # Wait briefly, then force-kill stragglers
    sleep 2
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null
        fi
    done
    echo "All services stopped."
}

trap cleanup EXIT INT TERM

# --- OpenSandbox server ---
echo "Starting OpenSandbox server on port 8080..."
DOCKER_HOST="unix://$HOME/.docker/run/docker.sock" \
    uv run opensandbox-server --config .sandbox.toml &
PIDS+=($!)

# --- Embedding server ---
EMBED_PORT="${EMBED_PORT:-8100}"
echo "Starting Embedding server on port ${EMBED_PORT}..."
uv run uvicorn agentic.servers.embedding_server:app \
    --host 0.0.0.0 \
    --port "$EMBED_PORT" \
    --log-level info &
PIDS+=($!)

echo ""
echo "Services running:"
echo "  OpenSandbox : http://localhost:8080"
echo "  Embeddings  : http://localhost:${EMBED_PORT}/v1/embeddings"
echo ""
echo "Press Ctrl-C to stop all services."
echo ""

# Wait a moment to catch immediate startup failures
sleep 3

for i in "${!PIDS[@]}"; do
    if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
        echo "ERROR: Service (PID ${PIDS[$i]}) failed to start. Check output above."
        exit 1
    fi
done

echo "All services started successfully."
echo ""

# Keep running until Ctrl-C — check every 5 seconds if services are still alive
while true; do
    for i in "${!PIDS[@]}"; do
        if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
            echo "Service (PID ${PIDS[$i]}) exited unexpectedly."
            exit 1
        fi
    done
    sleep 5
done
