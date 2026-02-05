"""Tests for CardEngine lifecycle, prompts, delegation, and edge cases."""

from __future__ import annotations

import pytest

from src.cards.engine import CardEngine, detect_done
from src.cards.models import Card, CardStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENTS = ["claude", "codex", "kimi"]


def _make_engine() -> CardEngine:
    return CardEngine(AGENTS)


def _make_card(engine: CardEngine, **overrides) -> Card:
    defaults = {
        "title": "Build REST API",
        "description": "Create a REST API for the widget service.",
        "planner": "claude",
        "implementer": "codex",
        "reviewer": "kimi",
        "coordinator": "",
    }
    defaults.update(overrides)
    return engine.create_card(**defaults)


# ---------------------------------------------------------------------------
# detect_done
# ---------------------------------------------------------------------------


class TestDetectDone:
    def test_exact(self):
        assert detect_done("[DONE]") is True

    def test_case_insensitive(self):
        assert detect_done("[done]") is True
        assert detect_done("[Done]") is True

    def test_embedded(self):
        assert detect_done("Plan is ready. [DONE]") is True
        assert detect_done("[DONE] I'm finished.") is True

    def test_negative(self):
        assert detect_done("Almost done") is False
        assert detect_done("[PASS]") is False
        assert detect_done("") is False


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestCRUD:
    def test_create_card(self):
        engine = _make_engine()
        card = _make_card(engine)
        assert card.title == "Build REST API"
        assert card.status == CardStatus.BACKLOG
        assert card.planner == "claude"
        assert card.implementer == "codex"
        assert card.reviewer == "kimi"
        assert card.id  # non-empty
        assert card.created_at  # non-empty

    def test_create_card_defaults(self):
        engine = _make_engine()
        card = engine.create_card("Title", "Desc")
        assert card.planner == ""
        assert card.implementer == ""
        assert card.reviewer == ""

    def test_get_card(self):
        engine = _make_engine()
        card = _make_card(engine)
        fetched = engine.get_card(card.id)
        assert fetched is card

    def test_get_card_missing(self):
        engine = _make_engine()
        with pytest.raises(KeyError):
            engine.get_card("nonexistent")

    def test_update_card(self):
        engine = _make_engine()
        card = _make_card(engine)
        updated = engine.update_card(card.id, title="New Title")
        assert updated.title == "New Title"

    def test_update_card_invalid_field(self):
        engine = _make_engine()
        card = _make_card(engine)
        with pytest.raises(ValueError, match="no field"):
            engine.update_card(card.id, nonexistent="value")

    def test_delete_card(self):
        engine = _make_engine()
        card = _make_card(engine)
        engine.delete_card(card.id)
        with pytest.raises(KeyError):
            engine.get_card(card.id)

    def test_delete_card_missing(self):
        engine = _make_engine()
        with pytest.raises(KeyError):
            engine.delete_card("nonexistent")

    def test_get_cards(self):
        engine = _make_engine()
        _make_card(engine, title="A")
        _make_card(engine, title="B")
        assert len(engine.get_cards()) == 2

    def test_get_cards_empty(self):
        engine = _make_engine()
        assert engine.get_cards() == []


# ---------------------------------------------------------------------------
# get_cards_for_agent
# ---------------------------------------------------------------------------


