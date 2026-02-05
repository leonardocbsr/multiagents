#!/bin/bash
set -euo pipefail

PORT=8421
AGENTS="claude,codex,kimi"
BACKEND="python"

while [[ $# -gt 0 ]]; do
    case $1 in
        --backend) BACKEND="$2"; shift 2 ;;
        --port)    PORT="$2";   shift 2 ;;
        --agents)  AGENTS="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: ./start.sh [--backend python] [--port PORT] [--agents AGENTS]"
            echo "  --backend  Backend runtime (default: python)"
            echo "             python: FastAPI backend + frontend"
            echo "  --port    Backend port (default: 8421)"
            echo "  --agents  Comma-separated agent list (default: claude,codex,kimi)"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prefer the project's virtualenv interpreter when available, even if another
# virtualenv is active in the shell.
if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    PYTHON_CMD="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON_CMD="python3"
fi

cleanup() {
    kill $API_PID $WEB_PID 2>/dev/null
    wait $API_PID $WEB_PID 2>/dev/null
}
check_port_in_use() {
    local port="$1"
    local label="$2"
    local pids
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
        echo "Error: $label port $port is already in use by PID(s): $pids"
        echo "Stop them first, e.g.: kill $pids"
        exit 1
    fi
}

check_port_in_use "$PORT" "API"
check_port_in_use "5174" "Web"

cd "$SCRIPT_DIR"

if [[ "$BACKEND" == "python" ]]; then
    exec npx concurrently \
        --kill-others \
        --names "api,web" \
        --prefix "[{name}]" \
        --prefix-colors "blue,magenta" \
        "PYTHONUNBUFFERED=1 $PYTHON_CMD -m src.main --port $PORT --agents $AGENTS" \
        "cd $SCRIPT_DIR/web && pnpm dev"
else
    echo "Unknown backend: $BACKEND (expected python)"
    exit 1
fi
