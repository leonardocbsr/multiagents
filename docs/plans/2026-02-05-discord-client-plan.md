# Discord Client Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a standalone Discord bot client that mirrors the web chat experience in Discord threads, connecting to the multiagents backend via WebSocket.

**Architecture:** Separate service at `clients/discord/` that speaks the existing WebSocket protocol. Discord @mentions create threads, each backed by a WebSocket session. Agent responses (Share content only) are posted as complete messages. User allowlist controls access.

**Tech Stack:** Python 3.12+, discord.py, websockets, python-dotenv, pytest + pytest-asyncio for tests.

---

### Task 1: Project Scaffold

**Files:**
- Create: `clients/discord/pyproject.toml`
- Create: `clients/discord/.env.example`
- Create: `clients/discord/src/__init__.py`
- Create: `clients/discord/tests/__init__.py`

**Step 1: Create directory structure**

```bash
mkdir -p clients/discord/src clients/discord/tests
```

**Step 2: Write pyproject.toml**

Create `clients/discord/pyproject.toml`:

```toml
[project]
name = "multiagents-discord"
version = "0.1.0"
description = "Discord client for multiagents platform"
requires-python = ">=3.12"
dependencies = [
    "discord.py>=2.4",
    "websockets>=14.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24"]

[project.scripts]
multiagents-discord = "src.__main__:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Step 3: Write .env.example**

Create `clients/discord/.env.example`:

```env
DISCORD_TOKEN=your-bot-token-here
SERVER_URL=ws://localhost:8421/ws
DISCORD_ALLOWLIST=123456789012345678,987654321098765432
DEFAULT_AGENTS=claude,codex,kimi
INACTIVITY_TIMEOUT=1800
```

**Step 4: Write empty init files**

Create `clients/discord/src/__init__.py` and `clients/discord/tests/__init__.py` as empty files.

**Step 5: Commit**

```bash
git add clients/discord/pyproject.toml clients/discord/.env.example clients/discord/src/__init__.py clients/discord/tests/__init__.py
git commit -m "feat(discord): scaffold project structure"
```

---

### Task 2: Config Module

**Files:**
- Create: `clients/discord/src/config.py`
- Create: `clients/discord/tests/test_config.py`

**Step 1: Write the failing test**

Create `clients/discord/tests/test_config.py`:

```python
from __future__ import annotations

import os
import pytest


def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("DISCORD_ALLOWLIST", "111,222,333")
    monkeypatch.setenv("SERVER_URL", "ws://example.com/ws")
    monkeypatch.setenv("DEFAULT_AGENTS", "claude,codex")
    monkeypatch.setenv("INACTIVITY_TIMEOUT", "600")

    from src.config import Config

    cfg = Config.from_env()
    assert cfg.discord_token == "test-token"
    assert cfg.allowlist == {111, 222, 333}
    assert cfg.server_url == "ws://example.com/ws"
    assert cfg.default_agents == ["claude", "codex"]
    assert cfg.inactivity_timeout == 600


def test_config_defaults(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "tok")
    monkeypatch.setenv("DISCORD_ALLOWLIST", "111")
    # Clear optional vars
    monkeypatch.delenv("SERVER_URL", raising=False)
    monkeypatch.delenv("DEFAULT_AGENTS", raising=False)
    monkeypatch.delenv("INACTIVITY_TIMEOUT", raising=False)

    from src.config import Config

    cfg = Config.from_env()
    assert cfg.server_url == "ws://localhost:8421/ws"
    assert cfg.default_agents == ["claude", "codex", "kimi"]
    assert cfg.inactivity_timeout == 1800


