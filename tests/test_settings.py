import json
import pytest
from pathlib import Path
from src.server.settings import SettingsStore, DEFAULTS


def test_get_returns_default_when_empty(tmp_path):
    store = SettingsStore(tmp_path / "test.db")
    assert store.get("timeouts.idle") == 1800


def test_set_and_get(tmp_path):
    store = SettingsStore(tmp_path / "test.db")
    store.set("timeouts.idle", 3600)
    assert store.get("timeouts.idle") == 3600


def test_delete_reverts_to_default(tmp_path):
    store = SettingsStore(tmp_path / "test.db")
    store.set("timeouts.idle", 3600)
    store.delete("timeouts.idle")
    assert store.get("timeouts.idle") == 1800


def test_get_all_returns_defaults_merged(tmp_path):
    store = SettingsStore(tmp_path / "test.db")
    store.set("agents.claude.model", "opus")
    all_settings = store.get_all()
    assert all_settings["agents.claude.model"] == "opus"
    assert all_settings["timeouts.idle"] == 1800


def test_set_many(tmp_path):
    store = SettingsStore(tmp_path / "test.db")
    store.set_many({"timeouts.idle": 900, "timeouts.parse": 60})
    assert store.get("timeouts.idle") == 900
    assert store.get("timeouts.parse") == 60


def test_get_effective_with_session_override(tmp_path):
    store = SettingsStore(tmp_path / "test.db")
    store.set("timeouts.idle", 3600)
    effective = store.get_effective(
        session_config={"timeouts.idle": 900}
    )
    assert effective["timeouts.idle"] == 900
    assert effective["timeouts.parse"] == 120  # from defaults


def test_get_effective_with_cli_overrides(tmp_path):
    store = SettingsStore(tmp_path / "test.db")
    store.set("timeouts.idle", 3600)
    effective = store.get_effective(
        cli_overrides={"timeouts.idle": 1800}
    )
    assert effective["timeouts.idle"] == 1800  # CLI wins


def test_unknown_key_returns_none(tmp_path):
    store = SettingsStore(tmp_path / "test.db")
    assert store.get("nonexistent.key") is None


def test_custom_default(tmp_path):
    store = SettingsStore(tmp_path / "test.db")
    assert store.get("nonexistent.key", default="fallback") == "fallback"


from src.server.sessions import SessionStore


def test_session_config_column(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    session = store.create_session(
        agent_names=[{"name": "claude", "type": "claude", "role": ""}],
        config={"agents.claude.model": "opus"},
    )
    loaded = store.get_session(session["id"])
    assert loaded["config"] == {"agents.claude.model": "opus"}


def test_session_config_defaults_empty(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    session = store.create_session(
        agent_names=[{"name": "claude", "type": "claude", "role": ""}],
    )
    loaded = store.get_session(session["id"])
    assert loaded["config"] == {}


from src.agents import create_agents


def test_claude_agent_model_in_args():
    agents = create_agents(
        [{"name": "claude", "type": "claude", "role": "", "model": "opus"}]
    )
    agent = agents[0]
    args = agent._build_args("hello")
    assert "--model" in args
    idx = args.index("--model")
    assert args[idx + 1] == "opus"


def test_claude_agent_no_model_flag_when_none():
    agents = create_agents(
        [{"name": "claude", "type": "claude", "role": ""}]
    )
    agent = agents[0]
    args = agent._build_args("hello")
    assert "--model" not in args


def test_codex_agent_model_in_args():
    agents = create_agents(
        [{"name": "codex", "type": "codex", "role": "", "model": "o3"}]
    )
    agent = agents[0]
    args = agent._build_args("hello")
    assert any("model=" in a for a in args)


def test_system_prompt_override_in_agent():
    agents = create_agents(
        [{"name": "claude", "type": "claude", "role": ""}]
    )
    agent = agents[0]
    agent.system_prompt_override = "You are a pirate."
    from src.agents.prompts import build_agent_system_prompt
    prompt = build_agent_system_prompt(".", base_prompt="You are a pirate.")
    assert "pirate" in prompt


def test_get_effective_merge_order(tmp_path):
    """Verify: defaults < global < session < CLI."""
    store = SettingsStore(tmp_path / "test.db")
    store.set("timeouts.idle", 3600)          # global override
    effective = store.get_effective(
        session_config={"timeouts.idle": 900},   # session override
        cli_overrides={"timeouts.idle": 100},     # CLI override
    )
    assert effective["timeouts.idle"] == 100  # CLI wins over all


def test_memory_model_setting(tmp_path):
    store = SettingsStore(tmp_path / "test.db")
    store.set("memory.model", "sonnet")
    assert store.get("memory.model") == "sonnet"
    effective = store.get_effective()
    assert effective["memory.model"] == "sonnet"


def test_timeout_config_applied_to_agents():
    agents = create_agents([{"name": "claude", "type": "claude", "role": ""}])
    from src.server.runner import SessionRunner
    config = {"timeouts.parse": 60.0, "timeouts.hard": 300.0}
    SessionRunner._apply_config_to_agents(None, agents, config)
    assert agents[0].parse_timeout == 60.0
    assert agents[0].hard_timeout == 300.0


def test_send_timeout_config_applied_to_session(tmp_path):
    from src.server.sessions import SessionStore
    from src.server.runner import SessionRunner
    store = SessionStore(tmp_path / "test.db")
    runner = SessionRunner(store, send_timeout=120.0)
    runner._apply_config_to_session("sid", {"timeouts.send": 45})
    assert runner._session_send_timeouts["sid"] == 45.0
    runner._apply_config_to_session("sid", {"timeouts.send": 0})
    assert "sid" not in runner._session_send_timeouts
