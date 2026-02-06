from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bridge import Bridge, ConnectionLost


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


class FakeWebSocketDisconnect(FakeWebSocket):
    """Simulates a connection that drops mid-stream."""

    def __init__(self, incoming: list[dict] | None = None, fail_after: int = 0):
        super().__init__(incoming)
        self._fail_after = fail_after
        self._iter_count = 0

    async def __anext__(self):
        # Deliver handshake messages via recv(), iteration messages here
        if self._iter_count >= self._fail_after:
            import websockets
            raise websockets.ConnectionClosed(None, None)
        self._iter_count += 1
        return await super().__anext__()


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


async def test_reconnect(bridge):
    """Reconnect sends join_session with last_event_id."""
    # Initial connection
    ws1 = FakeWebSocket(incoming=[
        {"type": "connected"},
        {"type": "session_created", "session_id": "sess-1", "agents": []},
    ])
    with patch("src.bridge.websockets") as mock_ws:
        mock_ws.connect = AsyncMock(return_value=ws1)
        await bridge.connect_and_create(["claude"])

    # Simulate having received some events
    bridge._last_event_id = 42

    # Reconnect
    ws2 = FakeWebSocket(incoming=[
        {"type": "connected"},
        {"type": "session_joined", "session_id": "sess-1", "messages": [], "is_running": False},
    ])
    with patch("src.bridge.websockets") as mock_ws:
        mock_ws.connect = AsyncMock(return_value=ws2)
        await bridge.reconnect()

    assert ws2.sent_messages[0] == {
        "type": "join_session",
        "session_id": "sess-1",
        "last_event_id": 42,
    }


async def test_reconnect_no_session(bridge):
    """Reconnect without a session_id raises RuntimeError."""
    with pytest.raises(RuntimeError, match="No session"):
        await bridge.reconnect()


async def test_listen_raises_connection_lost(bridge):
    """Listen raises ConnectionLost when connection drops."""
    ws = FakeWebSocketDisconnect(
        incoming=[
            {"type": "connected"},
            {"type": "session_created", "session_id": "sess-1", "agents": []},
            {"type": "round_started", "event_id": 1, "round": 1, "agents": ["claude"]},
        ],
        fail_after=1,  # Deliver 1 event then disconnect
    )
    with patch("src.bridge.websockets") as mock_ws:
        mock_ws.connect = AsyncMock(return_value=ws)
        mock_ws.ConnectionClosed = __import__("websockets").ConnectionClosed
        await bridge.connect_and_create(["claude"])

    events: list[dict] = []

    async def on_event(event: dict):
        events.append(event)

    with pytest.raises(ConnectionLost):
        await bridge.listen(on_event)


async def test_ack_sent_during_listen(bridge):
    """ACKs are sent for events with event_id."""
    ws = FakeWebSocket(incoming=[
        {"type": "connected"},
        {"type": "session_created", "session_id": "sess-1", "agents": []},
        {"type": "round_started", "event_id": 5, "round": 1, "agents": ["claude"]},
        {"type": "agent_completed", "event_id": 10, "agent": "claude", "text": "ok", "passed": False, "success": True},
    ])
    with patch("src.bridge.websockets") as mock_ws:
        mock_ws.connect = AsyncMock(return_value=ws)
        await bridge.connect_and_create(["claude"])

    events: list[dict] = []

    async def on_event(event: dict):
        events.append(event)

    # listen will raise ConnectionLost when FakeWebSocket runs out of messages
    # (StopAsyncIteration → normal loop end → ConnectionLost)
    with pytest.raises(ConnectionLost):
        await bridge.listen(on_event)

    # After listen, a final ack should have been sent
    ack_msgs = [m for m in ws.sent_messages if m.get("type") == "ack"]
    assert len(ack_msgs) >= 1
    assert ack_msgs[-1]["event_id"] == 10
    assert bridge._last_acked_id == 10


async def test_send_ack_only_when_needed(bridge):
    """_send_ack is a no-op when already acked."""
    ws = FakeWebSocket(incoming=[
        {"type": "connected"},
        {"type": "session_created", "session_id": "sess-1", "agents": []},
    ])
    with patch("src.bridge.websockets") as mock_ws:
        mock_ws.connect = AsyncMock(return_value=ws)
        await bridge.connect_and_create(["claude"])

    # No events received — ack should be no-op
    await bridge._send_ack()
    ack_msgs = [m for m in ws.sent_messages if m.get("type") == "ack"]
    assert len(ack_msgs) == 0

    # Set event_id manually
    bridge._last_event_id = 7
    await bridge._send_ack()
    ack_msgs = [m for m in ws.sent_messages if m.get("type") == "ack"]
    assert len(ack_msgs) == 1
    assert ack_msgs[0]["event_id"] == 7

    # Calling again should not send duplicate
    await bridge._send_ack()
    ack_msgs = [m for m in ws.sent_messages if m.get("type") == "ack"]
    assert len(ack_msgs) == 1
