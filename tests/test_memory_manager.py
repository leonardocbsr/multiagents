import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.memory.manager import MemoryManager


def test_build_context_empty(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    assert mgr.build_memory_context("anything") == ""


def test_build_context_with_episodes(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    mgr.store.save_episode(
        session_id="s1",
        query="API framework choice",
        summary="Team decided on FastAPI for REST endpoints",
        rounds=3,
        agents=["claude", "codex"],
    )
    ctx = mgr.build_memory_context("What API framework?")
    assert "FastAPI" in ctx or "API framework" in ctx
    assert "### Relevant Past Discussions" in ctx


def test_build_context_no_match(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    mgr.store.save_episode(session_id="s1", query="database", summary="PostgreSQL")
    assert mgr.build_memory_context("kubernetes deployment") == ""


def test_build_context_with_profiles(tmp_path):
    """Verify profile-based context output."""
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    mgr.store.update_agent_profile(
        agent_name="claude",
        strengths=["strong coordinator", "active communicator"],
        avg_response_time_ms=12500.0,
        best_role="coordinator",
        total_sessions=5,
    )
    mgr.store.update_agent_profile(
        agent_name="codex",
        strengths=["fast responses", "good share tag usage"],
        avg_response_time_ms=8200.0,
        best_role="implementer",
        total_sessions=3,
    )
    ctx = mgr.build_memory_context("")
    assert "## Agent Knowledge" in ctx
    assert "### Agent Capabilities" in ctx
    assert "Claude" in ctx
    assert "coordinator" in ctx
    assert "Codex" in ctx
    assert "implementer" in ctx


def test_build_context_with_ensemble_patterns(tmp_path):
    """Verify ensemble pattern context output."""
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    mgr.store.save_ensemble_pattern(
        "Claude + Codex",
        "combo",
        {"sessions": 5, "convergence_rate": 0.8, "avg_rounds": 3.2},
    )
    ctx = mgr.build_memory_context("")
    assert "### Collaboration Notes" in ctx
    assert "Claude + Codex" in ctx
    assert "5 sessions" in ctx


# --- finalize_session ---


def _write_transcript(tmp_path, session_id, events):
    d = tmp_path / ".multiagents" / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{session_id}.jsonl"
    with open(path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    return path


def _rich_transcript_events():
    """A transcript with rich agent interaction data."""
    return [
        {"type": "user_message", "ts": "t0", "session_id": "s1", "data": {"text": "Build a REST API"}},
        {"type": "round_started", "ts": "t1", "session_id": "s1", "data": {"round": 1, "agents": ["claude", "codex"]}},
        {
            "type": "agent_completed", "ts": "t2", "session_id": "s1",
            "data": {"agent": "claude", "text": "I suggest we use FastAPI for this. @codex what do you think?", "passed": False, "latency_ms": 1500, "round": 1},
        },
        {
            "type": "agent_completed", "ts": "t3", "session_id": "s1",
            "data": {"agent": "codex", "text": "+1 Claude, FastAPI is great. <Share>Use FastAPI with Pydantic models</Share>", "passed": False, "latency_ms": 1200, "round": 1},
        },
        {"type": "round_ended", "ts": "t4", "session_id": "s1", "data": {"round": 1, "all_passed": False}},
        {"type": "round_started", "ts": "t5", "session_id": "s1", "data": {"round": 2, "agents": ["claude", "codex"]}},
        {
            "type": "agent_completed", "ts": "t6", "session_id": "s1",
            "data": {"agent": "claude", "text": "[PASS]", "passed": True, "latency_ms": 300, "round": 2},
        },
        {
            "type": "agent_completed", "ts": "t7", "session_id": "s1",
            "data": {"agent": "codex", "text": "[PASS]", "passed": True, "latency_ms": 250, "round": 2},
        },
        {"type": "round_ended", "ts": "t8", "session_id": "s1", "data": {"round": 2, "all_passed": True}},
        {"type": "discussion_ended", "ts": "t9", "session_id": "s1", "data": {"reason": "all_passed", "rounds": 2}},
    ]


def test_finalize_creates_episode(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    events = [
        {"type": "user_message", "ts": "t0", "session_id": "s1", "data": {"text": "Build a REST API"}},
        {"type": "round_started", "ts": "t1", "session_id": "s1", "data": {"round": 1, "agents": ["claude", "codex"]}},
        {"type": "agent_completed", "ts": "t2", "session_id": "s1", "data": {"agent": "claude", "text": "Use FastAPI", "passed": False, "latency_ms": 1500, "round": 1}},
        {"type": "agent_completed", "ts": "t3", "session_id": "s1", "data": {"agent": "codex", "text": "+1 Claude", "passed": False, "latency_ms": 1200, "round": 1}},
        {"type": "round_ended", "ts": "t4", "session_id": "s1", "data": {"round": 1, "all_passed": False}},
        {"type": "discussion_ended", "ts": "t5", "session_id": "s1", "data": {"reason": "all_passed", "rounds": 2}},
    ]
    _write_transcript(tmp_path, "s1", events)
    ep_id = mgr.finalize_session("s1")
    assert ep_id is not None
    ep = mgr.store.get_episode(ep_id)
    assert ep["session_id"] == "s1"
    assert ep["rounds"] == 2
    assert "claude" in ep["agents"]
    assert "codex" in ep["agents"]


def test_finalize_no_transcript(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    assert mgr.finalize_session("nonexistent") is None


def test_finalize_idempotent(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    events = [
        {"type": "user_message", "ts": "t0", "session_id": "s1", "data": {"text": "Hello"}},
        {"type": "discussion_ended", "ts": "t1", "session_id": "s1", "data": {"reason": "all_passed", "rounds": 1}},
    ]
    _write_transcript(tmp_path, "s1", events)
    ep1 = mgr.finalize_session("s1")
    ep2 = mgr.finalize_session("s1")
    assert ep1 is not None
    assert ep2 is None


def test_get_pending_transcripts(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    events = [{"type": "user_message", "ts": "t0", "session_id": "s1", "data": {"text": "Hi"}}]
    _write_transcript(tmp_path, "s1", events)
    _write_transcript(tmp_path, "s2", events)
    mgr.finalize_session("s1")
    pending = mgr.get_pending_transcripts()
    assert len(pending) == 1
    assert pending[0].stem == "s2"


# --- parse_transcript ---


def test_parse_transcript(tmp_path):
    events = _rich_transcript_events()
    stats = MemoryManager._parse_transcript(events)

    assert stats["query"] == "Build a REST API"
    assert stats["rounds"] == 2
    assert stats["converged"] is True
    assert "claude" in stats["agents"]
    assert "codex" in stats["agents"]

    claude = stats["per_agent"]["claude"]
    assert claude["active_rounds"] == 1
    assert claude["pass_rounds"] == 1
    assert claude["total_latency_ms"] == 1800.0  # 1500 + 300
    assert claude["latency_samples"] == 2
    assert claude["mentions"] >= 0  # mentions of other agents

    codex = stats["per_agent"]["codex"]
    assert codex["active_rounds"] == 1
    assert codex["pass_rounds"] == 1
    assert codex["agreements"] >= 1  # "+1" detected
    assert codex["used_share_tags"] is True


# --- finalize populates agent_profiles ---


def test_finalize_populates_agent_profiles(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    _write_transcript(tmp_path, "s1", _rich_transcript_events())

    ep_id = mgr.finalize_session("s1")
    assert ep_id is not None

    # Agent profiles should exist
    profiles = mgr.store.get_agent_profiles()
    assert len(profiles) == 2
    names = {p["agent_name"] for p in profiles}
    assert names == {"claude", "codex"}

    for p in profiles:
        assert p["total_sessions"] == 1
        assert p["best_role"] != ""


# --- finalize populates ensemble_patterns ---


def test_finalize_populates_ensemble_patterns(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    _write_transcript(tmp_path, "s1", _rich_transcript_events())

    mgr.finalize_session("s1")

    patterns = mgr.store.get_ensemble_patterns(category="combo")
    assert len(patterns) == 1
    assert "Claude" in patterns[0]["key"]
    assert "Codex" in patterns[0]["key"]
    val = patterns[0]["value"]
    assert val["sessions"] == 1
    assert val["convergence_rate"] == 1.0


# --- LLM extraction with mocked Anthropic ---


def _make_claude_cli_output(learnings: dict) -> str:
    """Build fake claude CLI stream-json output containing a result object."""
    result_obj = {"type": "result", "result": json.dumps(learnings)}
    return json.dumps(result_obj) + "\n"


def test_extract_learnings_cli_mocked(tmp_path):
    """Test LLM extraction path with mocked claude CLI subprocess."""
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)

    learnings = {
        "per_agent": {
            "claude": {
                "strengths": ["excellent coordinator"],
                "weaknesses": [],
                "notable_behaviors": ["proactive question asker"],
                "role_effectiveness": {"coordinator": 0.9, "implementer": 0.3, "reviewer": 0.2},
            },
            "codex": {
                "strengths": ["fast and precise"],
                "weaknesses": [],
                "notable_behaviors": ["good share tag usage"],
                "role_effectiveness": {"coordinator": 0.2, "implementer": 0.8, "reviewer": 0.5},
            },
        },
        "session_learnings": ["Good coordination between agents"],
        "tags": ["converged", "good-coordination"],
    }

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = _make_claude_cli_output(learnings)
    fake_result.stderr = ""

    events = _rich_transcript_events()
    _write_transcript(tmp_path, "s1", events)

    with patch("src.memory.manager.shutil.which", return_value="/usr/bin/claude"):
        with patch("src.memory.manager.subprocess.run", return_value=fake_result):
            ep_id = mgr.finalize_session("s1")

    assert ep_id is not None
    ep = mgr.store.get_episode(ep_id)
    assert "converged" in ep["tags"]
    assert "good-coordination" in ep["tags"]

    profiles = mgr.store.get_agent_profiles()
    claude_profile = next(p for p in profiles if p["agent_name"] == "claude")
    assert "excellent coordinator" in claude_profile["strengths"]
    assert claude_profile["best_role"] == "coordinator"


def test_extract_learnings_cli_fallback_on_error(tmp_path):
    """When claude CLI fails, heuristic fallback should still work."""
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)

    events = _rich_transcript_events()
    _write_transcript(tmp_path, "s1", events)

    with patch("src.memory.manager.shutil.which", return_value="/usr/bin/claude"):
        with patch("src.memory.manager.subprocess.run", side_effect=Exception("CLI crashed")):
            ep_id = mgr.finalize_session("s1")

    assert ep_id is not None
    # Should still have profiles from heuristic fallback
    profiles = mgr.store.get_agent_profiles()
    assert len(profiles) == 2


def test_extract_learnings_no_cli_uses_heuristic(tmp_path):
    """When claude CLI is not in PATH, heuristic is used directly."""
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)

    events = _rich_transcript_events()
    _write_transcript(tmp_path, "s1", events)

    with patch("src.memory.manager.shutil.which", return_value=None):
        ep_id = mgr.finalize_session("s1")

    assert ep_id is not None
    profiles = mgr.store.get_agent_profiles()
    assert len(profiles) == 2
    # Heuristic tags for converged + 2 rounds
    ep = mgr.store.get_episode(ep_id)
    assert "converged" in ep["tags"]
    assert "quick-resolution" in ep["tags"]
