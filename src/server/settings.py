from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_DEFAULT_DB_PATH = Path.home() / ".multiagents" / "multiagents.db"

DEFAULTS: dict[str, Any] = {
    "agents.enabled": ["claude", "codex", "kimi"],
    "agents.claude.model": None,
    "agents.claude.system_prompt": None,
    "agents.codex.model": None,
    "agents.codex.system_prompt": None,
    "agents.kimi.model": None,
    "agents.kimi.system_prompt": None,
    "timeouts.idle": 1800,
    "timeouts.parse": 1200,
    "timeouts.send": 120,
    "timeouts.hard": 0,
    "memory.model": "haiku",
    "server.warmup_ttl": 300,
    "server.max_events": 2000,
    # UI layout feature flags
    "ui.layout.default": "split",  # "split" | "chat"
    "ui.layout.allow_switch": True,
    "ui.layout.split_enabled": True,
    # UI appearance flags
    "ui.theme.mode": "dark",  # "dark" | "light" | "system"
    "ui.theme.accent": "cyan",  # "cyan" | "emerald" | "amber"
    "ui.theme.density": "cozy",  # "compact" | "cozy"
    # Permission mode per agent: "bypass" | "auto" | "manual"
    "agents.claude.permissions": "bypass",
    "agents.codex.permissions": "bypass",
    "agents.kimi.permissions": "bypass",
    # Timeout for pending permission requests (seconds, 0 = no timeout)
    "permissions.timeout": 120,
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SettingsStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def get(self, key: str, default: Any = ...) -> Any:
        with self._lock:
            cur = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            row = cur.fetchone()
        if row is not None:
            return json.loads(row[0])
        if default is not ...:
            return default
        return DEFAULTS.get(key)

    def set(self, key: str, value: Any) -> None:
        encoded = json.dumps(value)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, encoded),
            )
            self._conn.commit()

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            self._conn.commit()

    def get_all(self) -> dict[str, Any]:
        with self._lock:
            cur = self._conn.execute("SELECT key, value FROM settings")
            rows = {row[0]: json.loads(row[1]) for row in cur.fetchall()}
        result = dict(DEFAULTS)
        result.update(rows)
        return result

    def set_many(self, updates: dict[str, Any]) -> None:
        with self._lock:
            for key, value in updates.items():
                self._conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, json.dumps(value)),
                )
            self._conn.commit()

    def get_effective(
        self,
        session_config: dict[str, Any] | None = None,
        cli_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.get_all()
        if session_config:
            result.update(session_config)
        if cli_overrides:
            result.update(cli_overrides)
        return result
