# Discord Bot Setup Guide

Step-by-step guide to set up the multiagents Discord bot.

## 1. Create the Discord Application

1. Go to https://discord.com/developers/applications
2. Click **New Application**, name it (e.g., "MultiAgents")
3. Go to **Bot** in the left sidebar
4. Click **Reset Token** and copy the token — you'll need it later
5. Under **Privileged Gateway Intents**, enable **Message Content Intent** (required for reading message text)

## 2. Invite the Bot to Your Server

1. Go to **OAuth2 > URL Generator** in the left sidebar
2. Under **Scopes**, check `bot`
3. Under **Bot Permissions**, check:
   - Send Messages
   - Create Public Threads
   - Send Messages in Threads
   - Read Message History
   - Manage Threads
4. Copy the generated URL and open it in your browser
5. Select your server and authorize

Alternatively, use this URL template (replace `YOUR_CLIENT_ID` with the Application ID from the General Information page):

```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=397284550656&scope=bot
```

## 3. Get Your Discord User ID

You need your Discord user ID for the allowlist:

1. Open Discord Settings > Advanced > enable **Developer Mode**
2. Right-click your username anywhere in Discord
3. Click **Copy User ID**

This is a number like `123456789012345678`.

## 4. Install and Configure

```bash
cd clients/discord
pip install -e .
cp .env.example .env
```

Edit `.env` with your values:

```env
# Required: paste your bot token from step 1
DISCORD_TOKEN=your-bot-token-here

# Required: comma-separated Discord user IDs that can use the bot
# Get your ID from step 3. Add others as needed.
DISCORD_ALLOWLIST=123456789012345678

# Optional: multiagents backend URL (default shown)
SERVER_URL=ws://localhost:8421/ws

# Optional: which agents to use (default shown)
DEFAULT_AGENTS=claude,codex,kimi

# Optional: seconds before idle threads auto-archive (default: 1800 = 30 min)
INACTIVITY_TIMEOUT=1800
```

## 5. Start the Services

You need both the multiagents backend AND the Discord bot running.

**Terminal 1 — Backend:**
```bash
cd /path/to/multiagents
./start.sh
# Or just the backend: python -m src.main
```

**Terminal 2 — Discord bot:**
```bash
cd /path/to/multiagents/clients/discord
python -m src
```

You should see: `Bot ready as MultiAgents#1234`

## 6. Use It

### Start a session

In any text channel where the bot has access, @mention it with your prompt:

```
@MultiAgents discuss the best approach for implementing user authentication
```

The bot will:
1. Create a thread from your message
2. Connect to the multiagents backend
3. Post "Session started with claude, codex, kimi."
4. Forward your prompt to the agents
5. Post agent responses as they complete

### Chat in the thread

Just type normally in the thread. Your messages are forwarded to the agents as if you typed them in the web UI.

### Stop a session

Type `!stop` in the thread. The bot will cancel the session and archive the thread.

### What you'll see

- **Agent responses** appear as `**Claude:** response text` — only the shared content (inside `<Share>` tags) is shown
- **Tool badges** appear as `` `🔧 Read` `` `` `🔧 Run` `` etc. when agents use tools
- **Round separators** like `───── Round 2 ─────` appear between discussion rounds
- **All passed** notification when agents have nothing to add
- **Private responses** show as "*(private response withheld)*" when an agent doesn't share content

## Troubleshooting

**Bot doesn't respond to mentions:**
- Check the bot is online (green dot in the member list)
- Verify your user ID is in `DISCORD_ALLOWLIST`
- Make sure Message Content Intent is enabled in the Developer Portal
- Check the bot has permission to read messages and create threads in that channel

**"Could not connect to multiagents server":**
- Make sure the backend is running (`./start.sh` or `python -m src.main`)
- Verify `SERVER_URL` in `.env` matches your backend address

**Bot creates thread but no agent responses:**
- Check the backend terminal for errors
- Make sure the agent CLIs (`claude`, `codex`, `kimi`) are installed and in `$PATH`
- Try with fewer agents: `DEFAULT_AGENTS=claude`

**Thread auto-archives too quickly/slowly:**
- Adjust `INACTIVITY_TIMEOUT` in `.env` (value in seconds)
