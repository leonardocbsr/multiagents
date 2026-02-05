import asyncio
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass

import pytest

from src.agents.base import AgentResponse
from src.chat.room import ChatRoom
from src.chat.events import (
    AgentCompleted,
    AgentDeliveryAcked,
    AgentNotice,
    AgentPromptAssembled,
    RoundPaused,
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
async def test_system_message_injection():
    agents = [
        FakeAgent("claude", ["First", "Second", "[PASS]"]),
        FakeAgent("codex", ["First", "Second", "[PASS]"]),
    ]
    room = ChatRoom(agents)
    events = []

    async def inject_system():
        await asyncio.sleep(0.01)
        room.inject_system_message("Task card created: [abc123] Build API")

    asyncio.create_task(inject_system())

    async for event in room.run("Build an API"):
        events.append(event)

    notices = [e for e in events if isinstance(e, AgentNotice) and e.agent_name == "system"]
    assert notices
    assert "Task card created" in notices[0].message

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


class PersistentSequencedAgent:
    def __init__(self, name: str, responses: list[tuple[float, str]]):
        self.name = name
        self.session_id = None
        self._responses = list(responses)
        self._index = 0
        self.cancel_calls = 0

    async def stream(self, prompt, timeout=120.0):
        delay, text = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        if delay:
            await asyncio.sleep(delay)
        if text:
            yield text
        yield AgentResponse(
            agent=self.name,
            response=text,
            success=True,
            latency_ms=max(delay, 0.0) * 1000,
        )

    async def cancel_turn(self) -> None:
        self.cancel_calls += 1


def test_persistent_drain_inbox_batch_collects_buffered_events():
    agent = PersistentSequencedAgent("claude", responses=[(0.00, "[PASS]")])
    room = ChatRoom([agent])
    room._inboxes = {"claude": asyncio.Queue()}
    room._inboxes["claude"].put_nowait(("user", "second", 1, "d2"))
    room._inboxes["claude"].put_nowait(("system", "notice", 1, "d3"))

    batch = room._drain_inbox_batch("claude", ("user", "first", 1, "d1"))
    assert batch == [
        ("user", "first", 1, "d1"),
        ("user", "second", 1, "d2"),
        ("system", "notice", 1, "d3"),
    ]


def test_persistent_batch_prompt_combines_events():
    agent = PersistentSequencedAgent("claude", responses=[(0.00, "[PASS]")])
    room = ChatRoom([agent])

    prompt = room._format_persistent_events_prompt(
        agent=agent,
        events=[
            ("user", "first request", 1, "d1"),
            ("system", "board changed", 1, "d2"),
            ("codex", "new findings", 1, "d3"),
        ],
        is_first_message=False,
    )
    assert "## Incoming Events" in prompt
    assert "[User]: first request" in prompt
    assert "[System]: board changed" in prompt
    assert "[Codex] shared:\nnew findings" in prompt


def test_relay_dedup_blocks_repeated_share_within_cooldown():
    agent = PersistentSequencedAgent("claude", responses=[(0.00, "[PASS]")])
    room = ChatRoom([agent])

    assert room._should_relay_share("claude", "codex", "same finding") is True
    assert room._should_relay_share("claude", "codex", "same finding") is False
    # Whitespace/case variations are treated as duplicates.
    assert room._should_relay_share("Claude", "Codex", "  SAME   finding ") is False


def test_delivery_ack_tracking_clears_when_all_recipients_ack():
    a1 = PersistentSequencedAgent("claude", responses=[(0.00, "[PASS]")])
    a2 = PersistentSequencedAgent("codex", responses=[(0.00, "[PASS]")])
    room = ChatRoom([a1, a2])
    queue: asyncio.Queue = asyncio.Queue()

    delivery_id = room._enqueue_delivery(
        sender="claude",
        message="share",
        round_number=1,
        recipients=["claude", "codex"],
    )
    assert delivery_id is not None
    assert room._delivery_pending[delivery_id] == {"claude", "codex"}

    room._ack_delivery(
        event_queue=queue,
        delivery_id=delivery_id,
        recipient="claude",
        sender="claude",
        round_number=1,
    )
    assert delivery_id in room._delivery_pending
    assert room._delivery_pending[delivery_id] == {"codex"}

    room._ack_delivery(
        event_queue=queue,
        delivery_id=delivery_id,
        recipient="codex",
        sender="claude",
        round_number=1,
    )
    assert delivery_id not in room._delivery_pending

    e1 = queue.get_nowait()
    e2 = queue.get_nowait()
    assert isinstance(e1, AgentDeliveryAcked)
    assert isinstance(e2, AgentDeliveryAcked)
    assert {e1.recipient, e2.recipient} == {"claude", "codex"}


def test_drop_agent_pending_deliveries_removes_stale_entries():
    a1 = PersistentSequencedAgent("claude", responses=[(0.00, "[PASS]")])
    a2 = PersistentSequencedAgent("codex", responses=[(0.00, "[PASS]")])
    room = ChatRoom([a1, a2])

    d1 = room._enqueue_delivery(
        sender="user",
        message="m1",
        round_number=1,
        recipients=["claude", "codex"],
    )
    d2 = room._enqueue_delivery(
        sender="user",
        message="m2",
        round_number=1,
        recipients=["codex"],
    )
    assert d1 and d2

    room._drop_agent_pending_deliveries("codex")
    assert room._delivery_pending[d1] == {"claude"}
    assert d2 not in room._delivery_pending

@pytest.mark.asyncio
async def test_persistent_round_attribution_with_overlap():
    agent = PersistentSequencedAgent(
        "claude",
        responses=[
            (0.15, "first response without share"),
            (0.00, "[PASS]"),
        ],
    )
    room = ChatRoom([agent])

    events = []

    async def inject_second_user_msg() -> None:
        await asyncio.sleep(0.05)
        room.inject_user_message("second prompt")

    asyncio.create_task(inject_second_user_msg())

    async for event in room.run_persistent("initial prompt"):
        events.append(event)
        completed = [e for e in events if isinstance(e, AgentCompleted)]
        if len(completed) >= 2:
            break

    completed = [e for e in events if isinstance(e, AgentCompleted)]
    assert len(completed) >= 2
    assert completed[0].round_number == 1
    assert completed[1].round_number == 1

    starts = [e.round_number for e in events if isinstance(e, RoundStarted)]
    assert starts == [1]


class PersistentSlowAgent:
    def __init__(self, name: str):
        self.name = name
        self.session_id = None
        self._calls = 0
        self.cancel_calls = 0

    async def stream(self, prompt, timeout=120.0):
        self._calls += 1
        if self._calls == 1:
            for _ in range(100):
                await asyncio.sleep(0.05)
                yield "chunk "
            yield AgentResponse(
                agent=self.name,
                response="completed first turn",
                success=True,
                latency_ms=5000,
            )
            return
        yield "[PASS]"
        yield AgentResponse(
            agent=self.name,
            response="[PASS]",
            success=True,
            latency_ms=10,
        )

    async def cancel_turn(self) -> None:
        self.cancel_calls += 1


@pytest.mark.asyncio
async def test_persistent_restart_runs_dm_without_cancel():
    agent = PersistentSlowAgent("claude")
    room = ChatRoom([agent])

    events = []

    async def restart_with_dm() -> None:
        await asyncio.sleep(0.1)
        await room.restart_agent("claude", "please pivot")

    asyncio.create_task(restart_with_dm())

    async for event in room.run_persistent("start"):
        events.append(event)
        completed = [e for e in events if isinstance(e, AgentCompleted)]
        prompts = [e for e in events if isinstance(e, AgentPromptAssembled)]
        has_passed = any(e.passed for e in completed)
        has_dm_prompt = any("## Direct Message from User" in e.sections.get("message", "") for e in prompts)
        if has_passed and has_dm_prompt:
            break

    completed = [e for e in events if isinstance(e, AgentCompleted)]
    prompts = [e for e in events if isinstance(e, AgentPromptAssembled)]
    assert not any(e.stopped for e in completed)
    assert any(e.passed for e in completed)
    assert agent.cancel_calls == 0
    assert any("## Direct Message from User" in e.sections.get("message", "") for e in prompts)


@pytest.mark.asyncio
async def test_persistent_prompt_templates_cover_user_and_relay_events():
    claude = PersistentSequencedAgent(
        "claude",
        responses=[
            (0.00, "<Share>check this from claude</Share>"),
            (0.00, "[PASS]"),
        ],
    )
    codex = PersistentSequencedAgent(
        "codex",
        responses=[
            (0.00, "[PASS]"),
            (0.00, "[PASS]"),
        ],
    )
    room = ChatRoom([claude, codex])

    prompts: list[AgentPromptAssembled] = []
    async for event in room.run_persistent("initial prompt"):
        if isinstance(event, AgentPromptAssembled):
            prompts.append(event)
            if any(
                "shared:\ncheck this from claude" in p.sections.get("message", "")
                for p in prompts
            ):
                break

    initial_for_claude = next(
        p for p in prompts
        if p.agent_name == "claude" and "[User]: initial prompt" in p.sections.get("message", "")
    )
    assert "## Incoming Event" in initial_for_claude.sections["message"]
    assert "If no action is needed, respond with exactly [PASS]." in initial_for_claude.sections["message"]

    relay_for_codex = next(
        p for p in prompts
        if p.agent_name == "codex" and "shared:\ncheck this from claude" in p.sections.get("message", "")
    )
    assert "Only respond if you can add net-new value" in relay_for_codex.sections["message"]


@pytest.mark.asyncio
async def test_persistent_relay_emits_delivery_acks_for_recipients():
    claude = PersistentSequencedAgent(
        "claude",
        responses=[
            (0.00, "<Share>delivery check</Share>"),
            (0.00, "[PASS]"),
        ],
    )
    codex = PersistentSequencedAgent("codex", responses=[(0.00, "[PASS]")])
    kimi = PersistentSequencedAgent("kimi", responses=[(0.00, "[PASS]")])
    room = ChatRoom([claude, codex, kimi])

    events = []
    async for event in room.run_persistent("start"):
        events.append(event)
        relay_acks = [
            e for e in events
            if isinstance(e, AgentDeliveryAcked)
            and e.sender == "claude"
            and e.round_number == 1
        ]
        recipients = {e.recipient for e in relay_acks}
        if {"codex", "kimi"}.issubset(recipients):
            break

    relay_acks = [
        e for e in events
        if isinstance(e, AgentDeliveryAcked)
        and e.sender == "claude"
        and e.round_number == 1
    ]
    assert {e.recipient for e in relay_acks} >= {"codex", "kimi"}


@pytest.mark.asyncio
async def test_persistent_non_consensus_settlement_starts_next_round_and_relays_share():
    claude = PersistentSequencedAgent(
        "claude",
        responses=[
            (0.00, "[PASS]"),
            (0.00, "[PASS]"),
        ],
    )
    codex = PersistentSequencedAgent(
        "codex",
        responses=[
            (0.00, "[PASS]"),
            (0.00, "[PASS]"),
        ],
    )
    kimi = PersistentSequencedAgent(
        "kimi",
        responses=[
            (0.05, "<Share>critical finding</Share>"),
        ],
    )
    room = ChatRoom([claude, codex, kimi])

    events = []
    async for event in room.run_persistent("start"):
        events.append(event)
        saw_round1_end = any(
            isinstance(e, RoundEnded) and e.round_number == 1 and not e.all_passed
            for e in events
        )
        saw_round2_start = any(
            isinstance(e, RoundStarted) and e.round_number == 2
            for e in events
        )
        relay_prompts = [
            e for e in events
            if isinstance(e, AgentPromptAssembled)
            and e.agent_name in {"claude", "codex"}
            and "shared:\ncritical finding" in e.sections.get("message", "")
        ]
        if saw_round1_end and saw_round2_start and len(relay_prompts) >= 2:
            break

    assert any(
        isinstance(e, RoundEnded) and e.round_number == 1 and not e.all_passed
        for e in events
    )
    assert any(
        isinstance(e, RoundStarted) and e.round_number == 2
        for e in events
    )
    assert any(
        isinstance(e, AgentPromptAssembled)
        and e.agent_name == "claude"
        and "shared:\ncritical finding" in e.sections.get("message", "")
        for e in events
    )
    assert any(
        isinstance(e, AgentPromptAssembled)
        and e.agent_name == "codex"
        and "shared:\ncritical finding" in e.sections.get("message", "")
        for e in events
    )


@pytest.mark.asyncio
async def test_persistent_first_prompt_includes_participants_even_with_session_id():
    agent = PersistentSequencedAgent("claude", responses=[(0.00, "[PASS]")])
    agent.session_id = "existing-session"
    room = ChatRoom(
        [agent],
        participants=[
            {"name": "claude", "type": "claude"},
            {"name": "codex", "type": "codex"},
            {"name": "kimi", "type": "kimi"},
        ],
    )

    prompts: list[AgentPromptAssembled] = []
    async for event in room.run_persistent("start"):
        if isinstance(event, AgentPromptAssembled):
            prompts.append(event)
            break

    assert prompts, "expected at least one assembled prompt"
    message = prompts[0].sections.get("message", "")
    assert "Other participants: codex, kimi." in message


@pytest.mark.asyncio
async def test_persistent_all_pass_starts_next_round_only_after_new_activity():
    agent = PersistentSequencedAgent("claude", responses=[(0.00, "[PASS]"), (0.00, "[PASS]")])
    room = ChatRoom([agent])

    events = []
    saw_round1_end = False
    async for event in room.run_persistent("start"):
        events.append(event)
        if isinstance(event, RoundEnded) and event.round_number == 1:
            saw_round1_end = True
            starts = [e.round_number for e in events if isinstance(e, RoundStarted)]
            assert starts == [1]
            room.inject_user_message("next task")
            continue
        if saw_round1_end and isinstance(event, RoundStarted) and event.round_number == 2:
            break

    starts = [e.round_number for e in events if isinstance(e, RoundStarted)]
    assert starts[:2] == [1, 2]


@pytest.mark.asyncio
async def test_persistent_stop_round_can_pause_and_resume():
    agent = PersistentSlowAgent("claude")
    room = ChatRoom([agent])

    async def stop_then_resume() -> None:
        await asyncio.sleep(0.1)
        room.stop_round()
        await asyncio.sleep(0.2)
        room.resume()
        room.inject_user_message("continue")

    asyncio.create_task(stop_then_resume())

    events = []
    async for event in room.run_persistent("start"):
        events.append(event)
        saw_paused = any(isinstance(e, RoundPaused) for e in events)
        saw_post_pause_user = any(isinstance(e, UserMessageReceived) for e in events)
        saw_stopped = any(isinstance(e, AgentCompleted) and e.stopped for e in events)
        if saw_paused and saw_post_pause_user and saw_stopped:
            break

    assert any(isinstance(e, RoundPaused) for e in events)
    assert any(isinstance(e, UserMessageReceived) for e in events)
    assert any(isinstance(e, AgentCompleted) and e.stopped for e in events)
