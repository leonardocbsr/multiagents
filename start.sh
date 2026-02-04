#!/bin/bash
set -e

PORT=8421
AGENTS="claude,codex,kimi"

while [[ $# -gt 0 ]]; do
    case $1 in
        --port)    PORT="$2";   shift 2 ;;
        --agents)  AGENTS="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: ./start.sh [--port PORT] [--agents AGENTS]"
            echo "  --port    Backend port (default: 8421)"
            echo "  --agents  Comma-separated agent list (default: claude,codex,kimi)"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "$VIRTUAL_ENV" && -d "$SCRIPT_DIR/.venv" ]]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

exec npx concurrently \
    --kill-others \
    --names "api,web" \
    --prefix "[{name}]" \
    --prefix-colors "blue,magenta" \
    "python3 -m src.main --port $PORT --agents $AGENTS" \
    "cd $SCRIPT_DIR/web && pnpm dev"
