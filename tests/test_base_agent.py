from collections.abc import AsyncIterator

import pytest

from src.agents.base import AgentNotice, AgentResponse, BaseAgent
from src.agents.protocols.base import ProcessRestarted, TextDelta, TurnComplete


class _StubPersistent:
    def __init__(self, events: list[object]) -> None:
        self._events = events
        self._session_id = "sid-1"

    async def send_and_stream(self, prompt: str) -> AsyncIterator[object]:
        for event in self._events:
            yield event

    def get_stderr(self) -> str:
        return ""


class _DummyAgent(BaseAgent):
    name = "dummy"
    agent_type = "dummy"

    def __init__(self, persistent: _StubPersistent) -> None:
        self._stub = persistent

    def _ensure_persistent(self) -> _StubPersistent:
        return self._stub


@pytest.mark.asyncio
async def test_base_agent_uses_turn_complete_success_flag() -> None:
    agent = _DummyAgent(
        _StubPersistent(
            [
                TextDelta(text="partial output"),
                TurnComplete(session_id="sid-1", success=False, error="turn failed"),
            ]
        )
    )

    items = []
    async for item in agent.stream("hello"):
        items.append(item)

    response = next(i for i in items if isinstance(i, AgentResponse))
    assert response.success is False
    assert response.response == "partial output"
    assert response.session_id == "sid-1"


@pytest.mark.asyncio
async def test_base_agent_uses_turn_error_when_no_text() -> None:
    agent = _DummyAgent(
        _StubPersistent(
            [
                TurnComplete(session_id="sid-1", success=False, error="upstream error"),
            ]
        )
    )

    items = []
    async for item in agent.stream("hello"):
        items.append(item)

    response = next(i for i in items if isinstance(i, AgentResponse))
    assert response.success is False
    assert response.response == "upstream error"


@pytest.mark.asyncio
async def test_base_agent_emits_notice_when_persistent_process_restarts() -> None:
    agent = _DummyAgent(
        _StubPersistent(
            [
                ProcessRestarted(reason="broken pipe", retry=1),
                TurnComplete(session_id="sid-1", success=True),
            ]
        )
    )

    items = []
    async for item in agent.stream("hello"):
        items.append(item)

    notice = next(i for i in items if isinstance(i, AgentNotice))
    assert "persistent process restarted" in notice.message
    assert "retry 1" in notice.message
