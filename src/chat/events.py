from __future__ import annotations

from dataclasses import dataclass

from ..agents.base import AgentResponse


@dataclass
class ChatEvent:
    """Base class for chat events."""


@dataclass
class RoundStarted(ChatEvent):
    round_number: int
    agents: list[str]


@dataclass
class AgentStreamChunk(ChatEvent):
    agent_name: str
    round_number: int
    text: str


@dataclass
class AgentCompleted(ChatEvent):
    agent_name: str
    round_number: int
    response: AgentResponse
    passed: bool
    stopped: bool = False


@dataclass
class AgentInterrupted(ChatEvent):
    """Fired when an agent is stopped for a DM restart."""
    agent_name: str
    round_number: int
    partial_text: str


@dataclass
class AgentStderr(ChatEvent):
    agent_name: str
    round_number: int
    text: str


@dataclass
class AgentNotice(ChatEvent):
    """Visible system notice about an agent (e.g. session reset)."""
    agent_name: str
    message: str


@dataclass
class AgentPromptAssembled(ChatEvent):
    """Fired before dispatching prompt to an agent, for UI visibility."""
    agent_name: str
    round_number: int
    sections: dict[str, str]  # system, memory, cards, round_delta


@dataclass
class AgentDeliveryAcked(ChatEvent):
    """Fired when an agent dequeues a delivered inbox message."""
    delivery_id: str
    recipient: str
    sender: str
    round_number: int | None


@dataclass
class RoundEnded(ChatEvent):
    round_number: int
    all_passed: bool


@dataclass
class RoundPaused(ChatEvent):
    """Fired after a round where any agent was stopped, before next round."""
    round_number: int


@dataclass
class DiscussionEnded(ChatEvent):
    reason: str  # "all_passed" | "paused" | "error"


@dataclass
class AgentPermissionRequested(ChatEvent):
    """Agent waiting for user tool approval."""
    agent_name: str
    round_number: int
    request_id: str
    tool_name: str
    tool_input: dict
    description: str = ""


@dataclass
class UserMessageReceived(ChatEvent):
    text: str
