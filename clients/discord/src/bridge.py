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