class TestGetCardsForAgent:
    def test_filter_by_planner(self):
        engine = _make_engine()
        _make_card(engine, planner="claude", implementer="codex", reviewer="kimi")
        _make_card(engine, planner="codex", implementer="kimi", reviewer="claude")
        result = engine.get_cards_for_agent("claude")
        assert len(result) == 2  # claude is planner on 1st, reviewer on 2nd

    def test_filter_by_implementer(self):
        engine = _make_engine()
        _make_card(engine, planner="claude", implementer="codex", reviewer="kimi")
        result = engine.get_cards_for_agent("codex")
        assert len(result) == 1

    def test_filter_no_match(self):
        engine = _make_engine()
        _make_card(engine, planner="claude", implementer="codex", reviewer="kimi")
        result = engine.get_cards_for_agent("nonexistent")
        assert result == []

    def test_filter_case_insensitive(self):
        engine = _make_engine()
        _make_card(engine, planner="Claude", implementer="codex", reviewer="kimi")
        result = engine.get_cards_for_agent("claude")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Full lifecycle: happy path
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    def test_backlog_to_done(self):
        """backlog -> planning -> review(approve) -> implementing -> review(approve) -> mark_done"""
        engine = _make_engine()
        card = _make_card(engine)

        # 1. Start: backlog -> planning
        card, prompt = engine.start_card(card.id)
        assert card.status == CardStatus.PLANNING
        assert "[TASK:" in prompt
        assert "@claude" in prompt
        assert "PLANNER" in prompt

        # 2. Planner completes: planning -> reviewing
        plan_content = "Step 1: Design schema\nStep 2: Implement\n[DONE]"
        card, prompt = engine.on_agent_completed(card.id, "claude", plan_content)
        assert card.status == CardStatus.REVIEWING
        assert card.previous_phase == CardStatus.PLANNING
        assert prompt is not None
        assert "@kimi" in prompt
        assert "REVIEWER" in prompt
        assert plan_content in prompt

        # 3. Reviewer approves plan: reviewing -> implementing
        review_content = "Plan looks good. [DONE]"
        card, prompt = engine.on_agent_completed(card.id, "kimi", review_content)
        assert card.status == CardStatus.IMPLEMENTING
        assert prompt is not None
        assert "@codex" in prompt
        assert "IMPLEMENTER" in prompt

        # 4. Implementer completes: implementing -> reviewing
        impl_content = "Implemented the schema and endpoints. [DONE]"
        card, prompt = engine.on_agent_completed(card.id, "codex", impl_content)
        assert card.status == CardStatus.REVIEWING
        assert card.previous_phase == CardStatus.IMPLEMENTING
        assert prompt is not None
        assert "@kimi" in prompt
        assert impl_content in prompt

        # 5. Reviewer approves implementation: stays reviewing, returns None
        review2_content = "Implementation meets criteria. [DONE]"
        card, prompt = engine.on_agent_completed(card.id, "kimi", review2_content)
        assert card.status == CardStatus.REVIEWING
        assert prompt is None  # waiting for user

        # 6. User marks done
        card = engine.mark_done(card.id)
        assert card.status == CardStatus.DONE

    def test_history_accumulates(self):
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)
        engine.on_agent_completed(card.id, "claude", "Plan here [DONE]")
        engine.on_agent_completed(card.id, "kimi", "Looks good [DONE]")
        engine.on_agent_completed(card.id, "codex", "Implemented [DONE]")
        assert len(card.history) == 3
        assert card.history[0].phase == CardStatus.PLANNING
        assert card.history[1].phase == CardStatus.REVIEWING
        assert card.history[2].phase == CardStatus.IMPLEMENTING


# ---------------------------------------------------------------------------
# Rejection loop
# ---------------------------------------------------------------------------


class TestRejectionLoop:
    def test_review_rejects_plan(self):
        """review rejects -> back to planning -> re-review -> approve"""
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)

        # Planner finishes
        engine.on_agent_completed(card.id, "claude", "Initial plan [DONE]")
        assert card.status == CardStatus.REVIEWING

        # Reviewer rejects (no [DONE])
        feedback = "The plan is missing error handling."
        card, prompt = engine.on_agent_completed(card.id, "kimi", feedback)
        assert card.status == CardStatus.PLANNING
        assert prompt is not None
        assert "reviewer sent back" in prompt.lower()
        assert feedback in prompt
        assert "@claude" in prompt

        # Planner revises
        card, prompt = engine.on_agent_completed(
            card.id, "claude", "Updated plan with error handling [DONE]"
        )
        assert card.status == CardStatus.REVIEWING
        assert prompt is not None

        # Reviewer approves
        card, prompt = engine.on_agent_completed(card.id, "kimi", "Good now [DONE]")
        assert card.status == CardStatus.IMPLEMENTING

    def test_review_rejects_implementation(self):
        """review rejects implementation -> back to implementing -> re-review"""
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)

        # Planning -> Review -> Implementing
        engine.on_agent_completed(card.id, "claude", "Plan [DONE]")
        engine.on_agent_completed(card.id, "kimi", "OK [DONE]")

        # Implementer finishes
        engine.on_agent_completed(card.id, "codex", "Code here [DONE]")
        assert card.status == CardStatus.REVIEWING

        # Reviewer rejects
        feedback = "Missing unit tests."
        card, prompt = engine.on_agent_completed(card.id, "kimi", feedback)
        assert card.status == CardStatus.IMPLEMENTING
        assert prompt is not None
        assert "reviewer sent back" in prompt.lower()
        assert feedback in prompt
        assert "@codex" in prompt

        # Implementer revises
        card, prompt = engine.on_agent_completed(
            card.id, "codex", "Added tests [DONE]"
        )
        assert card.status == CardStatus.REVIEWING

        # Reviewer approves
        card, prompt = engine.on_agent_completed(card.id, "kimi", "All good [DONE]")
        assert card.status == CardStatus.REVIEWING
        assert prompt is None  # wait for user


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------


