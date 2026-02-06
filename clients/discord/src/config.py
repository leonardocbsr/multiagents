from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    discord_token: str
    allowlist: set[int]
    server_url: str
    default_agents: list[str]
    inactivity_timeout: int

    @classmethod
    def from_env(cls) -> Config:
        token = os.environ.get("DISCORD_TOKEN", "").strip()
        if not token:
            raise ValueError("DISCORD_TOKEN environment variable is required")

        raw_allowlist = os.environ.get("DISCORD_ALLOWLIST", "").strip()
        if not raw_allowlist:
            raise ValueError("DISCORD_ALLOWLIST environment variable is required")

        allowlist = {int(uid.strip()) for uid in raw_allowlist.split(",") if uid.strip()}

        server_url = os.environ.get("SERVER_URL", "ws://localhost:8421/ws").strip()
        agents_str = os.environ.get("DEFAULT_AGENTS", "claude,codex,kimi").strip()
        default_agents = [a.strip() for a in agents_str.split(",") if a.strip()]
        raw_timeout = os.environ.get("INACTIVITY_TIMEOUT", "1800").strip()
        try:
            inactivity_timeout = int(raw_timeout)
        except ValueError as exc:
            raise ValueError("INACTIVITY_TIMEOUT must be an integer number of seconds") from exc
        if inactivity_timeout <= 0:
            raise ValueError("INACTIVITY_TIMEOUT must be greater than 0")

        return cls(
            discord_token=token,
            allowlist=allowlist,
            server_url=server_url,
            default_agents=default_agents,
            inactivity_timeout=inactivity_timeout,
        )
