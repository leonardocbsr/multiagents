# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-agent group chat application. A human user converses with multiple AI agents (Claude, Codex, Kimi) simultaneously in round-based discussions. Agents respond concurrently each round and signal `[PASS]` when they have nothing to add. The discussion ends when all agents pass.

## Commands

### Backend (Python 3.12+)

```bash
pip install -e .                          # Install dependencies
python -m src.main                        # Run server (default port 8421)
multiagents --agents claude,codex --port 8080  # Custom options
pytest                                    # Run all tests
pytest tests/test_room.py                 # Run single test file
pytest tests/test_room.py -k test_name    # Run single test
```

### Frontend (TypeScript, pnpm)

```bash
cd web && pnpm install                    # Install dependencies
cd web && pnpm dev                        # Dev server (port 5174, proxies to backend)
cd web && pnpm build                      # Production build to web/dist/
```

### Full Stack

```bash
./start.sh                               # Dev mode: backend + frontend with prefixed logs
./start.sh --port 8080 --agents claude,codex  # Custom options
```

## Architecture

### Backend (`src/`)

Three layers: **agents** spawn and stream from external CLI tools, **chat** orchestrates multi-round discussions, **server** handles WebSocket connections and persistence.

**Agent layer** (`src/agents/`): Each agent (Claude, Codex, Kimi) inherits `BaseAgent` and wraps an external CLI. Agents spawn async subprocesses that emit JSON lines. Key override points: `_build_args()`, `_parse_stream_line()`, `_parse_output()`, `_extract_session_id()`. Agents support session resumption via persisted CLI session IDs.

**Chat layer** (`src/chat/`): `ChatRoom` runs rounds as an async generator yielding typed `ChatEvent` dataclasses (`RoundStarted`, `AgentStreamChunk`, `AgentCompleted`, `RoundEnded`, `DiscussionEnded`). `router.py` handles prompt formatting with conversation history, `[PASS]` detection, coordination pattern extraction, and `<Share>` tag protocol.

**Server layer** (`src/server/`): FastAPI app with WebSocket at `/ws` and REST at `/api/sessions`. `SessionRunner` manages per-session chat tasks, WebSocket subscriber broadcast, and pre-warmed agent pools. `SessionStore` uses SQLite with WAL mode at `~/.multiagents/multiagents.db`.

### Frontend (`web/src/`)

React 19 + Tailwind CSS 4 SPA. `useWebSocket` hook manages the connection lifecycle with auto-reconnect (exponential backoff) and a reducer for state updates. The WebSocket protocol uses `event_id` for replay on reconnect.

### Key Protocols

**Coordination patterns** are parsed both in `src/chat/router.py` (backend) and `web/src/types.ts` (frontend) using matching regexes. Patterns: `@AgentName` (mention), `+1 AgentName` (agreement), `[HANDOFF:Agent]`, `[EXPLORE]`, `[DECISION]`, `[BLOCKED]`, `[DONE]`, `[TODO]`, `[QUESTION]`.

**Share tags**: Agents wrap coordinated content in `<Share>...</Share>`. Backend extracts shareable content via `extract_shareable()` for history; content outside tags stays private.

**Tool badges**: Streaming output wraps tool use in `<tool>Name detail</tool>` tags. Frontend renders these as inline UI badges.

**WebSocket message types**: Server sends `connected`, `session_created`, `session_joined`, `round_started`, `agent_stream`, `agent_completed`, `round_ended`, `discussion_ended`, `paused`, `resumed`, `error`. Client sends `create_session`, `join_session`, `message`, `pause`, `resume`, `cancel`, `ack`, `metric`.

## Testing

pytest with `asyncio_mode = "auto"`. Tests use `FakeAgent` mocks (defined in test files) to simulate agent behavior without spawning real CLIs.

## Environment

- Backend default port: **8421**
- Frontend dev port: **5174** (Vite proxies `/ws` and `/api` to backend)
- Production: set `STATIC_DIR` env var to serve `web/dist/` from backend
- Required external CLIs: `claude`, `codex`, `kimi` (must be in `$PATH`)
- Database: `~/.multiagents/multiagents.db` (SQLite, WAL mode)
- Agent work dirs: `/tmp/multiagents-<agent>-<uuid>/`
- **Important**: Agents must use **absolute paths** (e.g., `/path/to/repo/...`) to access project files, as their CWD is isolated.
