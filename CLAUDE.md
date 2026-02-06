# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-agent group chat application. A human user converses with multiple AI agents (Claude, Codex, Kimi) in an event-driven runtime with round tracking. Agents react to incoming events, use `[PASS]` when they have nothing new to add, and rounds settle when all agents are idle with empty inboxes.

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

### Setup

```bash
./setup.sh                               # First-time setup: venv, deps, CLI validation
multiagents init                         # Initialize .multiagents/ dir for memory
```

### Full Stack

```bash
./start.sh                               # Dev mode: backend + frontend with prefixed logs
./start.sh --port 8080 --agents claude,codex  # Custom options
```

## Architecture

### Backend (`src/`)

Five layers: **agents** spawn and stream from external CLI tools via protocol adapters, **chat** orchestrates event-driven messaging with round settlement, **memory** provides cross-session learning, **cards** runs kanban workflows, **server** handles WebSocket connections and persistence.

**Agent layer** (`src/agents/`): Each agent (Claude, Codex, Kimi) inherits `BaseAgent` and wraps an external CLI. `PersistentAgent` (`persistent.py`) manages long-lived subprocesses with bidirectional stdio, crash recovery (exponential backoff, max 3 retries), and session ID tracking for resume. Key override points on `BaseAgent`: `_build_persistent_args()`, `_build_persistent_resume_args()`, `_get_protocol()`, `_get_cwd()`.

**Protocol adapters** (`src/agents/protocols/`): Each CLI has a dedicated `ProtocolAdapter` subclass that translates wire-level JSON into common event types (`TextDelta`, `ThinkingDelta`, `ToolBadge`, `TurnComplete`). Interface: `send_message()`, `read_events()`, `cancel()`, `shutdown()`.
- `ClaudeProtocol`: NDJSON stream-json. Handles `system` (init, compact_boundary), `assistant` (text, thinking, tool_use, server_tool_use, web_search, code_execution, MCP tool use/results), `result` (success + error subtypes), `user` replay, `stream_event`.
- `CodexProtocol`: JSON-RPC 2.0 (no jsonrpc header). Handles `turn/started`, `item/agentMessage/delta`, `item/started` and `item/completed` (reasoning, commandExecution, fileChange, mcpToolCall, webSearch), `turn/completed`. Thread-based sessions with `thread/start` and `thread/resume`.
- `KimiProtocol`: JSON-RPC 2.0 wire mode. Handles `TurnBegin`, `TurnEnd`, `StepBegin`, `StepInterrupted`, `CompactionBegin/End`, `StatusUpdate`, `ContentPart` (text, think, tool_call, media), `ToolCall`, `ToolCallPart`, `ToolResult`, `SubagentEvent`. Requests: auto-approves `ApprovalRequest`, rejects `ToolCallRequest`. Session ID managed via CLI `--session` flag (not in wire protocol).

**Chat layer** (`src/chat/`): `ChatRoom` runs persistent event loops as an async generator yielding typed `ChatEvent` dataclasses (`RoundStarted`, `AgentStreamChunk`, `AgentCompleted`, `RoundEnded`, `RoundPaused`, `AgentInterrupted`). `router.py` handles prompt formatting helpers, `[PASS]` detection, coordination pattern extraction, and `<Share>` tag protocol. Also: DM debouncing (500ms coalesce in `_dm_debounce_timers`), per-agent inbox queues (`_inboxes`) for targeted message delivery during rounds.

**Memory layer** (`src/memory/`): Cross-session learning system. `MemoryStore` persists to project-local `.multiagents/memory.db`. `MemoryManager` extracts insights via LLM (Haiku). `SessionRecorder` captures session data. `build_memory_context()` injects agent profiles into prompts.

**Cards layer** (`src/cards/`): Kanban workflow engine with role delegation parsing, `[DONE]` detection, and phase transitions. CLI utility at `scripts/multiagents-cards`.

**Server layer** (`src/server/`): FastAPI app with WebSocket at `/ws` and REST at `/api/sessions`. `SessionRunner` manages per-session chat tasks, WebSocket subscriber broadcast, and pre-warmed agent pools (agents spawned in advance with 300s TTL via `warmup_agents()`). `SessionStore` uses SQLite with WAL mode. `SettingsStore` manages runtime config in the same database.

### Frontend (`web/src/`)

React 19 + Tailwind CSS 4 SPA. `useWebSocket` hook manages the connection lifecycle with auto-reconnect (exponential backoff) and a reducer for state updates. The WebSocket protocol uses `event_id` for replay on reconnect.

### Key Protocols

**Coordination patterns** are parsed both in `src/chat/router.py` (backend) and `web/src/types.ts` (frontend) using matching regexes. Patterns: `@AgentName` (mention), `+1 AgentName` (agreement), `[HANDOFF:Agent]`, `[EXPLORE]`, `[DECISION]`, `[BLOCKED]`, `[DONE]`, `[TODO]`, `[QUESTION]`.

**Share tags**: Agents wrap coordinated content in `<Share>...</Share>`. Backend extracts shareable content via `extract_shareable()` for history; content outside tags stays private.

**Tool badges**: Streaming output wraps tool use in `<tool>Name detail</tool>` tags. Frontend renders these as inline UI badges.

**WebSocket message types**: server emits events such as `round_started`, `agent_stream`, `agent_completed`, `round_ended`, `paused`, `agent_interrupted`, `dm_sent`, and client sends controls such as `message`, `stop_agent`, `stop_round`, `resume`, `direct_message`, `cancel`, `ack`.

## Testing

pytest with `asyncio_mode = "auto"`. Tests use `FakeAgent` mocks (defined in test files) to simulate agent behavior without spawning real CLIs.

## Environment

- Backend default port: **8421**
- Frontend dev port: **5174** (Vite proxies `/ws` and `/api` to backend)
- Production: set `STATIC_DIR` env var to serve `web/dist/` from backend
- Required external CLIs: `claude`, `codex`, `kimi` (must be in `$PATH`)
- Session database: `~/.multiagents/multiagents.db` (SQLite, WAL mode — sessions + settings)
- Memory database: `<project>/.multiagents/memory.db` (SQLite — cross-session learning)
- Agent work dirs: `/tmp/multiagents-<agent>-<uuid>/`
- Kimi generates temp agent YAML + prompt files in `/tmp/multiagents-kimi-agent-*/`
- **Important**: Agents must use **absolute paths** (e.g., `/path/to/repo/...`) to access project files, as their CWD is isolated.
