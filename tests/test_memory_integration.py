import json
from pathlib import Path

from src.memory.recorder import SessionRecorder
from src.memory.manager import MemoryManager


def test_full_pipeline(tmp_path):
    """Record a session, finalize it, search for the episode."""
    (tmp_path / ".multiagents").mkdir()
    with SessionRecorder(tmp_path, "pipe-1") as rec:
        rec.record_user_message("How should we handle authentication?")
        rec.record_round_started(1, ["claude", "codex"])
        rec.record_agent_completed("claude", "Use OAuth 2.0 with JWT", False, 2000.0, 1)
        rec.record_agent_completed("codex", "+1 OAuth", False, 1500.0, 1)
        rec.record_round_ended(1, False)
        rec.record_round_started(2, ["claude", "codex"])
        rec.record_agent_completed("claude", "[PASS]", True, 300.0, 2)
        rec.record_agent_completed("codex", "[PASS]", True, 250.0, 2)
        rec.record_round_ended(2, True)
        rec.record_discussion_ended("all_passed", 2)

    mgr = MemoryManager(tmp_path)
    ep_id = mgr.finalize_session("pipe-1")
    assert ep_id is not None
    results = mgr.store.search_episodes("authentication")
    assert len(results) >= 1

    ctx = mgr.build_memory_context("authentication flow")
    assert "OAuth" in ctx or "authentication" in ctx


def test_pending_transcript_recovery(tmp_path):
    """Simulate crash recovery: unfinalized transcripts get picked up."""
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    d = tmp_path / ".multiagents" / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    for sid in ["crash-1", "crash-2"]:
        with open(d / f"{sid}.jsonl", "w") as f:
            f.write(json.dumps({"type": "user_message", "ts": "t", "session_id": sid, "data": {"text": "hi"}}) + "\n")

    pending = mgr.get_pending_transcripts()
    assert len(pending) == 2

    for p in pending:
        mgr.finalize_session(p.stem)

    assert mgr.get_pending_transcripts() == []


def test_memory_context_in_extra_context(tmp_path):
    """Verify MemoryManager.build_memory_context output is valid extra_context format."""
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    mgr.store.save_episode(
        session_id="s1",
        query="API design",
        summary="Chose FastAPI",
        rounds=2,
        agents=["claude"],
    )
    ctx = mgr.build_memory_context("API framework")
    assert isinstance(ctx, str)
    assert len(ctx) > 0
    from src.chat.router import format_prompt

    prompt = format_prompt(
        [{"role": "user", "content": "Build API"}],
        "claude",
        current_round=1,
        extra_context={"memory": ctx},
    )
    assert "Agent Knowledge" in prompt
    assert "Relevant Past Discussions" in prompt


def test_recover_pending_on_startup(tmp_path):
    """Simulate startup recovery: finalize all pending transcripts."""
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)
    d = tmp_path / ".multiagents" / "transcripts"
    d.mkdir(parents=True, exist_ok=True)

    for sid in ["r1", "r2"]:
        with open(d / f"{sid}.jsonl", "w") as f:
            f.write(json.dumps({"type": "user_message", "ts": "t", "session_id": sid, "data": {"text": "query"}}) + "\n")
            f.write(json.dumps({"type": "discussion_ended", "ts": "t", "session_id": sid, "data": {"reason": "all_passed", "rounds": 1}}) + "\n")

    for p in mgr.get_pending_transcripts():
        mgr.finalize_session(p.stem)

    assert len(mgr.get_pending_transcripts()) == 0
    assert len(mgr.store.list_episodes()) == 2