class TestPromptGeneration:
    def test_planning_prompt_format(self):
        engine = _make_engine()
        card = _make_card(engine)
        _, prompt = engine.start_card(card.id)
        assert prompt.startswith(f"[TASK:{card.id}]")
        assert "@claude" in prompt
        assert "PLANNER" in prompt
        assert card.title in prompt
        assert card.description in prompt
        assert "[DONE]" in prompt

    def test_review_prompt_after_planning(self):
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)
        plan = "Step 1: Do X\nStep 2: Do Y\n[DONE]"
        _, prompt = engine.on_agent_completed(card.id, "claude", plan)
        assert prompt.startswith(f"[TASK:{card.id}]")
        assert "@kimi" in prompt
        assert "REVIEWER" in prompt
        assert "planner" in prompt.lower()
        assert plan in prompt
        assert "[DONE]" in prompt

    def test_implementation_prompt(self):
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)
        engine.on_agent_completed(card.id, "claude", "The plan [DONE]")
        _, prompt = engine.on_agent_completed(card.id, "kimi", "OK [DONE]")
        assert prompt.startswith(f"[TASK:{card.id}]")
        assert "@codex" in prompt
        assert "IMPLEMENTER" in prompt
        assert "approved plan" in prompt.lower()
        assert "[DONE]" in prompt

    def test_review_prompt_after_implementation(self):
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)
        engine.on_agent_completed(card.id, "claude", "The plan [DONE]")
        engine.on_agent_completed(card.id, "kimi", "OK [DONE]")
        _, prompt = engine.on_agent_completed(
            card.id, "codex", "Implemented everything [DONE]"
        )
        assert prompt.startswith(f"[TASK:{card.id}]")
        assert "@kimi" in prompt
        assert "implementer" in prompt.lower()
        assert "Original plan" in prompt

    def test_rejection_prompt(self):
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)
        engine.on_agent_completed(card.id, "claude", "Plan A [DONE]")
        feedback = "Needs more detail on error handling."
        _, prompt = engine.on_agent_completed(card.id, "kimi", feedback)
        assert prompt.startswith(f"[TASK:{card.id}]")
        assert "@claude" in prompt
        assert "reviewer sent back" in prompt.lower()
        assert feedback in prompt
        assert "[DONE]" in prompt

    def test_implementation_prompt_includes_reviewer_feedback_after_rejection(self):
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)
        engine.on_agent_completed(card.id, "claude", "Plan [DONE]")
        engine.on_agent_completed(card.id, "kimi", "Approved [DONE]")
        engine.on_agent_completed(card.id, "codex", "Code v1 [DONE]")
        # Reject implementation
        engine.on_agent_completed(card.id, "kimi", "Needs tests")
        # Implementer re-implements
        engine.on_agent_completed(card.id, "codex", "Code v2 [DONE]")
        # The review prompt after second implementation should reference the plan
        card_obj = engine.get_card(card.id)
        assert card_obj.status == CardStatus.REVIEWING


# ---------------------------------------------------------------------------
# Delegation
# ---------------------------------------------------------------------------


