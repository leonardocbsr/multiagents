from __future__ import annotations

import os
import pytest


def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("DISCORD_ALLOWLIST", "111,222,333")
    monkeypatch.setenv("SERVER_URL", "ws://example.com/ws")
    monkeypatch.setenv("DEFAULT_AGENTS", "claude,codex")
    monkeypatch.setenv("INACTIVITY_TIMEOUT", "600")

    from src.config import Config

    cfg = Config.from_env()
    assert cfg.discord_token == "test-token"
    assert cfg.allowlist == {111, 222, 333}
    assert cfg.server_url == "ws://example.com/ws"
    assert cfg.default_agents == ["claude", "codex"]
    assert cfg.inactivity_timeout == 600


def test_config_defaults(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "tok")
    monkeypatch.setenv("DISCORD_ALLOWLIST", "111")
    monkeypatch.delenv("SERVER_URL", raising=False)
    monkeypatch.delenv("DEFAULT_AGENTS", raising=False)
    monkeypatch.delenv("INACTIVITY_TIMEOUT", raising=False)

    from src.config import Config

    cfg = Config.from_env()
    assert cfg.server_url == "ws://localhost:8421/ws"
    assert cfg.default_agents == ["claude", "codex", "kimi"]
    assert cfg.inactivity_timeout == 1800


def test_config_missing_token_raises(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("DISCORD_ALLOWLIST", "111")

    from src.config import Config

    with pytest.raises(ValueError, match="DISCORD_TOKEN"):
        Config.from_env()


def test_config_missing_allowlist_raises(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "tok")
    monkeypatch.delenv("DISCORD_ALLOWLIST", raising=False)

    from src.config import Config

    with pytest.raises(ValueError, match="DISCORD_ALLOWLIST"):
        Config.from_env()
