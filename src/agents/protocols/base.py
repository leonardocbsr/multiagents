from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class AgentEvent:
    """Base class for events yielded by protocol adapters."""


@dataclass
class TextDelta(AgentEvent):
    text: str


@dataclass
class ThinkingDelta(AgentEvent):
    text: str


@dataclass
class ToolBadge(AgentEvent):
    label: str
    detail: str = ""


@dataclass
class TurnComplete(AgentEvent):
    text: str = ""
    session_id: str | None = None
    success: bool = True
    error: str | None = None


class ProtocolAdapter(ABC):
    """Abstract adapter between a common interface and an agent's wire protocol."""

    proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        """Run handshake/initialization after process spawns. No-op by default."""

    @abstractmethod
    async def send_message(self, text: str) -> None:
        """Send a user/prompt message to the agent."""

    @abstractmethod
    def read_events(self) -> AsyncIterator[AgentEvent]:
        """Yield streaming events until the current turn completes."""

    async def cancel(self) -> None:
        """Interrupt the current turn. No-op by default."""

    async def shutdown(self) -> None:
        """Graceful close. No-op by default."""

    def get_session_id(self) -> str | None:
        """Return session/thread ID for resume after crash."""
        return None
