import pytest
from unittest.mock import AsyncMock

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
