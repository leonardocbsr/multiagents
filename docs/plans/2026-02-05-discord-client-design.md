# Discord Client Design

## Overview

A standalone Discord bot that mirrors the web chat experience in Discord threads. Users @mention the bot to start multiagent sessions, and each thread becomes a live chat with AI agents — just like the middle chat panel in the web UI.

## Architecture

The Discord client is a **separate service** at `clients/discord/`, parallel to the `web/` frontend. It connects to the multiagents backend via WebSocket using the same protocol the web frontend speaks.

```
Discord @mention → bot.py → bridge.py → WebSocket → multiagents server
                                                          ↓
Discord thread  ← bot.py ← formatter.py ← bridge.py ← agent events
```

The bot doesn't import or depend on any backend code. It speaks the existing WebSocket protocol, so new server features (agents, event types) automatically work with Discord.

## File Structure

```
clients/discord/
├── pyproject.toml          # discord.py + websockets deps
├── .env.example            # DISCORD_TOKEN, SERVER_URL, ALLOWLIST
├── src/
│   ├── __init__.py
│   ├── __main__.py         # Entry point: python -m src
│   ├── bot.py              # Discord bot: event handlers, thread management
│   ├── bridge.py           # WebSocket client to multiagents server
│   ├── allowlist.py        # User ID allowlist check
│   ├── formatter.py        # Convert server events → Discord messages
│   └── config.py           # Env-based configuration
```

**Dependencies:** `discord.py`, `websockets`, `python-dotenv`.

## Bot Behavior

### Starting a Session

1. User @mentions the bot in any text channel: `@MultiAgents discuss API design for auth`
2. Bot checks user ID against the allowlist. If not allowed, silently ignores.
3. Bot creates a Discord thread from that message (named after the first ~50 chars of the prompt).
4. Bot opens a WebSocket to the multiagents server, sends `create_session` then `message` with the prompt.
5. Bot posts a brief "Session started with claude, codex, kimi" in the thread.

### During a Session

- Any message in the thread from an allowlisted user is forwarded as a `message` to the WebSocket.
- Agent responses arrive as `agent_completed` events. The bot posts the Share content to the thread, prefixed with the agent name in bold (e.g., **Claude:** ...).
- `round_ended` events trigger a separator (e.g., `───── Round 2 ─────`).
- Tool badges `<tool>Name detail</tool>` render as `🔧 Name` inline in the agent message.
- If all agents `[PASS]`, bot posts "All agents passed. Send a message to continue."
- Agent interruptions/errors: "⚠ Claude was interrupted: reason"

### Ending a Session

- User types `!stop` in the thread → bot sends `cancel` via WebSocket and closes the connection.
- Thread is archived after configurable inactivity timeout (default 30 min).

### No Streaming

Agent responses are posted as complete messages once `agent_completed` fires. This avoids Discord's message edit rate limits (5/5s) and keeps the thread clean and readable.

## Key Classes

### `MultiAgentsBot(discord.Client)`

Handles `on_message` events. Checks allowlist, detects @mentions vs thread replies, manages a dict of `thread_id → Bridge` instances.

### `Bridge`

Async WebSocket client. Connects to the multiagents server, sends/receives JSON. Exposes `send_message(text)`, `create_session(agents)`, and an async iterator for incoming events. Each thread gets its own Bridge instance with its own WebSocket connection.

### `Formatter`

Stateless. Takes a server event dict and returns a Discord-formatted string — markdown, bold agent names, tool badge emojis, round separators. Handles Discord's 2000-char limit by splitting long responses at paragraph boundaries.

## Allowlist

- Configured via `DISCORD_ALLOWLIST` env var: comma-separated Discord user IDs.
- Messages from non-allowlisted users are silently ignored (no error reply, no reaction).

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | Yes | — | Bot token from Discord Developer Portal |
| `SERVER_URL` | No | `ws://localhost:8421/ws` | Multiagents server WebSocket URL |
| `DISCORD_ALLOWLIST` | Yes | — | Comma-separated Discord user IDs |
| `DEFAULT_AGENTS` | No | `claude,codex,kimi` | Agents to use when creating sessions |
| `INACTIVITY_TIMEOUT` | No | `1800` | Seconds before archiving idle threads |

## Error Handling

- **Server unreachable:** Bot posts "Could not connect to multiagents server" in the thread and retries with exponential backoff (max 3 attempts). If all fail, archives the thread.
- **WebSocket disconnect mid-session:** Bridge reconnects and sends `join_session` to resume. Events have `event_id` so the server replays missed events (existing protocol feature).
- **Discord rate limits:** `discord.py` handles these automatically with built-in retry logic.
- **Long agent responses:** Discord has a 2000-char limit per message. Formatter splits at paragraph boundaries into multiple messages.
- **Bot restart:** On startup, bot doesn't try to resume old threads. Users @mention again to start fresh.

## Running

```bash
cd clients/discord
pip install -e .
python -m src   # or: multiagents-discord
```