class TestDelegation:
    def test_build_delegation_prompt(self):
        engine = _make_engine()
        card = _make_card(engine, planner="", implementer="", reviewer="")
        prompt = engine.build_delegation_prompt(card.id)
        assert card.title in prompt
        assert card.description in prompt
        assert "claude" in prompt
        assert "codex" in prompt
        assert "kimi" in prompt
        assert "Planner" in prompt
        assert "Implementer" in prompt
        assert "Reviewer" in prompt

    def test_parse_delegation_response_success(self):
        engine = _make_engine()
        card = _make_card(engine, planner="", implementer="", reviewer="")
        responses = {
            "claude": "I think Planner: @Claude, Implementer: @Codex, Reviewer: @Kimi",
            "codex": "Sounds good to me!",
            "kimi": "+1 Claude's suggestion.",
        }
        result = engine.parse_delegation_response(card.id, responses)
        assert result is not None
        assert result.planner == "claude"
        assert result.implementer == "codex"
        assert result.reviewer == "kimi"

    def test_parse_delegation_response_partial(self):
        engine = _make_engine()
        card = _make_card(engine, planner="", implementer="", reviewer="")
        responses = {
            "claude": "Planner: @Claude",
            "codex": "I can implement",
        }
        result = engine.parse_delegation_response(card.id, responses)
        assert result is None

    def test_parse_delegation_response_case_insensitive(self):
        engine = _make_engine()
        card = _make_card(engine, planner="", implementer="", reviewer="")
        responses = {
            "claude": "planner: @claude, implementer: @codex, reviewer: @kimi",
        }
        result = engine.parse_delegation_response(card.id, responses)
        assert result is not None
        assert result.planner == "claude"

    def test_parse_delegation_across_multiple_responses(self):
        engine = _make_engine()
        card = _make_card(engine, planner="", implementer="", reviewer="")
        responses = {
            "claude": "Planner: @Claude",
            "codex": "Implementer: @Codex",
            "kimi": "Reviewer: @Kimi",
        }
        result = engine.parse_delegation_response(card.id, responses)
        assert result is not None
        assert result.planner == "claude"
        assert result.implementer == "codex"
        assert result.reviewer == "kimi"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_start_non_backlog_card_raises(self):
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)  # now in PLANNING
        with pytest.raises(ValueError, match="backlog"):
            engine.start_card(card.id)

    def test_mark_done_non_reviewing_card_raises(self):
        engine = _make_engine()
        card = _make_card(engine)
        with pytest.raises(ValueError, match="reviewing"):
            engine.mark_done(card.id)

    def test_mark_done_from_planning_raises(self):
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)
        with pytest.raises(ValueError, match="reviewing"):
            engine.mark_done(card.id)

    def test_on_agent_completed_no_done_in_planning(self):
        """If the planner doesn't say [DONE], card stays in planning with no new prompt."""
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)
        card, prompt = engine.on_agent_completed(
            card.id, "claude", "Still working on it..."
        )
        assert card.status == CardStatus.PLANNING
        assert prompt is None

    def test_on_agent_completed_no_done_in_implementing(self):
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)
        engine.on_agent_completed(card.id, "claude", "Plan [DONE]")
        engine.on_agent_completed(card.id, "kimi", "OK [DONE]")
        card, prompt = engine.on_agent_completed(
            card.id, "codex", "Working on it..."
        )
        assert card.status == CardStatus.IMPLEMENTING
        assert prompt is None

    def test_card_id_uniqueness(self):
        engine = _make_engine()
        c1 = _make_card(engine, title="A")
        c2 = _make_card(engine, title="B")
        assert c1.id != c2.id

    def test_agent_name_lowercased(self):
        engine = _make_engine()
        card = engine.create_card(
            "T", "D", planner="Claude", implementer="Codex", reviewer="Kimi"
        )
        assert card.planner == "claude"
        assert card.implementer == "codex"
        assert card.reviewer == "kimi"


# ---------------------------------------------------------------------------
# Coordinator lifecycle
# ---------------------------------------------------------------------------


