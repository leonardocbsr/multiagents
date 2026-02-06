# Multiagents

Multi-agent AI orchestration platform. Run collaborative sessions with Claude, Codex, and Kimi — featuring event-driven messaging, round consensus with `[PASS]`, kanban task workflows, agent personas, cross-session memory, and real-time streaming.

## Features

- **Event-driven collaboration with rounds** — agents react to incoming events in real time; rounds close on settlement and advance after all agents return `[PASS]`
- **Kanban task workflows** — cards move through Backlog, Planning, Reviewing, Implementing, Done
- **Agent personas** — dynamic roles let you run multiple instances of the same model with different specializations
- **Direct messages** — message individual agents mid-discussion
- **Cross-session memory** — agent learning profiles persist and grow across sessions
- **Split layout** — agent raw streams | shared narrative | kanban board
- **Real-time streaming** — live output via WebSocket with tool badges and thinking blocks
- **Configurable settings** — models, system prompts, and timeouts adjustable from the UI
- **Session persistence** — SQLite-backed history with replay on reconnect
- **Pause/resume/cancel** — full control over ongoing discussions

## Quick Start

```bash
./setup.sh          # Install Python + Node dependencies
./start.sh          # Launch backend + frontend (http://localhost:5174)
```

Or manually:

```bash
pip install -e .                # Backend dependencies
cd web && pnpm install          # Frontend dependencies
./start.sh                      # Run both
```

See the [Quickstart Tutorial](./docs/QUICKSTART.md) for a guided walkthrough.

## Runtime Controls

- `Stop agent`: interrupt one agent's active turn.
- `Stop round`: interrupt all active turns in the current round.
- `Resume`: continue after a paused round.
- `Direct message`: send a targeted instruction to one agent.
  - If active, the agent is restarted with the DM.
  - If idle, the DM triggers a focused single-agent turn.

## Technology Stack

### Backend
- **Language**: Python 3.12+
- **Framework**: FastAPI with native WebSocket support
- **Server**: Uvicorn
- **Database**: SQLite with WAL mode (`~/.multiagents/multiagents.db`)
- **Build**: Hatchling

### Frontend
- **Language**: TypeScript ~5.9
- **Framework**: React 19
- **Build Tool**: Vite 7
- **Styling**: Tailwind CSS 4 with Typography plugin
- **Package Manager**: pnpm

## Project Structure

```
.
├── pyproject.toml              # Python project config & dependencies
├── setup.sh                    # One-command install script
├── start.sh                    # Full-stack dev launcher
├── scripts/
│   └── multiagents-cards       # Cards CLI utility
├── src/                        # Backend source
│   ├── main.py                 # CLI entry point & server bootstrap
│   ├── agents/                 # AI agent integrations
│   │   ├── base.py             # Abstract base agent class
│   │   ├── claude.py           # Claude Code CLI integration
│   │   ├── codex.py            # OpenAI Codex CLI integration
│   │   ├── kimi.py             # Kimi Code CLI integration
│   │   └── prompts.py          # System prompts & persona templates
│   ├── cards/                  # Kanban task engine
│   │   ├── engine.py           # Card lifecycle & state machine
│   │   └── models.py           # Card data models
│   ├── chat/                   # Chat orchestration
│   │   ├── room.py             # Event-driven messaging, round settlement, stop/DM/restart
│   │   ├── events.py           # Typed event dataclasses
│   │   └── router.py           # Prompt formatting & pass detection
│   ├── memory/                 # Cross-session memory
│   │   ├── cli.py              # Memory CLI & project init
│   │   ├── discovery.py        # Agent capability discovery
│   │   ├── manager.py          # Memory lifecycle management
│   │   ├── recorder.py         # Session recording & persistence
│   │   └── store.py            # Memory storage backend
│   └── server/                 # Web server
│       ├── app.py              # FastAPI app & WebSocket handler
│       ├── runner.py           # Session runner with agent warmup
│       ├── sessions.py         # SQLite session store
│       ├── settings.py         # Runtime settings & configuration
│       └── protocol.py         # Event serialization
├── tests/                      # Test suite (pytest)
└── web/                        # Frontend application
    ├── package.json            # Node dependencies
    ├── pnpm-workspace.yaml     # pnpm build config
    ├── src/
    │   ├── App.tsx             # Main app component
    │   ├── types.ts            # TypeScript type definitions
    │   ├── hooks/              # React hooks
    │   │   └── useWebSocket.ts # WebSocket with auto-reconnect
    │   └── components/         # UI components
    └── dist/                   # Built frontend assets (served by FastAPI)
```

