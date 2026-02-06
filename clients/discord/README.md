# multiagents-discord

Discord client for the [multiagents](../../README.md) platform. Mirrors the web chat experience in Discord threads.

## Setup

1. Create a Discord bot at [discord.com/developers](https://discord.com/developers/applications)
   - Enable **Message Content Intent** under Bot settings
   - Copy the bot token

2. Invite the bot to your server with this URL (replace `CLIENT_ID`):
   ```
   https://discord.com/oauth2/authorize?client_id=CLIENT_ID&permissions=397284550656&scope=bot
   ```
   Permissions: Send Messages, Create Public Threads, Send Messages in Threads, Read Message History, Manage Threads

3. Configure and run:
   ```bash
   cd clients/discord
   cp .env.example .env
   # Edit .env with your token and user IDs
   pip install -e .
   python -m src
   ```

## Usage

- **Start a session:** @mention the bot in any channel with your prompt
- **Chat in thread:** Reply in the thread -- messages are forwarded to agents
- **Stop:** Type `!stop` in the thread

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | Yes | -- | Bot token |
| `SERVER_URL` | No | `ws://localhost:8421/ws` | Multiagents server WebSocket URL |
| `DISCORD_ALLOWLIST` | Yes | -- | Comma-separated Discord user IDs |
| `DEFAULT_AGENTS` | No | `claude,codex,kimi` | Agents for new sessions |
| `INACTIVITY_TIMEOUT` | No | `1800` | Seconds before auto-archiving idle threads |
