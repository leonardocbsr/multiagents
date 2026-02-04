import asyncio
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass

import pytest

from src.agents.base import AgentResponse
from src.chat.room import ChatRoom
from src.chat.events import (
    AgentCompleted,
    AgentStreamChunk,
    RoundStarted,
    RoundEnded,
    DiscussionEnded,
    UserMessageReceived,
)


class FakeAgent:
    def __init__(self, name: str, responses: list[str]):
        self.name = name
        self._responses = iter(responses)
        self.session_id = None

    async def stream(self, prompt, timeout=120.0):
        text = next(self._responses, "[PASS]")
        yield text  # stream chunk
        yield AgentResponse(
            agent=self.name,
            response=text,
            success=True,
            latency_ms=100.0,
        )


@pytest.mark.asyncio
async def test_all_pass_ends_discussion():
    agents = [
        FakeAgent("claude", ["Hello!", "[PASS]"]),
        FakeAgent("codex", ["Hi!", "[PASS]"]),
        FakeAgent("kimi", ["Hey!", "[PASS]"]),
    ]
    room = ChatRoom(agents)
    events = []
    async for event in room.run("Build an API"):
        events.append(event)

    # Round 1: all agents respond with real content
    # Round 2: all agents pass -> discussion ends
    discussion_ended = [e for e in events if isinstance(e, DiscussionEnded)]
    assert len(discussion_ended) == 1
    assert discussion_ended[0].reason == "all_passed"


@pytest.mark.asyncio
async def test_user_message_injection():
    agents = [
        FakeAgent("claude", ["First", "[PASS]"]),
        FakeAgent("codex", ["Second", "[PASS]"]),
        FakeAgent("kimi", ["Third", "[PASS]"]),
    ]
    room = ChatRoom(agents)
    events = []

    async def inject_message():
        await asyncio.sleep(0.01)
        room.inject_user_message("What about testing?")

    asyncio.create_task(inject_message())

    async for event in room.run("Build an API"):
        events.append(event)

    # Should have at least 2 rounds (initial + response to injection)
    round_starts = [e for e in events if isinstance(e, RoundStarted)]
    assert len(round_starts) >= 2


@pytest.mark.asyncio
async def test_share_tags_filter_history():
    """Only content inside <Share> tags should go to history for other agents."""
    agents = [
        FakeAgent("claude", ["<Share>Public info</Share> private stuff", "[PASS]"]),
        FakeAgent("codex", ["Got it", "[PASS]"]),
    ]
    room = ChatRoom(agents)
    
    async for _ in room.run("Test"):
        pass
    
    # Check history - only "Public info" should be in claude's first message
    claude_msgs = [m for m in room.history if m["role"] == "claude"]
    assert len(claude_msgs) == 2  # First response + [PASS]
    assert claude_msgs[0]["content"] == "Public info"
    assert "private stuff" not in claude_msgs[0]["content"]
    assert claude_msgs[0]["round"] == 1
    assert claude_msgs[1]["content"] == "[PASS]"
    assert claude_msgs[1]["round"] == 2


@pytest.mark.asyncio
async def test_no_share_tags_private():
    """If no <Share> tags, history should record a placeholder."""
    agents = [
        FakeAgent("claude", ["Full response without tags", "[PASS]"]),
    ]
    room = ChatRoom(agents)
    
    async for _ in room.run("Test"):
        pass
    
    claude_msgs = [m for m in room.history if m["role"] == "claude"]
    assert len(claude_msgs) == 2  # Placeholder + [PASS]
    assert claude_msgs[0]["content"] == "(private response withheld)"
    assert claude_msgs[0]["round"] == 1
    assert claude_msgs[1]["content"] == "[PASS]"
    assert claude_msgs[1]["round"] == 2


class SlowFakeAgent:
    """Agent that takes a while to respond, for testing stops."""
    def __init__(self, name: str, delay: float = 1.0):
        self.name = name
        self._delay = delay
        self.session_id = None

    async def stream(self, prompt, timeout=120.0):
        for i in range(10):
            yield f"chunk {i} "
            await asyncio.sleep(self._delay / 10)
        yield AgentResponse(
            agent=self.name,
            response="full response",
            success=True,
            latency_ms=self._delay * 1000,
        )


@pytest.mark.asyncio
async def test_stop_single_agent():
    """Stopping one agent mid-round should not affect other agents."""
    slow = SlowFakeAgent("claude", delay=2.0)
    fast = FakeAgent("codex", ["Done!", "[PASS]"])
    room = ChatRoom([slow, fast])

    events = []
    async def stop_after_stream():
        await asyncio.sleep(0.05)
        room.stop_agent("claude")

    asyncio.create_task(stop_after_stream())

    async for event in room.run("test"):
        events.append(event)
        if isinstance(event, RoundEnded):
            room.stop_round()
            break

    completed = [e for e in events if isinstance(e, AgentCompleted)]
    claude_done = [e for e in completed if e.agent_name == "claude"]
    codex_done = [e for e in completed if e.agent_name == "codex"]

    assert len(claude_done) == 1
    assert claude_done[0].stopped is True

    assert len(codex_done) == 1
    assert codex_done[0].stopped is False


@pytest.mark.asyncio
async def test_stop_round_stops_all_agents():
    """stop_round should stop all running agents."""
    agents = [SlowFakeAgent("claude", delay=2.0), SlowFakeAgent("codex", delay=2.0)]
    room = ChatRoom(agents)

    events = []
    async def stop_after_start():
        await asyncio.sleep(0.05)
        room.stop_round()

    asyncio.create_task(stop_after_start())

    async for event in room.run("test"):
        events.append(event)
        if isinstance(event, RoundEnded):
            break

    completed = [e for e in events if isinstance(e, AgentCompleted)]
    assert len(completed) == 2
    assert all(e.stopped is True for e in completed)


@pytest.mark.asyncio
async def test_stopped_agent_rejoins_next_round():
    """Agents stopped in round N should participate in round N+1."""
    class TwoRoundAgent:
        def __init__(self, name):
            self.name = name
            self.session_id = None
            self._round = 0

        async def stream(self, prompt, timeout=120.0):
            self._round += 1
            if self._round == 1:
                for i in range(20):
                    yield f"chunk "
                    await asyncio.sleep(0.1)
                yield AgentResponse(agent=self.name, response="full", success=True, latency_ms=2000)
            else:
                yield "[PASS]"
                yield AgentResponse(agent=self.name, response="[PASS]", success=True, latency_ms=10)

    agents = [TwoRoundAgent("claude"), TwoRoundAgent("codex")]
    room = ChatRoom(agents)

    events = []

    async def stop_round_1():
        await asyncio.sleep(0.05)
        room.stop_round(pause=False)

    asyncio.create_task(stop_round_1())

    async for event in room.run("test"):
        events.append(event)
        if isinstance(event, DiscussionEnded):
            break

    round_starts = [e for e in events if isinstance(e, RoundStarted)]
    assert len(round_starts) == 2
    assert round_starts[1].agents == ["claude", "codex"]