## Commands

### Backend

```bash
pip install -e .                                  # Install dependencies
python -m src.main                                # Run server (port 8421)
multiagents --agents claude,codex --port 8080     # Custom options
pytest                                            # Run all tests
pytest tests/test_room.py -k test_name            # Run single test
```

### Frontend

```bash
cd web && pnpm install       # Install dependencies
cd web && pnpm dev           # Dev server (port 5174, proxies to backend)
cd web && pnpm build         # Production build to web/dist/
```

### Full Stack

```bash
./start.sh                                    # Backend + frontend with prefixed logs
./start.sh --port 8080 --agents claude,codex  # Custom options
```

### CLI Arguments

```
-a, --agents        Comma-separated agent list (default: claude,codex,kimi)
-t, --timeout       Idle timeout per agent in seconds (default: 1800)
--parse-timeout     Timeout for parsing agent output (default: 1200)
--send-timeout      WebSocket send timeout (default: 120)
--hard-timeout      Hard timeout per agent, 0 = disabled (default: 0)
--host              Bind host (default: 127.0.0.1)
--port              Bind port (default: 8421)
```

By default, the server binds to loopback (`127.0.0.1`). Use `--host 0.0.0.0` only when you intentionally want LAN access.

## Code Organization

### Agent Architecture (`src/agents/`)

All agents inherit from `BaseAgent` and implement:
- `_build_args(prompt)` — CLI arguments for the agent
- `_parse_output(stdout)` — parse final output into (text, raw_data)
- `_parse_stream_line(line)` — parse streaming JSON lines for live updates
- `_extract_session_id(stdout)` — extract CLI session ID for resume capability

Each agent runs in its own temporary directory (`/tmp/multiagents-<agent>-<uuid>/`), supports session resumption via CLI-specific session IDs, and streams JSON output with tool use badges and thinking blocks.

### Chat Flow (`src/chat/`)

- **ChatRoom**: Event-driven agent inbox loops with real-time share relays. Rounds end when agents settle and all inboxes are empty.
- **Round advancement**: After a settled round where all agents returned `[PASS]`, the next round opens on the next incoming activity (user message, DM restart, or seeded add-agent message).
- **Prompt Formatting**: Agents receive event-specific prompts with session context and strict `<Share>...</Share>` visibility rules.
- **Events**: Type-safe event system (`RoundStarted`, `AgentStreamChunk`, `AgentCompleted`, `RoundEnded`, `RoundPaused`, `AgentInterrupted`).

### Cards Engine (`src/cards/`)

Kanban-style task management that agents can create and update during discussions. Cards flow through defined stages (Backlog → Planning → Reviewing → Implementing → Done) with structured metadata.

### Memory System (`src/memory/`)

Cross-session persistence layer. Records agent interactions, discovers capabilities, and builds learning profiles that carry forward across sessions.

### Server Architecture (`src/server/`)

- **SessionStore**: Thread-safe SQLite with session/message/agent_state tables
- **SessionRunner**: WebSocket subscriptions, agent warmup pools, chat execution
- **Settings**: Runtime configuration for models, prompts, and timeouts
- **WebSocket Protocol**: JSON messages for session management, chat control, and real-time updates

## Testing

```bash
pytest               # Run all tests
pytest -v            # Verbose output
pytest tests/test_room.py -k test_name   # Single test
```

Tests use `FakeAgent` mocks to simulate agent behavior without spawning real CLIs. Coverage includes event-driven room behavior, round settlement/advancement, prompt formatting, pass detection, and user message injection.

## External Dependencies

Requires these CLI tools in `$PATH`:

- `claude` — Anthropic's Claude Code CLI
- `codex` — OpenAI's Codex CLI
- `kimi` — Moonshot AI's Kimi Code CLI

## Agent Guidelines

For agent collaboration protocols, see [GUIDELINES.md](./GUIDELINES.md).

## Project Policies

- [Contributing Guide](./CONTRIBUTING.md)
- [Security Policy](./SECURITY.md)
- [Code of Conduct](./CODE_OF_CONDUCT.md)

## License

[MIT](./LICENSE)