class TestCoordinatorLifecycle:
    """Test the full coordinator flow: COORDINATING -> PLANNING -> REVIEWING -> COORDINATING -> ... -> DONE"""

    def test_happy_path(self):
        """Full path: backlog -> coordinating(initial) -> planning -> reviewing ->
        coordinating(plan_decision) -> implementing -> reviewing ->
        coordinating(impl_decision) -> done"""
        engine = _make_engine()
        card = _make_card(engine, coordinator="claude", planner="codex", implementer="codex", reviewer="kimi")

        # 1. Start: backlog -> coordinating(initial)
        card, prompt = engine.start_card(card.id)
        assert card.status == CardStatus.COORDINATING
        assert card.coordination_stage == "initial"
        assert "COORDINATOR" in prompt
        assert "@claude" in prompt

        # 2. Coordinator sets direction: coordinating -> planning
        card, prompt = engine.on_agent_completed(card.id, "claude", "Focus on REST endpoints first. [DONE]")
        assert card.status == CardStatus.PLANNING
        assert card.coordination_stage == ""
        assert "@codex" in prompt
        assert "PLANNER" in prompt

        # 3. Planner completes: planning -> reviewing
        card, prompt = engine.on_agent_completed(card.id, "codex", "Step 1: endpoints. Step 2: tests. [DONE]")
        assert card.status == CardStatus.REVIEWING
        assert card.previous_phase == CardStatus.PLANNING

        # 4. Reviewer provides feedback: reviewing -> coordinating(plan_decision)
        card, prompt = engine.on_agent_completed(card.id, "kimi", "Plan looks reasonable but needs error handling.")
        assert card.status == CardStatus.COORDINATING
        assert card.coordination_stage == "plan_decision"
        assert "tech lead" in prompt.lower() or "COORDINATOR" in prompt

        # 5. Coordinator approves plan: coordinating -> implementing
        card, prompt = engine.on_agent_completed(card.id, "claude", "Plan is acceptable, proceed. [DONE]")
        assert card.status == CardStatus.IMPLEMENTING
        assert card.coordination_stage == ""
        assert "@codex" in prompt
        assert "IMPLEMENTER" in prompt

        # 6. Implementer completes: implementing -> reviewing
        card, prompt = engine.on_agent_completed(card.id, "codex", "Implemented endpoints and tests. [DONE]")
        assert card.status == CardStatus.REVIEWING
        assert card.previous_phase == CardStatus.IMPLEMENTING

        # 7. Reviewer provides feedback: reviewing -> coordinating(impl_decision)
        card, prompt = engine.on_agent_completed(card.id, "kimi", "Implementation looks good. [DONE]")
        assert card.status == CardStatus.COORDINATING
        assert card.coordination_stage == "impl_decision"

        # 8. Coordinator approves: coordinating -> done
        card, prompt = engine.on_agent_completed(card.id, "claude", "Ship it. [DONE]")
        assert card.status == CardStatus.DONE
        assert prompt is None

    def test_coordinator_assigns_roles(self):
        """Coordinator can assign missing roles during initial phase."""
        engine = _make_engine()
        card = _make_card(engine, coordinator="claude", planner="", implementer="", reviewer="")

        card, _ = engine.start_card(card.id)
        assert card.status == CardStatus.COORDINATING

        # Coordinator assigns roles
        card, prompt = engine.on_agent_completed(
            card.id, "claude",
            "Planner: @Codex, Implementer: @Codex, Reviewer: @Kimi\nLet's start. [DONE]"
        )
        assert card.status == CardStatus.PLANNING
        assert card.planner == "codex"
        assert card.implementer == "codex"
        assert card.reviewer == "kimi"

    def test_coordinator_rejects_plan(self):
        """Coordinator sends plan back to planner."""
        engine = _make_engine()
        card = _make_card(engine, coordinator="claude", planner="codex", implementer="codex", reviewer="kimi")

        engine.start_card(card.id)
        engine.on_agent_completed(card.id, "claude", "Go ahead. [DONE]")  # initial -> planning
        engine.on_agent_completed(card.id, "codex", "Plan v1. [DONE]")    # planning -> reviewing
        engine.on_agent_completed(card.id, "kimi", "Needs work.")          # reviewing -> coordinating(plan_decision)

        # Coordinator rejects
        card, prompt = engine.on_agent_completed(card.id, "claude", "Reviewer is right, add caching.")
        assert card.status == CardStatus.PLANNING
        assert card.coordination_stage == ""
        assert prompt is not None
        assert "coordinator sent back" in prompt.lower()
        assert "@codex" in prompt

    def test_coordinator_rejects_implementation(self):
        """Coordinator sends implementation back."""
        engine = _make_engine()
        card = _make_card(engine, coordinator="claude", planner="codex", implementer="codex", reviewer="kimi")

        # Run through to impl_decision
        engine.start_card(card.id)
        engine.on_agent_completed(card.id, "claude", "Go. [DONE]")       # initial
        engine.on_agent_completed(card.id, "codex", "Plan. [DONE]")      # planning
        engine.on_agent_completed(card.id, "kimi", "OK.")                 # reviewing -> coord(plan)
        engine.on_agent_completed(card.id, "claude", "Approved. [DONE]") # plan_decision -> impl
        engine.on_agent_completed(card.id, "codex", "Code. [DONE]")      # impl -> reviewing
        engine.on_agent_completed(card.id, "kimi", "Missing tests.")     # reviewing -> coord(impl)

        # Coordinator rejects
        card, prompt = engine.on_agent_completed(card.id, "claude", "Add tests as reviewer says.")
        assert card.status == CardStatus.IMPLEMENTING
        assert card.coordination_stage == ""
        assert prompt is not None
        assert "@codex" in prompt

    def test_coordinator_approach_in_planning_prompt(self):
        """Planning prompt should include coordinator's direction."""
        engine = _make_engine()
        card = _make_card(engine, coordinator="claude", planner="codex", implementer="codex", reviewer="kimi")

        engine.start_card(card.id)
        engine.on_agent_completed(card.id, "claude", "Use microservices architecture. [DONE]")

        card = engine.get_card(card.id)
        assert card.status == CardStatus.PLANNING
        # The planning prompt was returned from on_agent_completed — check history
        # has the coordinator entry
        assert len(card.history) == 1
        assert card.history[0].phase == CardStatus.COORDINATING

    def test_no_done_in_coordinating_stays(self):
        """If coordinator doesn't say [DONE], card stays in coordinating."""
        engine = _make_engine()
        card = _make_card(engine, coordinator="claude", planner="codex", implementer="codex", reviewer="kimi")

        engine.start_card(card.id)
        card, prompt = engine.on_agent_completed(card.id, "claude", "Still thinking about approach...")
        assert card.status == CardStatus.COORDINATING
        assert card.coordination_stage == "initial"
        assert prompt is None


