# Quickstart Tutorial

This guide walks you through your first multi-agent session — from installation to a working collaborative discussion.

## Prerequisites

- **Python 3.12+**
- **Node.js 18+** with **pnpm**
- At least one agent CLI installed and in your `$PATH`:
  - `claude` — [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
  - `codex` — [OpenAI Codex CLI](https://github.com/openai/codex)
  - `kimi` — [Kimi Code CLI](https://github.com/anthropics/kimi)

You only need one agent to get started, but the platform shines with two or more.

## 1. Install

```bash
git clone https://github.com/leonardocbsr/multiagents.git
cd multiagents
./setup.sh
```

`setup.sh` creates a Python virtualenv, installs backend dependencies, and runs `pnpm install` for the frontend. It also checks which agent CLIs are available and warns about any that are missing.

## 2. Launch

```bash
./start.sh
```

This starts both the backend (port 8421) and the frontend dev server (port 5174) together. Open **http://localhost:5174** in your browser.

To customize which agents participate:

```bash
./start.sh --agents claude,codex    # Only Claude and Codex
./start.sh --port 9000              # Different backend port
```

## 3. Create a session

When the app loads, you'll see the **session picker** — a list of previous sessions (if any) and a "New Chat" button.

<!-- TODO: screenshot of session picker -->

Click **New Chat**. You'll be prompted to:

1. **Pick a working directory** — the folder agents will operate in. Each agent gets its own isolated temp directory, but uses absolute paths to read/write files in your project.
2. **Select agents** — check which agents to include. You can also add multiple instances of the same model with different personas (e.g., "Claude as Architect" and "Claude as Reviewer").

<!-- TODO: screenshot of agent roster selection -->

## 4. Send your first message

Type a prompt in the input bar at the bottom and hit Enter. For example:

> Review the structure of this project and suggest improvements to the error handling.

What happens next:

1. **Round starts** — all selected agents receive your message simultaneously.
2. **Streaming responses** — you'll see live output from each agent in real time.
3. **Round ends** — once every agent has finished responding, the round is complete.
4. **Next round** — agents can now respond to each other. This continues until all agents signal `[PASS]`, meaning they have nothing more to add.

<!-- TODO: screenshot of agents streaming responses -->

## 5. Understand the layout

The UI has a three-panel split layout:

```
+------------------+-------------------+------------------+
|  Agent Streams   |   Shared Chat     |   Kanban Board   |
|                  |                   |                  |
|  Raw output from |  Curated view of  |  Task cards that |
|  each agent,     |  content agents   |  agents create   |
|  including tool  |  wrapped in       |  and move through |
|  use and         |  <Share> tags     |  workflow stages  |
|  thinking blocks |                   |                  |
+------------------+-------------------+------------------+
|                    Prompt Input Bar                      |
+---------------------------------------------------------+
```

- **Agent Streams** (left) — the full raw output from each agent, color-coded. Includes tool use badges (file reads, writes, searches) and thinking blocks.
- **Shared Chat** (center) — a clean narrative view. Only content that agents explicitly wrap in `<Share>...</Share>` tags appears here. This is the "public" conversation.
- **Kanban Board** (right) — a task board where agents can create cards that flow through stages: Backlog → Planning → Reviewing → Implementing → Done.

You can toggle panels and resize them using the layout controls in the header.

<!-- TODO: screenshot of the three-panel layout -->

## 6. How rounds and passing work

Each round follows this cycle:

```
User sends message (or agents continue discussion)
        │
        ▼
  ┌─────────────┐
  │ All agents   │  ← agents run concurrently
  │ respond      │
  └─────┬───────┘
        │
        ▼
  Round ends
        │
        ▼
  Did all agents say [PASS]?
       / \
     Yes   No
      │     │
      ▼     ▼
   Done   Next round
```

- An agent signals **`[PASS]`** when it has nothing to add. This is the main mechanism for ending discussions — once every agent passes in the same round, the discussion ends.
- You can send a new message at any time to start a fresh round, even mid-discussion.
- Use **Pause** to temporarily halt a discussion and **Resume** to continue.
- Use **Cancel** to stop the current discussion entirely.

## 7. Agent coordination patterns

Agents use lightweight text patterns to coordinate with each other:

| Pattern | Meaning | Example |
|---------|---------|---------|
| `@AgentName` | Direct mention — gets that agent's attention | `@Codex can you check the tests?` |
| `+1 AgentName` | Agreement — endorses another agent's suggestion | `+1 Claude, that approach looks right` |
| `[HANDOFF:Agent]` | Delegation — hands a specific task to another agent | `[HANDOFF:Kimi] Please implement the parser` |
| `[PASS]` | Nothing to add — signals the agent is done for this round | `[PASS]` |
| `[EXPLORE]` | Status — currently investigating | Working through the codebase... |
| `[DECISION]` | Status — proposing or making a decision | Let's use approach B |
| `[BLOCKED]` | Status — stuck on something | Need clarification on the API spec |
| `[DONE]` | Status — finished the assigned work | Implementation complete |
| `[TODO]` | Status — noting something for later | `[TODO] Add error handling` |
| `[QUESTION]` | Status — asking the group | `[QUESTION] Should we support pagination?` |

These patterns are parsed by both the backend and frontend to enable features like highlighting mentions and tracking task status.

## 8. Adjust settings

Click the **gear icon** in the header to open the settings modal. You can adjust:

- **Models** — which underlying model each agent uses
- **System prompts** — custom instructions for each agent
- **Timeouts** — how long to wait for agent responses (default: 30 minutes)

Settings changes apply to the current session immediately.

<!-- TODO: screenshot of settings modal -->

## 9. Session persistence

Sessions are automatically saved to a local SQLite database at `~/.multiagents/multiagents.db`. When you return to the app:

- Previous sessions appear in the session picker with their creation time
- Rejoining a session replays the full conversation history via WebSocket event replay
- Agent CLI session IDs are preserved, so agents can resume with their prior context

## 10. Tips

- **Start with two agents.** A two-agent setup (e.g., Claude + Codex) is easier to follow than three and still demonstrates the collaboration dynamics.
- **Be specific in your prompts.** Multi-agent discussions work best with clear, scoped tasks rather than vague requests.
- **Use direct messages.** You can message a specific agent mid-discussion if you want targeted input without triggering a full round.
- **Watch the shared chat.** The center panel filters out noise and shows only the coordinated output — it's the best place to follow the discussion's conclusions.
- **Check the kanban board.** For implementation tasks, agents will often create cards to track their work. The board gives you a high-level view of progress.

## Next steps

- Read the [Agent Collaboration Guidelines](../GUIDELINES.md) for the full coordination protocol
- See the [README](../README.md) for architecture details and the full command reference
- Check [CONTRIBUTING.md](../CONTRIBUTING.md) if you want to contribute to the project
