import pytest
from unittest.mock import AsyncMock
from unittest.mock import patch

from src.cards.models import Card, CardStatus
from src.server.runner import SessionRunner
from src.server.sessions import SessionStore


@pytest.mark.asyncio
async def test_resolve_card_agent_with_fallback_assigns_planner(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    session = store.create_session(agent_names=["claude", "codex"])
    runner = SessionRunner(store=store)
    runner.broadcast = AsyncMock(return_value=0)  # type: ignore[method-assign]

    card = Card(
        id="card-1",
        title="Test card",
        description="",
        status=CardStatus.PLANNING,
        planner="",
        implementer="",
        reviewer="",
        coordinator="",
        coordination_stage="",
        previous_phase=None,
    )

    resolved = await runner._resolve_card_agent_with_fallback(
        session["id"], card, ["claude", "codex"],
    )

    assert resolved == "claude"
    assert card.planner == "claude"
    runner.broadcast.assert_awaited()


@pytest.mark.asyncio
async def test_get_warmed_agents_caches_fallback_agents_in_session_pool(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    session = store.create_session(agent_names=["claude"])
    session_id = session["id"]
    runner = SessionRunner(store=store)

    class _FakeAgent:
        def __init__(self, name: str):
            self.name = name
            self.agent_type = name
            self.parse_timeout = 0.0
            self.hard_timeout = None
            self.session_id = None

    with patch("src.server.runner.create_agents") as mocked_create:
        mocked_create.return_value = [_FakeAgent("claude")]

        first = await runner.get_warmed_agents(session_id, ["claude"])
        second = await runner.get_warmed_agents(session_id, ["claude"])

        assert mocked_create.call_count == 1
        assert session_id in runner._agent_pools
        assert runner._agent_pools[session_id]["claude"] is first[0]
        assert second[0] is first[0]
