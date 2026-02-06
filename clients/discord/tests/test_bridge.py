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

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx < len(self._incoming):
            msg = json.dumps(self._incoming[self._idx])
            self._idx += 1
            return msg
        raise StopAsyncIteration

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
        {"type": "connected"},
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
        {"type": "connected"},
        {"type": "session_created", "session_id": "sess-1", "agents": []},
    ])
    with patch("src.bridge.websockets") as mock_ws:
        mock_ws.connect = AsyncMock(return_value=ws)
        await bridge.connect_and_create(["claude"])

    await bridge.send_message("hello agents")
    assert ws.sent_messages[-1] == {"type": "message", "text": "hello agents"}


async def test_cancel(bridge):
    ws = FakeWebSocket(incoming=[
        {"type": "connected"},
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
        {"type": "connected"},
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
        {"type": "connected"},
        {"type": "session_created", "session_id": "sess-1", "agents": []},
    ])
    with patch("src.bridge.websockets") as mock_ws:
        mock_ws.connect = AsyncMock(return_value=ws)
        await bridge.connect_and_create(["claude"])

    await bridge.close()
    assert ws._closed is True
