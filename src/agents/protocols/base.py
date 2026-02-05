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
class ToolOutput(AgentEvent):
    """Streaming output from a tool execution (e.g. bash stdout)."""
    tool_name: str = ""
    text: str = ""


@dataclass
class ToolResult(AgentEvent):
    """Tool execution completed."""
    tool_name: str = ""
    success: bool = True
    output: str = ""  # truncated summary


@dataclass
class TurnComplete(AgentEvent):
    text: str = ""
    session_id: str | None = None
    success: bool = True
    error: str | None = None


@dataclass
class PermissionRequest(AgentEvent):
    """Agent needs user approval for a tool call."""
    request_id: str = ""
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    description: str = ""


@dataclass
class ProcessRestarted(AgentEvent):
    """Persistent process was restarted and the turn will be retried."""
    reason: str = ""
    retry: int = 0


@dataclass
class PermissionResponse:
    """User decision on a permission request."""
    request_id: str = ""
    approved: bool = False


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

    async def respond_to_permission(self, response: PermissionResponse) -> None:
        """Send permission decision back to agent CLI. No-op by default."""

    def get_session_id(self) -> str | None:
        """Return session/thread ID for resume after crash."""
        return None
