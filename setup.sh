#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
warn() { echo -e "  ${YELLOW}!${RESET} $1"; }
fail() { echo -e "  ${RED}✗${RESET} $1"; }
ERRORS=0

echo -e "\n${BOLD}multiagents setup${RESET}\n"

# --- Python ------------------------------------------------------------------
echo -e "${BOLD}Python${RESET}"

if ! command -v python3 &>/dev/null; then
    fail "python3 not found — install Python 3.12+"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [[ "$PY_MAJOR" -lt 3 || ("$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 12) ]]; then
    fail "Python $PY_VERSION found — requires 3.12+"
    exit 1
fi
ok "Python $PY_VERSION"

if [[ -z "$VIRTUAL_ENV" ]]; then
    if [[ ! -d .venv ]]; then
        python3 -m venv .venv
        ok "Created .venv"
    fi
    source .venv/bin/activate
    ok "Activated .venv"
else
    ok "Using active venv: $VIRTUAL_ENV"
fi

# Ensure pip is available inside the venv
if ! python3 -m pip --version &>/dev/null; then
    python3 -m ensurepip --upgrade >/dev/null 2>&1
fi

if python3 -m pip install -q -e ".[dev]" 2>&1; then
    ok "Installed Python dependencies"
else
    fail "Failed to install Python dependencies — run: pip install -e '.[dev]'"
    ERRORS=$((ERRORS + 1))
fi

# --- Node / pnpm -------------------------------------------------------------
echo -e "\n${BOLD}Frontend${RESET}"

if ! command -v node &>/dev/null; then
    fail "node not found — install Node.js 18+"
    ERRORS=$((ERRORS + 1))
else
    ok "Node $(node --version)"

    if ! command -v pnpm &>/dev/null; then
        warn "pnpm not found — installing via npm"
        if ! npm install -g pnpm 2>&1; then
            fail "Failed to install pnpm — run: npm install -g pnpm"
            ERRORS=$((ERRORS + 1))
        fi
    fi

    if command -v pnpm &>/dev/null; then
        ok "pnpm $(pnpm --version)"
        if (cd web && pnpm install --frozen-lockfile 2>/dev/null || pnpm install) 2>&1; then
            ok "Installed frontend dependencies"
        else
            fail "Failed to install frontend dependencies — run: cd web && pnpm install"
            ERRORS=$((ERRORS + 1))
        fi
    fi
fi

# --- Agent CLIs ---------------------------------------------------------------
echo -e "\n${BOLD}Agent CLIs${RESET}"

MISSING=()
for cli in claude codex kimi; do
    if command -v "$cli" &>/dev/null; then
        ok "$cli"
    else
        warn "$cli not found on PATH (optional — only needed to run that agent)"
        MISSING+=("$cli")
    fi
done

# --- Done ---------------------------------------------------------------------
if [[ $ERRORS -gt 0 ]]; then
    echo -e "\n${RED}${BOLD}Setup failed${RESET} — $ERRORS error(s) above need fixing.\n"
    exit 1
fi

echo -e "\n${GREEN}${BOLD}Ready!${RESET} Run ${BOLD}./start.sh${RESET} to launch.\n"

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo -e "${YELLOW}Note:${RESET} Missing CLIs: ${MISSING[*]}"
    echo -e "Install them or use ${BOLD}--agents${RESET} to select only available agents:"
    echo -e "  ./start.sh --agents claude\n"
fi
