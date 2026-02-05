import json
import sqlite3

from src.memory.store import MemoryStore


def test_creates_db_and_tables(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)
    db_path = tmp_path / ".multiagents" / "memory.db"
    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','trigger')"
    ).fetchall()}
    conn.close()
    assert "episodes" in tables
    assert "agent_episodes" in tables
    assert "agent_profiles" in tables
    assert "ensemble_patterns" in tables
    assert "episodes_fts" in tables


def test_save_and_get_episode(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)
    ep_id = store.save_episode(
        session_id="sess-1",
        query="Build a REST API",
        summary="Team chose FastAPI",
        rounds=3,
        agents=["claude", "codex"],
    )
    ep = store.get_episode(ep_id)
    assert ep["session_id"] == "sess-1"
    assert ep["query"] == "Build a REST API"
    assert ep["summary"] == "Team chose FastAPI"
    assert ep["rounds"] == 3
    assert ep["agents"] == ["claude", "codex"]


def test_get_episode_not_found(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)
    assert store.get_episode("nonexistent") is None


def test_episode_exists(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)
    ep_id = store.save_episode(session_id="sess-1", query="hello", summary="hi")
    assert store.episode_exists_for_session("sess-1") is True
    assert store.episode_exists_for_session("sess-999") is False


def test_search_episodes(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)
    store.save_episode(session_id="s1", query="REST API design", summary="Chose FastAPI")
    store.save_episode(session_id="s2", query="Database schema", summary="Use PostgreSQL")
    store.save_episode(session_id="s3", query="Auth flow", summary="OAuth with JWT")

    results = store.search_episodes("API")
    assert len(results) == 1
    assert results[0]["session_id"] == "s1"


def test_search_empty_results(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)
    store.save_episode(session_id="s1", query="API", summary="FastAPI")
    assert store.search_episodes("kubernetes") == []


def test_search_respects_limit(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)
    for i in range(10):
        store.save_episode(session_id=f"s{i}", query=f"API version {i}", summary="API discussion")
    assert len(store.search_episodes("API", limit=3)) == 3


def test_list_episodes(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)
    id1 = store.save_episode(session_id="s1", summary="First")
    id2 = store.save_episode(session_id="s2", summary="Second")
    results = store.list_episodes(limit=2)
    assert len(results) == 2
    assert results[0]["id"] == id2  # newest first


def test_list_episodes_empty(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)
    assert store.list_episodes() == []


# -- agent_episodes CRUD --


def test_save_agent_episode_with_stats(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)
    ep_id = store.save_episode(session_id="s1", query="test", summary="test")

    store.save_agent_episode(
        episode_id=ep_id,
        agent_name="claude",
        response_time_ms=1500,
        agreed_with_consensus=True,
        unique_contributions=["Used FastAPI pattern", "Suggested middleware"],
    )
    rows = store.get_agent_episodes("claude")
    assert len(rows) == 1
    assert rows[0]["episode_id"] == ep_id
    assert rows[0]["response_time_ms"] == 1500
    assert rows[0]["agreed_with_consensus"] is True
    assert rows[0]["unique_contributions"] == ["Used FastAPI pattern", "Suggested middleware"]


def test_save_agent_episode_replaces_on_conflict(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)
    ep_id = store.save_episode(session_id="s1", query="test", summary="test")

    store.save_agent_episode(episode_id=ep_id, agent_name="claude", response_time_ms=1000)
    store.save_agent_episode(episode_id=ep_id, agent_name="claude", response_time_ms=2000)

    rows = store.get_agent_episodes("claude")
    assert len(rows) == 1
    assert rows[0]["response_time_ms"] == 2000


# -- agent_profiles CRUD --


def test_update_agent_profile(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)

    store.update_agent_profile(
        agent_name="claude",
        strengths=["strong coordinator", "active communicator"],
        weaknesses=["slow responses"],
        notable_behaviors=["uses Share tags"],
        avg_response_time_ms=12500.0,
        consensus_agreement_rate=0.8,
        role_scores={"coordinator": 0.9, "implementer": 0.3},
        best_role="coordinator",
        total_sessions=5,
    )

    profiles = store.get_agent_profiles(["claude"])
    assert len(profiles) == 1
    p = profiles[0]
    assert p["agent_name"] == "claude"
    assert p["strengths"] == ["strong coordinator", "active communicator"]
    assert p["weaknesses"] == ["slow responses"]
    assert p["avg_response_time_ms"] == 12500.0
    assert p["best_role"] == "coordinator"
    assert p["total_sessions"] == 5
    assert p["role_scores"]["coordinator"] == 0.9


def test_get_agent_profiles_all(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)

    store.update_agent_profile(agent_name="claude", best_role="coordinator", total_sessions=3)
    store.update_agent_profile(agent_name="codex", best_role="implementer", total_sessions=2)

    profiles = store.get_agent_profiles()
    assert len(profiles) == 2
    names = [p["agent_name"] for p in profiles]
    assert "claude" in names
    assert "codex" in names


def test_get_agent_profiles_filtered(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)

    store.update_agent_profile(agent_name="claude", total_sessions=3)
    store.update_agent_profile(agent_name="codex", total_sessions=2)
    store.update_agent_profile(agent_name="kimi", total_sessions=1)

    profiles = store.get_agent_profiles(["claude", "kimi"])
    assert len(profiles) == 2
    names = {p["agent_name"] for p in profiles}
    assert names == {"claude", "kimi"}


# -- ensemble_patterns CRUD --


def test_save_and_get_ensemble_pattern(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)

    store.save_ensemble_pattern(
        "Claude + Codex",
        "combo",
        {"sessions": 5, "convergence_rate": 0.8, "avg_rounds": 3.2},
    )
    patterns = store.get_ensemble_patterns(category="combo")
    assert len(patterns) == 1
    assert patterns[0]["key"] == "Claude + Codex"
    assert patterns[0]["category"] == "combo"
    assert patterns[0]["value"]["sessions"] == 5
    assert patterns[0]["value"]["convergence_rate"] == 0.8


def test_ensemble_pattern_upsert(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)

    store.save_ensemble_pattern("Claude + Codex", "combo", {"sessions": 1})
    store.save_ensemble_pattern("Claude + Codex", "combo", {"sessions": 2})

    patterns = store.get_ensemble_patterns(category="combo")
    assert len(patterns) == 1
    assert patterns[0]["value"]["sessions"] == 2


def test_get_ensemble_patterns_all_categories(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    store = MemoryStore(tmp_path)

    store.save_ensemble_pattern("Claude + Codex", "combo", {"sessions": 3})
    store.save_ensemble_pattern("best-pair", "ranking", "Claude + Codex")

    all_patterns = store.get_ensemble_patterns()
    assert len(all_patterns) == 2

    combo_only = store.get_ensemble_patterns(category="combo")
    assert len(combo_only) == 1
    assert combo_only[0]["key"] == "Claude + Codex"
