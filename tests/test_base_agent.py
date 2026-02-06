from collections.abc import AsyncIterator

import pytest

from src.agents.base import AgentResponse, BaseAgent
from src.agents.protocols.base import TextDelta, TurnComplete


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