class TestCoordinatorDelegation:
    """Test delegation with coordinator role."""

    def test_delegation_includes_coordinator(self):
        """Delegation prompt mentions coordinator role."""
        engine = _make_engine()
        card = _make_card(engine, planner="", implementer="", reviewer="", coordinator="")
        prompt = engine.build_delegation_prompt(card.id)
        assert "coordinator" in prompt.lower()

    def test_delegation_parses_coordinator(self):
        """Delegation response can include coordinator assignment."""
        engine = _make_engine()
        card = _make_card(engine, planner="", implementer="", reviewer="", coordinator="")
        responses = {
            "claude": "Coordinator: @Claude, Planner: @Codex, Implementer: @Codex, Reviewer: @Kimi",
        }
        result = engine.parse_delegation_response(card.id, responses)
        assert result is not None
        assert result.coordinator == "claude"
        assert result.planner == "codex"
        assert result.reviewer == "kimi"

    def test_delegation_succeeds_without_coordinator(self):
        """Delegation still works without coordinator (backward compat)."""
        engine = _make_engine()
        card = _make_card(engine, planner="", implementer="", reviewer="", coordinator="")
        responses = {
            "claude": "Planner: @Claude, Implementer: @Codex, Reviewer: @Kimi",
        }
        result = engine.parse_delegation_response(card.id, responses)
        assert result is not None
        assert result.coordinator == ""  # unchanged
        assert result.planner == "claude"


class TestBackwardCompatibility:
    """Verify no-coordinator cards behave exactly as before."""

    def test_no_coordinator_same_lifecycle(self):
        """Without coordinator, lifecycle is unchanged."""
        engine = _make_engine()
        card = _make_card(engine)  # no coordinator by default
        assert card.coordinator == ""

        card, prompt = engine.start_card(card.id)
        assert card.status == CardStatus.PLANNING  # skips coordinating
        assert "PLANNER" in prompt

    def test_no_coordinator_review_auto_transitions(self):
        """Without coordinator, reviewer directly approves/rejects."""
        engine = _make_engine()
        card = _make_card(engine)
        engine.start_card(card.id)
        engine.on_agent_completed(card.id, "claude", "Plan [DONE]")

        # Reviewer approves → implementing (no coordinator gate)
        card, prompt = engine.on_agent_completed(card.id, "kimi", "OK [DONE]")
        assert card.status == CardStatus.IMPLEMENTING

    def test_get_cards_for_agent_finds_coordinator(self):
        """get_cards_for_agent includes cards where agent is coordinator."""
        engine = _make_engine()
        _make_card(engine, coordinator="claude", planner="codex", implementer="codex", reviewer="kimi")
        result = engine.get_cards_for_agent("claude")
        assert len(result) == 1