def test_multi_session_profile_accumulation(tmp_path):
    """Two sessions with the same agents — verify profiles aggregate."""
    (tmp_path / ".multiagents").mkdir()
    mgr = MemoryManager(tmp_path)

    # Session 1: claude is fast, codex agrees
    d = tmp_path / ".multiagents" / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    events1 = [
        {"type": "user_message", "ts": "t0", "session_id": "s1", "data": {"text": "Design API"}},
        {"type": "agent_completed", "ts": "t1", "session_id": "s1", "data": {"agent": "claude", "text": "Use REST", "passed": False, "latency_ms": 1000, "round": 1}},
        {"type": "agent_completed", "ts": "t2", "session_id": "s1", "data": {"agent": "codex", "text": "+1 agree", "passed": False, "latency_ms": 800, "round": 1}},
        {"type": "discussion_ended", "ts": "t3", "session_id": "s1", "data": {"reason": "all_passed", "rounds": 2}},
    ]
    with open(d / "s1.jsonl", "w") as f:
        for ev in events1:
            f.write(json.dumps(ev) + "\n")

    mgr.finalize_session("s1")

    # Session 2: same agents, different discussion
    events2 = [
        {"type": "user_message", "ts": "t0", "session_id": "s2", "data": {"text": "Database choice"}},
        {"type": "agent_completed", "ts": "t1", "session_id": "s2", "data": {"agent": "claude", "text": "Use PostgreSQL", "passed": False, "latency_ms": 2000, "round": 1}},
        {"type": "agent_completed", "ts": "t2", "session_id": "s2", "data": {"agent": "codex", "text": "+1 good choice", "passed": False, "latency_ms": 1500, "round": 1}},
        {"type": "discussion_ended", "ts": "t3", "session_id": "s2", "data": {"reason": "all_passed", "rounds": 3}},
    ]
    with open(d / "s2.jsonl", "w") as f:
        for ev in events2:
            f.write(json.dumps(ev) + "\n")

    mgr.finalize_session("s2")

    # Verify profiles aggregated
    profiles = mgr.store.get_agent_profiles()
    assert len(profiles) == 2

    claude = next(p for p in profiles if p["agent_name"] == "claude")
    assert claude["total_sessions"] == 2
    # Running average: (1000 + 2000) / 2 = 1500
    assert abs(claude["avg_response_time_ms"] - 1500.0) < 1.0

    codex = next(p for p in profiles if p["agent_name"] == "codex")
    assert codex["total_sessions"] == 2

    # Ensemble patterns should have 2 sessions
    patterns = mgr.store.get_ensemble_patterns(category="combo")
    assert len(patterns) == 1
    assert patterns[0]["value"]["sessions"] == 2


def test_full_pipeline_with_profiles(tmp_path):
    """Record -> finalize -> verify profiles -> verify context output."""
    (tmp_path / ".multiagents").mkdir()

    with SessionRecorder(tmp_path, "fp-1") as rec:
        rec.record_user_message("Build a web scraper")
        rec.record_round_started(1, ["claude", "codex"])
        rec.record_agent_completed("claude", "Use BeautifulSoup with @codex reviewing", False, 3000.0, 1)
        rec.record_agent_completed("codex", "+1 agree, also consider <Share>Use aiohttp for async requests</Share>", False, 2000.0, 1)
        rec.record_round_ended(1, False)
        rec.record_round_started(2, ["claude", "codex"])
        rec.record_agent_completed("claude", "[PASS]", True, 200.0, 2)
        rec.record_agent_completed("codex", "[PASS]", True, 150.0, 2)
        rec.record_round_ended(2, True)
        rec.record_discussion_ended("all_passed", 2)

    mgr = MemoryManager(tmp_path)
    ep_id = mgr.finalize_session("fp-1")
    assert ep_id is not None

    # Verify profiles were populated
    profiles = mgr.store.get_agent_profiles()
    assert len(profiles) == 2
    for p in profiles:
        assert p["total_sessions"] == 1
        assert p["best_role"] != ""

    # Verify ensemble patterns
    patterns = mgr.store.get_ensemble_patterns(category="combo")
    assert len(patterns) == 1

    # Verify context includes all sections
    ctx = mgr.build_memory_context("web scraper")
    assert "## Agent Knowledge" in ctx
    assert "### Agent Capabilities" in ctx
    assert "### Collaboration Notes" in ctx
    assert "### Relevant Past Discussions" in ctx
