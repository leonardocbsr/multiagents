from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Awaitable

import websockets

log = logging.getLogger("multiagents-discord")

CONNECT_TIMEOUT = 10  # seconds


class ConnectionLost(Exception):
    """Raised when the WebSocket connection is lost."""


class Bridge:
    """WebSocket client that bridges Discord to the multiagents server."""

    def __init__(self, server_url: str):
        self._server_url = server_url
        self._ws = None
        self._session_id: str | None = None
        self._last_event_id: int = 0
        self._last_acked_id: int = 0

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def connect_and_create(self, agents: list[str]) -> str:
        """Connect to server and create a new session. Returns session_id."""
        self._ws = await asyncio.wait_for(
            websockets.connect(self._server_url),
            timeout=CONNECT_TIMEOUT,
        )

        # Wait for connected message
        raw = await asyncio.wait_for(self._ws.recv(), timeout=CONNECT_TIMEOUT)
        msg = json.loads(raw)
        if msg.get("type") != "connected":
            log.warning("Expected 'connected', got: %s", msg.get("type"))

        # Create session
        await self._ws.send(json.dumps({
            "type": "create_session",
            "agents": agents,
        }))

        # Wait for session_created
        raw = await asyncio.wait_for(self._ws.recv(), timeout=CONNECT_TIMEOUT)
        msg = json.loads(raw)
        if msg.get("type") != "session_created":
            raise RuntimeError(f"Expected session_created, got: {msg.get('type')}")

        self._session_id = msg["session_id"]
        self._last_event_id = 0
        self._last_acked_id = 0
        return self._session_id

    async def reconnect(self) -> None:
        """Reconnect to an existing session via join_session."""
        if not self._session_id:
            raise RuntimeError("No session to reconnect to")

        # Close stale connection
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        self._ws = await asyncio.wait_for(
            websockets.connect(self._server_url),
            timeout=CONNECT_TIMEOUT,
        )

        # Wait for connected
        raw = await asyncio.wait_for(self._ws.recv(), timeout=CONNECT_TIMEOUT)
        msg = json.loads(raw)
        if msg.get("type") != "connected":
            log.warning("Expected 'connected', got: %s", msg.get("type"))

        # Join existing session with replay
        await self._ws.send(json.dumps({
            "type": "join_session",
            "session_id": self._session_id,
            "last_event_id": self._last_event_id,
        }))

        # Wait for session_joined
        raw = await asyncio.wait_for(self._ws.recv(), timeout=CONNECT_TIMEOUT)
        msg = json.loads(raw)
        if msg.get("type") != "session_joined":
            raise RuntimeError(f"Expected session_joined, got: {msg.get('type')}")

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

    async def _send_ack(self) -> None:
        """Send an ack for the latest event_id if needed."""
        if self._last_event_id > self._last_acked_id and self._ws:
            try:
                await self._ws.send(json.dumps({
                    "type": "ack",
                    "event_id": self._last_event_id,
                }))
                self._last_acked_id = self._last_event_id
            except Exception:
                pass

    async def listen(self, on_event: Callable[[dict], Awaitable[None]]) -> None:
        """Listen for server events and call on_event for each.

        Raises ConnectionLost when the connection drops.
        Sends event ACKs on a 250ms debounce like the web frontend.
        """
        if not self._ws:
            raise RuntimeError("Not connected")

        ack_task: asyncio.Task | None = None

        async def _deferred_ack():
            await asyncio.sleep(0.25)
            await self._send_ack()

        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                event_type = msg.get("type", "")

                # Track event IDs and schedule debounced ACK
                if "event_id" in msg:
                    self._last_event_id = msg["event_id"]
                    if ack_task is None or ack_task.done():
                        ack_task = asyncio.create_task(_deferred_ack())

                # Skip connection-level events
                if event_type in ("connected", "session_created", "session_joined"):
                    continue

                await on_event(msg)
        except websockets.ConnectionClosed:
            raise ConnectionLost("WebSocket connection closed")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise ConnectionLost(str(exc)) from exc
        finally:
            if ack_task and not ack_task.done():
                ack_task.cancel()
            await self._send_ack()

        # async for ended normally — server closed the connection
        raise ConnectionLost("Connection closed")

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            await self._ws.close()
            self._ws = None