def test_config_missing_token_raises(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("DISCORD_ALLOWLIST", "111")

    from src.config import Config

    with pytest.raises(ValueError, match="DISCORD_TOKEN"):
        Config.from_env()


def test_config_missing_allowlist_raises(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "tok")
    monkeypatch.delenv("DISCORD_ALLOWLIST", raising=False)

    from src.config import Config

    with pytest.raises(ValueError, match="DISCORD_ALLOWLIST"):
        Config.from_env()
```

**Step 2: Run test to verify it fails**

```bash
cd clients/discord && python -m pytest tests/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.config'`

**Step 3: Write the implementation**

Create `clients/discord/src/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    discord_token: str
    allowlist: set[int]
    server_url: str
    default_agents: list[str]
    inactivity_timeout: int

    @classmethod
    def from_env(cls) -> Config:
        token = os.environ.get("DISCORD_TOKEN", "").strip()
        if not token:
            raise ValueError("DISCORD_TOKEN environment variable is required")

        raw_allowlist = os.environ.get("DISCORD_ALLOWLIST", "").strip()
        if not raw_allowlist:
            raise ValueError("DISCORD_ALLOWLIST environment variable is required")

        allowlist = {int(uid.strip()) for uid in raw_allowlist.split(",") if uid.strip()}

        server_url = os.environ.get("SERVER_URL", "ws://localhost:8421/ws").strip()
        agents_str = os.environ.get("DEFAULT_AGENTS", "claude,codex,kimi").strip()
        default_agents = [a.strip() for a in agents_str.split(",") if a.strip()]
        inactivity_timeout = int(os.environ.get("INACTIVITY_TIMEOUT", "1800"))

        return cls(
            discord_token=token,
            allowlist=allowlist,
            server_url=server_url,
            default_agents=default_agents,
            inactivity_timeout=inactivity_timeout,
        )
```

**Step 4: Run test to verify it passes**

```bash
cd clients/discord && python -m pytest tests/test_config.py -v
```

Expected: 4 PASSED

**Step 5: Commit**

```bash
git add clients/discord/src/config.py clients/discord/tests/test_config.py
git commit -m "feat(discord): add config module with env-based configuration"
```

---

### Task 3: Allowlist Module

**Files:**
- Create: `clients/discord/src/allowlist.py`
- Create: `clients/discord/tests/test_allowlist.py`

**Step 1: Write the failing test**

Create `clients/discord/tests/test_allowlist.py`:

```python
from __future__ import annotations

from src.allowlist import is_allowed


def test_allowed_user():
    allowlist = {111, 222, 333}
    assert is_allowed(222, allowlist) is True


def test_disallowed_user():
    allowlist = {111, 222, 333}
    assert is_allowed(999, allowlist) is False


def test_empty_allowlist():
    assert is_allowed(111, set()) is False
```

**Step 2: Run test to verify it fails**

```bash
cd clients/discord && python -m pytest tests/test_allowlist.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `clients/discord/src/allowlist.py`:

```python
from __future__ import annotations


def is_allowed(user_id: int, allowlist: set[int]) -> bool:
    return user_id in allowlist
```

**Step 4: Run test to verify it passes**

```bash
cd clients/discord && python -m pytest tests/test_allowlist.py -v
```

Expected: 3 PASSED

**Step 5: Commit**

```bash
git add clients/discord/src/allowlist.py clients/discord/tests/test_allowlist.py
git commit -m "feat(discord): add user allowlist check"
```

---

### Task 4: Formatter Module

**Files:**
- Create: `clients/discord/src/formatter.py`
- Create: `clients/discord/tests/test_formatter.py`

**Step 1: Write the failing test**

Create `clients/discord/tests/test_formatter.py`:

```python
from __future__ import annotations

from src.formatter import format_event


def test_agent_completed_with_share():
    event = {
        "type": "agent_completed",
        "agent": "claude",
        "text": "<thinking>internal reasoning</thinking><Share>Here is my analysis of the problem.</Share>",
        "passed": False,
        "success": True,
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert messages[0].startswith("**Claude:**")
    assert "Here is my analysis of the problem." in messages[0]
    assert "thinking" not in messages[0].lower()
    assert "<Share>" not in messages[0]


def test_agent_completed_no_share_private():
    event = {
        "type": "agent_completed",
        "agent": "codex",
        "text": "some internal reasoning without share tags",
        "passed": False,
        "success": True,
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "private" in messages[0].lower()


def test_agent_completed_pass():
    event = {
        "type": "agent_completed",
        "agent": "kimi",
        "text": "[PASS]",
        "passed": True,
        "success": True,
    }
    messages = format_event(event)
    assert messages == []  # Individual passes are silent


def test_agent_completed_with_tool_badges():
    event = {
        "type": "agent_completed",
        "agent": "claude",
        "text": "<tool>Read src/main.py</tool>\n<Share>I read the file and found the issue.</Share>",
        "passed": False,
        "success": True,
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "Read" in messages[0] or "🔧" in messages[0]
    assert "I read the file and found the issue." in messages[0]


def test_agent_completed_failure():
    event = {
        "type": "agent_completed",
        "agent": "codex",
        "text": "",
        "passed": False,
        "success": False,
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "failed" in messages[0].lower() or "error" in messages[0].lower()


def test_round_started():
    event = {
        "type": "round_started",
        "round": 2,
        "agents": ["claude", "codex"],
    }
    messages = format_event(event)
    # Round 1 is silent (implicit start), round 2+ shows separator
    assert len(messages) == 1
    assert "Round 2" in messages[0]


def test_round_started_first_round_silent():
    event = {
        "type": "round_started",
        "round": 1,
        "agents": ["claude", "codex"],
    }
    messages = format_event(event)
    assert messages == []


def test_round_ended_all_passed():
    event = {
        "type": "round_ended",
        "round": 3,
        "all_passed": True,
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "passed" in messages[0].lower()


def test_round_ended_normal():
    event = {
        "type": "round_ended",
        "round": 3,
        "all_passed": False,
    }
    messages = format_event(event)
    assert messages == []  # Normal round end is silent


def test_agent_interrupted():
    event = {
        "type": "agent_interrupted",
        "agent": "claude",
        "round": 2,
        "partial_text": "I was working on...",
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "Claude" in messages[0]
    assert "interrupted" in messages[0].lower()


def test_discussion_ended():
    event = {
        "type": "discussion_ended",
        "reason": "all_passed",
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "ended" in messages[0].lower() or "complete" in messages[0].lower()


def test_long_message_split():
    # Discord 2000-char limit
    long_text = "A" * 3000
    event = {
        "type": "agent_completed",
        "agent": "claude",
        "text": f"<Share>{long_text}</Share>",
        "passed": False,
        "success": True,
    }
    messages = format_event(event)
    assert len(messages) >= 2
    for msg in messages:
        assert len(msg) <= 2000


def test_unknown_event_ignored():
    event = {"type": "agent_stream", "agent": "claude", "chunk": "partial"}
    messages = format_event(event)
    assert messages == []


def test_multiple_share_blocks():
    event = {
        "type": "agent_completed",
        "agent": "claude",
        "text": "<Share>First point.</Share>\n<thinking>hmm</thinking>\n<Share>Second point.</Share>",
        "passed": False,
        "success": True,
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "First point." in messages[0]
    assert "Second point." in messages[0]
```

**Step 2: Run test to verify it fails**

```bash
cd clients/discord && python -m pytest tests/test_formatter.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `clients/discord/src/formatter.py`:

```python
from __future__ import annotations

import re

_DISCORD_MAX_LEN = 2000

_THINKING_RE = re.compile(
    r"<(?:thinking|antThinking)>[\s\S]*?</(?:thinking|antThinking)>",
    re.IGNORECASE,
)
_SHARE_RE = re.compile(r"<Share>(.*?)</Share>", re.DOTALL | re.IGNORECASE)
_TOOL_RE = re.compile(r"<tool>(.*?)</tool>", re.DOTALL | re.IGNORECASE)


def _extract_share(text: str) -> str | None:
    """Extract Share content, stripping thinking blocks first."""
    if text.strip() == "[PASS]":
        return None
    cleaned = _THINKING_RE.sub("", text)
    matches = _SHARE_RE.findall(cleaned)
    if not matches:
        return None
    content = "\n\n".join(m.strip() for m in matches if m.strip())
    return content if content else None


def _extract_tools(text: str) -> list[str]:
    """Extract tool badge labels from text."""
    matches = _TOOL_RE.findall(text)
    tools = []
    for m in matches:
        label = m.strip().split()[0] if m.strip() else ""
        if label:
            tools.append(label)
    return tools


def _split_message(text: str, max_len: int = _DISCORD_MAX_LEN) -> list[str]:
    """Split text into chunks that fit Discord's message limit."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at a paragraph boundary
        cut = text.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = text.rfind("\n", 0, max_len)
        if cut == -1:
            cut = text.rfind(" ", 0, max_len)
        if cut == -1:
            cut = max_len
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()

    return chunks


def format_event(event: dict) -> list[str]:
    """Convert a server WebSocket event to Discord message(s).

    Returns a list of strings to post. Empty list means nothing to post.
    """
    event_type = event.get("type", "")

    if event_type == "agent_completed":
        return _format_agent_completed(event)
    elif event_type == "round_started":
        return _format_round_started(event)
    elif event_type == "round_ended":
        return _format_round_ended(event)
    elif event_type == "agent_interrupted":
        return _format_agent_interrupted(event)
    elif event_type == "discussion_ended":
        return _format_discussion_ended(event)
    else:
        return []


def _format_agent_completed(event: dict) -> list[str]:
    agent = event.get("agent", "unknown")
    text = event.get("text", "")
    passed = event.get("passed", False)
    success = event.get("success", True)
    agent_display = agent.capitalize()

    if passed:
        return []

    if not success:
        return [f"⚠ **{agent_display}** encountered an error."]

    tools = _extract_tools(text)
    share = _extract_share(text)

    if share is None:
        return [f"**{agent_display}:** *(private response withheld)*"]

    parts: list[str] = []
    if tools:
        badge_line = " ".join(f"`🔧 {t}`" for t in tools)
        parts.append(badge_line)
    parts.append(share)

    body = f"**{agent_display}:** " + "\n".join(parts)
    return _split_message(body)


def _format_round_started(event: dict) -> list[str]:
    round_num = event.get("round", 1)
    if round_num <= 1:
        return []
    return [f"───── Round {round_num} ─────"]


def _format_round_ended(event: dict) -> list[str]:
    if event.get("all_passed"):
        return ["All agents passed. Send a message to continue."]
    return []


def _format_agent_interrupted(event: dict) -> list[str]:
    agent = event.get("agent", "unknown").capitalize()
    return [f"⚠ **{agent}** was interrupted."]


def _format_discussion_ended(event: dict) -> list[str]:
    reason = event.get("reason", "unknown")
    if reason == "all_passed":
        return ["Discussion complete — all agents have nothing to add."]
    elif reason == "cancelled":
        return ["Discussion cancelled."]
    elif reason == "error":
        return ["Discussion ended due to an error."]
    return [f"Discussion ended ({reason})."]
```

**Step 4: Run test to verify it passes**

```bash
cd clients/discord && python -m pytest tests/test_formatter.py -v
```

Expected: all PASSED

**Step 5: Commit**

```bash
git add clients/discord/src/formatter.py clients/discord/tests/test_formatter.py
git commit -m "feat(discord): add event formatter with share extraction and message splitting"
```

---

### Task 5: Bridge Module

**Files:**
- Create: `clients/discord/src/bridge.py`
- Create: `clients/discord/tests/test_bridge.py`

**Step 1: Write the failing test**

Create `clients/discord/tests/test_bridge.py`:

```python
from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bridge import Bridge


class FakeWebSocket:
    """Fake websocket connection for testing."""

    def __init__(self, incoming: list[dict] | None = None):
        self._incoming = incoming or []
        self._sent: list[dict] = []
        self._idx = 0
        self._closed = False

    async def send(self, data: str):
        self._sent.append(json.loads(data))

    async def recv(self):
        if self._idx < len(self._incoming):
            msg = json.dumps(self._incoming[self._idx])
            self._idx += 1
            return msg
        # Simulate connection close after messages exhausted
        raise Exception("connection closed")

    async def close(self):
        self._closed = True

    @property
    def sent_messages(self) -> list[dict]:
        return self._sent


@pytest.fixture
def bridge():
    return Bridge("ws://localhost:8421/ws")


async def test_create_session(bridge):
    ws = FakeWebSocket(incoming=[
        {"type": "session_created", "session_id": "sess-1", "agents": []},
    ])
    with patch("src.bridge.websockets") as mock_ws:
        mock_ws.connect = AsyncMock(return_value=ws)
        session_id = await bridge.connect_and_create(["claude", "codex"])

    assert session_id == "sess-1"
    assert ws.sent_messages[0] == {
        "type": "create_session",
        "agents": ["claude", "codex"],
    }


async def test_send_message(bridge):
    ws = FakeWebSocket(incoming=[
        {"type": "session_created", "session_id": "sess-1", "agents": []},
    ])
    with patch("src.bridge.websockets") as mock_ws:
        mock_ws.connect = AsyncMock(return_value=ws)
        await bridge.connect_and_create(["claude"])

    await bridge.send_message("hello agents")
    assert ws.sent_messages[-1] == {"type": "message", "text": "hello agents"}


async def test_cancel(bridge):
    ws = FakeWebSocket(incoming=[
        {"type": "session_created", "session_id": "sess-1", "agents": []},
    ])
    with patch("src.bridge.websockets") as mock_ws:
        mock_ws.connect = AsyncMock(return_value=ws)
        await bridge.connect_and_create(["claude"])

    await bridge.cancel()
    assert ws.sent_messages[-1] == {"type": "cancel"}


async def test_event_callback(bridge):
    events_received: list[dict] = []
    ws = FakeWebSocket(incoming=[
        {"type": "session_created", "session_id": "sess-1", "agents": []},
        {"type": "round_started", "event_id": 1, "round": 1, "agents": ["claude"]},
        {"type": "agent_completed", "event_id": 2, "agent": "claude", "text": "hi", "passed": False, "success": True},
    ])
    with patch("src.bridge.websockets") as mock_ws:
        mock_ws.connect = AsyncMock(return_value=ws)
        await bridge.connect_and_create(["claude"])

    async def on_event(event: dict):
        events_received.append(event)

    # Run listener briefly
    task = asyncio.create_task(bridge.listen(on_event))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass

    assert len(events_received) >= 1
    assert events_received[0]["type"] == "round_started"


async def test_close(bridge):
    ws = FakeWebSocket(incoming=[
        {"type": "session_created", "session_id": "sess-1", "agents": []},
    ])
    with patch("src.bridge.websockets") as mock_ws:
        mock_ws.connect = AsyncMock(return_value=ws)
        await bridge.connect_and_create(["claude"])

    await bridge.close()
    assert ws._closed is True
```

**Step 2: Run test to verify it fails**

```bash
cd clients/discord && python -m pytest tests/test_bridge.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `clients/discord/src/bridge.py`:

```python
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Awaitable

import websockets

log = logging.getLogger("multiagents-discord")


class Bridge:
    """WebSocket client that bridges Discord to the multiagents server."""

    def __init__(self, server_url: str):
        self._server_url = server_url
        self._ws = None
        self._session_id: str | None = None
        self._last_event_id: int = 0

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def connect_and_create(self, agents: list[str]) -> str:
        """Connect to server and create a new session. Returns session_id."""
        self._ws = await websockets.connect(self._server_url)

        # Wait for connected message
        raw = await self._ws.recv()
        msg = json.loads(raw)
        if msg.get("type") != "connected":
            log.warning("Expected 'connected', got: %s", msg.get("type"))

        # Create session
        await self._ws.send(json.dumps({
            "type": "create_session",
            "agents": agents,
        }))

        # Wait for session_created
        raw = await self._ws.recv()
        msg = json.loads(raw)
        if msg.get("type") != "session_created":
            raise RuntimeError(f"Expected session_created, got: {msg.get('type')}")

        self._session_id = msg["session_id"]
        return self._session_id

    async def send_message(self, text: str) -> None:
        """Send a user message to the session."""
        if not self._ws:
            raise RuntimeError("Not connected")
        await self._ws.send(json.dumps({"type": "message", "text": text}))

    async def cancel(self) -> None:
        """Cancel the current discussion."""
        if not self._ws:
            return
        await self._ws.send(json.dumps({"type": "cancel"}))

    async def listen(self, on_event: Callable[[dict], Awaitable[None]]) -> None:
        """Listen for server events and call on_event for each.

        Runs until the connection closes or is cancelled.
        Skips session_created and connected events (already handled).
        Tracks last_event_id for potential reconnection.
        """
        if not self._ws:
            raise RuntimeError("Not connected")

        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                event_type = msg.get("type", "")

                # Track event IDs for replay
                if "event_id" in msg:
                    self._last_event_id = msg["event_id"]

                # Skip connection-level events
                if event_type in ("connected", "session_created", "session_joined"):
                    continue

                await on_event(msg)
        except websockets.ConnectionClosed:
            log.info("WebSocket connection closed")
        except Exception:
            log.exception("Error in bridge listener")

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._ws = None
```

**Step 4: Run test to verify it passes**

```bash
cd clients/discord && python -m pytest tests/test_bridge.py -v
```

Expected: all PASSED

**Step 5: Commit**

```bash
git add clients/discord/src/bridge.py clients/discord/tests/test_bridge.py
git commit -m "feat(discord): add WebSocket bridge client"
```

---

### Task 6: Discord Bot Module

**Files:**
- Create: `clients/discord/src/bot.py`
- Create: `clients/discord/tests/test_bot.py`

**Step 1: Write the failing test**

Create `clients/discord/tests/test_bot.py`:

```python
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot import MultiAgentsBot
from src.config import Config


@pytest.fixture
def config():
    return Config(
        discord_token="fake-token",
        allowlist={111, 222},
        server_url="ws://localhost:8421/ws",
        default_agents=["claude", "codex"],
        inactivity_timeout=1800,
    )


@pytest.fixture
def bot(config):
    return MultiAgentsBot(config)


def _make_message(
    content: str,
    author_id: int = 111,
    is_bot: bool = False,
    channel_type: str = "text",
    mentions_bot: bool = False,
    thread_id: int | None = None,
):
    """Create a mock Discord message."""
    msg = MagicMock()
    msg.content = content
    msg.author.id = author_id
    msg.author.bot = is_bot
    msg.author.display_name = "TestUser"
    msg.id = 12345

    if thread_id:
        msg.channel = MagicMock()
        msg.channel.id = thread_id
        msg.channel.type = MagicMock()
        msg.channel.type.name = "public_thread"
    else:
        msg.channel = MagicMock()
        msg.channel.id = 99999
        msg.channel.type = MagicMock()
        msg.channel.type.name = channel_type

    if mentions_bot:
        bot_user = MagicMock()
        bot_user.id = 99
        msg.mentions = [bot_user]
    else:
        msg.mentions = []

    msg.channel.create_thread = AsyncMock()
    msg.channel.send = AsyncMock()

    return msg


def test_should_ignore_bot_messages(bot):
    msg = _make_message("hello", is_bot=True)
    assert bot.should_handle(msg) is False


def test_should_ignore_non_allowlisted_user(bot):
    msg = _make_message("hello", author_id=999)
    assert bot.should_handle(msg) is False


def test_should_handle_allowlisted_user(bot):
    msg = _make_message("hello", author_id=111)
    assert bot.should_handle(msg) is True


def test_is_mention(bot):
    bot_user = MagicMock()
    bot_user.id = 99
    bot._user = bot_user  # Simulate logged-in bot user

    msg = _make_message("hello @bot", mentions_bot=True)
    assert bot.is_mention(msg) is True


def test_is_thread_message(bot):
    msg = _make_message("followup", thread_id=55555)
    assert bot.is_thread_message(msg) is True


def test_is_stop_command(bot):
    msg = _make_message("!stop")
    assert bot.is_stop_command(msg) is True

    msg = _make_message("hello")
    assert bot.is_stop_command(msg) is False


def test_thread_name_from_prompt(bot):
    assert bot.thread_name("Discuss the API design for authentication") == "Discuss the API design for authenticati…"
    assert bot.thread_name("Short") == "Short"
    assert len(bot.thread_name("A" * 200)) <= 50
```

**Step 2: Run test to verify it fails**

```bash
cd clients/discord && python -m pytest tests/test_bot.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `clients/discord/src/bot.py`:

```python
from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord

from .allowlist import is_allowed
from .bridge import Bridge
from .config import Config
from .formatter import format_event

log = logging.getLogger("multiagents-discord")


class MultiAgentsBot(discord.Client):
    """Discord bot that bridges to the multiagents platform."""

    def __init__(self, config: Config, **kwargs: Any):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents, **kwargs)

        self.config = config
        # thread_id → Bridge
        self._bridges: dict[int, Bridge] = {}
        # thread_id → asyncio.Task (listener)
        self._listeners: dict[int, asyncio.Task] = {}
        # thread_id → asyncio.Task (inactivity timer)
        self._timers: dict[int, asyncio.Task] = {}

    def should_handle(self, message: discord.Message) -> bool:
        """Check if this message should be processed."""
        if message.author.bot:
            return False
        if not is_allowed(message.author.id, self.config.allowlist):
            return False
        return True

    def is_mention(self, message: discord.Message) -> bool:
        """Check if the bot is @mentioned in this message."""
        if not self.user:
            return False
        return self.user in message.mentions

    def is_thread_message(self, message: discord.Message) -> bool:
        """Check if this message is inside a thread."""
        return hasattr(message.channel, "type") and "thread" in str(message.channel.type)

    def is_stop_command(self, message: discord.Message) -> bool:
        """Check if this is a !stop command."""
        return message.content.strip().lower() == "!stop"

    def thread_name(self, prompt: str) -> str:
        """Generate a thread name from the prompt (max 50 chars)."""
        if len(prompt) <= 50:
            return prompt
        return prompt[:49] + "…"

    async def on_ready(self):
        log.info("Bot ready as %s", self.user)

    async def on_message(self, message: discord.Message):
        if not self.should_handle(message):
            return

        # Stop command in a thread
        if self.is_thread_message(message) and self.is_stop_command(message):
            await self._stop_session(message.channel)
            return

        # Message in an active thread → forward to session
        if self.is_thread_message(message) and message.channel.id in self._bridges:
            bridge = self._bridges[message.channel.id]
            await bridge.send_message(message.content)
            self._reset_inactivity_timer(message.channel)
            return

        # @mention in a channel → create new thread + session
        if self.is_mention(message):
            # Strip the bot mention from the prompt
            prompt = message.content
            if self.user:
                prompt = prompt.replace(f"<@{self.user.id}>", "").strip()
                prompt = prompt.replace(f"<@!{self.user.id}>", "").strip()

            if not prompt:
                prompt = "Start a discussion"

            thread = await message.create_thread(name=self.thread_name(prompt))
            await self._start_session(thread, prompt)

    async def _start_session(self, thread: discord.Thread, prompt: str):
        """Create a new session and start listening for events."""
        bridge = Bridge(self.config.server_url)

        try:
            session_id = await bridge.connect_and_create(self.config.default_agents)
        except Exception:
            log.exception("Failed to connect to multiagents server")
            await thread.send("Could not connect to multiagents server.")
            return

        self._bridges[thread.id] = bridge

        agents_str = ", ".join(self.config.default_agents)
        await thread.send(f"Session started with {agents_str}.")

        # Send the initial prompt
        await bridge.send_message(prompt)

        # Start listening for events in background
        listener = asyncio.create_task(self._listen_loop(thread, bridge))
        self._listeners[thread.id] = listener

        # Start inactivity timer
        self._reset_inactivity_timer(thread)

    async def _listen_loop(self, thread: discord.Thread, bridge: Bridge):
        """Listen for server events and post them to the thread."""

        async def on_event(event: dict):
            messages = format_event(event)
            for msg in messages:
                await thread.send(msg)

        try:
            await bridge.listen(on_event)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Listener error for thread %s", thread.id)
        finally:
            self._cleanup_thread(thread.id)

    async def _stop_session(self, channel: discord.Thread | Any):
        """Stop the session for a thread."""
        thread_id = channel.id
        bridge = self._bridges.get(thread_id)
        if bridge:
            await bridge.cancel()
            await bridge.close()
        await channel.send("Session stopped.")
        self._cleanup_thread(thread_id)
        if hasattr(channel, "edit"):
            try:
                await channel.edit(archived=True)
            except Exception:
                pass

    def _cleanup_thread(self, thread_id: int):
        """Clean up all state for a thread."""
        self._bridges.pop(thread_id, None)
        listener = self._listeners.pop(thread_id, None)
        if listener and not listener.done():
            listener.cancel()
        timer = self._timers.pop(thread_id, None)
        if timer and not timer.done():
            timer.cancel()

    def _reset_inactivity_timer(self, channel: discord.Thread | Any):
        """Reset the inactivity timer for a thread."""
        thread_id = channel.id
        old_timer = self._timers.get(thread_id)
        if old_timer and not old_timer.done():
            old_timer.cancel()

        async def _timeout():
            await asyncio.sleep(self.config.inactivity_timeout)
            await self._stop_session(channel)

        self._timers[thread_id] = asyncio.create_task(_timeout())
```

**Step 4: Run test to verify it passes**

```bash
cd clients/discord && python -m pytest tests/test_bot.py -v
```

Expected: all PASSED

**Step 5: Commit**

```bash
git add clients/discord/src/bot.py clients/discord/tests/test_bot.py
git commit -m "feat(discord): add main bot with thread management and event forwarding"
```

---

### Task 7: Entry Point

**Files:**
- Create: `clients/discord/src/__main__.py`

**Step 1: Write the entry point**

Create `clients/discord/src/__main__.py`:

```python
from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from .config import Config
from .bot import MultiAgentsBot


def main():
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    try:
        config = Config.from_env()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    bot = MultiAgentsBot(config)
    bot.run(config.discord_token)


if __name__ == "__main__":
    main()
```

**Step 2: Verify it imports cleanly**

```bash
cd clients/discord && python -c "from src.__main__ import main; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add clients/discord/src/__main__.py
git commit -m "feat(discord): add entry point"
```

---

### Task 8: Run All Tests

**Step 1: Install dev dependencies and run full test suite**

```bash
cd clients/discord && pip install -e ".[dev]" && python -m pytest tests/ -v
```

Expected: all tests PASSED

**Step 2: Verify the CLI entry point is installed**

```bash
which multiagents-discord || echo "not in PATH (expected if not in venv)"
```

**Step 3: Final commit if any adjustments needed**

```bash
git add -A clients/discord/ && git diff --cached --stat
```

Only commit if there are changes.

---

### Task 9: Documentation

**Files:**
- Create: `clients/discord/README.md`

**Step 1: Write README**

Create `clients/discord/README.md`:

```markdown
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
- **Chat in thread:** Reply in the thread — messages are forwarded to agents
- **Stop:** Type `!stop` in the thread

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | Yes | — | Bot token |
| `SERVER_URL` | No | `ws://localhost:8421/ws` | Multiagents server WebSocket URL |
| `DISCORD_ALLOWLIST` | Yes | — | Comma-separated Discord user IDs |
| `DEFAULT_AGENTS` | No | `claude,codex,kimi` | Agents for new sessions |
| `INACTIVITY_TIMEOUT` | No | `1800` | Seconds before auto-archiving idle threads |
```

**Step 2: Commit**

```bash
git add clients/discord/README.md
git commit -m "docs(discord): add README with setup instructions"
```

---

## Summary

| Task | Description | Test count |
|------|-------------|------------|
| 1 | Project scaffold | — |
| 2 | Config module | 4 tests |
| 3 | Allowlist module | 3 tests |
| 4 | Formatter module | 13 tests |
| 5 | Bridge module | 5 tests |
| 6 | Bot module | 7 tests |
| 7 | Entry point | — |
| 8 | Run all tests | 32 total |
| 9 | Documentation | — |

Total: **9 tasks**, **32 tests**, **7 files** of implementation code.
