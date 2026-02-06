from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB_PATH = Path.home() / ".multiagents" / "multiagents.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    agent_names TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    is_running  INTEGER NOT NULL DEFAULT 0,
    is_paused   INTEGER NOT NULL DEFAULT 0,
    current_round INTEGER NOT NULL DEFAULT 0,
    last_event_id INTEGER NOT NULL DEFAULT 0,
    last_event_at TEXT NOT NULL DEFAULT '',
    working_dir   TEXT NOT NULL DEFAULT '',
    config        TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role         TEXT NOT NULL,
    content      TEXT NOT NULL,
    round_number INTEGER,
    passed       INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_state (
    session_id     TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    agent_name     TEXT NOT NULL,
    cli_session_id TEXT,
    last_round     INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'idle',
    stream_text    TEXT NOT NULL DEFAULT '',
    updated_at     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (session_id, agent_name)
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);

CREATE TABLE IF NOT EXISTS session_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    event_id    INTEGER NOT NULL,
    type        TEXT NOT NULL,
    data        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_session_events_session_event ON session_events(session_id, event_id);
CREATE INDEX IF NOT EXISTS idx_session_events_session ON session_events(session_id);

CREATE TABLE IF NOT EXISTS cards (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'backlog',
    planner         TEXT NOT NULL DEFAULT '',
    implementer     TEXT NOT NULL DEFAULT '',
    reviewer        TEXT NOT NULL DEFAULT '',
    coordinator     TEXT NOT NULL DEFAULT '',
    coordination_stage TEXT NOT NULL DEFAULT '',
    previous_phase  TEXT,
    history         TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cards_session ON cards(session_id);
"""

_MAX_SESSION_EVENTS = 2000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_agents(raw: str) -> list[dict]:
    """Parse agent_names column, migrating legacy string lists to persona dicts."""
    data = json.loads(raw)
    if not data:
        return []
    if isinstance(data[0], str):
        return [{"name": name, "type": name, "role": "", "model": None} for name in data]
    # Ensure newly required keys exist on older rows.
    normalized: list[dict] = []
    for item in data:
        normalized.append({
            "name": item.get("name", item.get("type", "")),
            "type": item.get("type", ""),
            "role": item.get("role", ""),
            "model": item.get("model"),
        })
    return normalized


class SessionStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Ensure newer columns/tables exist for older databases."""
        with self._lock:
            cur = self._conn.execute("PRAGMA table_info(sessions)")
            session_cols = {row[1] for row in cur.fetchall()}
            if "is_running" not in session_cols:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN is_running INTEGER NOT NULL DEFAULT 0")
            if "current_round" not in session_cols:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN current_round INTEGER NOT NULL DEFAULT 0")
            if "last_event_id" not in session_cols:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN last_event_id INTEGER NOT NULL DEFAULT 0")
            if "is_paused" not in session_cols:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN is_paused INTEGER NOT NULL DEFAULT 0")
            if "last_event_at" not in session_cols:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN last_event_at TEXT NOT NULL DEFAULT ''")
            if "working_dir" not in session_cols:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN working_dir TEXT NOT NULL DEFAULT ''")
            if "config" not in session_cols:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN config TEXT NOT NULL DEFAULT '{}'")

            cur = self._conn.execute("PRAGMA table_info(agent_state)")
            agent_cols = {row[1] for row in cur.fetchall()}
            if "last_round" not in agent_cols:
                self._conn.execute("ALTER TABLE agent_state ADD COLUMN last_round INTEGER NOT NULL DEFAULT 0")
            if "status" not in agent_cols:
                self._conn.execute("ALTER TABLE agent_state ADD COLUMN status TEXT NOT NULL DEFAULT 'idle'")
            if "stream_text" not in agent_cols:
                self._conn.execute("ALTER TABLE agent_state ADD COLUMN stream_text TEXT NOT NULL DEFAULT ''")
            if "updated_at" not in agent_cols:
                self._conn.execute("ALTER TABLE agent_state ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")

            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS session_events ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, "
                "event_id INTEGER NOT NULL, "
                "type TEXT NOT NULL, "
                "data TEXT NOT NULL, "
                "created_at TEXT NOT NULL)"
            )
            self._conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_session_events_session_event "
                "ON session_events(session_id, event_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_events_session "
                "ON session_events(session_id)"
            )

            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS cards ("
                "id TEXT PRIMARY KEY, "
                "session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, "
                "title TEXT NOT NULL, "
                "description TEXT NOT NULL DEFAULT '', "
                "status TEXT NOT NULL DEFAULT 'backlog', "
                "planner TEXT NOT NULL DEFAULT '', "
                "implementer TEXT NOT NULL DEFAULT '', "
                "reviewer TEXT NOT NULL DEFAULT '', "
                "coordinator TEXT NOT NULL DEFAULT '', "
                "coordination_stage TEXT NOT NULL DEFAULT '', "
                "previous_phase TEXT, "
                "history TEXT NOT NULL DEFAULT '[]', "
                "created_at TEXT NOT NULL)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cards_session ON cards(session_id)"
            )
            self._conn.commit()

    def list_sessions(self) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, title, agent_names, updated_at FROM sessions ORDER BY updated_at DESC"
            )
            return [
                {"id": row[0], "title": row[1], "agent_names": _parse_agents(row[2]), "updated_at": row[3]}
                for row in cur.fetchall()
            ]

    def create_session(self, agent_names: list[str] | list[dict], working_dir: str = "", config: dict | None = None) -> dict:
        session_id = uuid.uuid4().hex
        now = _now()
        title = "New Chat"
        config_json = json.dumps(config or {})
        agents_data: list[dict] = []
        for item in agent_names:
            if isinstance(item, str):
                agents_data.append({"name": item, "type": item, "role": "", "model": None})
            else:
                agents_data.append({
                    "name": item.get("name", item.get("type", "")),
                    "type": item.get("type", ""),
                    "role": item.get("role", ""),
                    "model": item.get("model"),
                })
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (id, title, agent_names, created_at, updated_at, working_dir, config) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, title, json.dumps(agents_data), now, now, working_dir, config_json),
            )
            for agent in agents_data:
                self._conn.execute(
                    "INSERT INTO agent_state (session_id, agent_name) VALUES (?, ?)",
                    (session_id, agent["name"]),
                )
            self._conn.commit()
        return {"id": session_id, "title": title, "agent_names": agents_data, "working_dir": working_dir, "config": config or {}}

    def get_session(self, session_id: str) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, title, agent_names, created_at, updated_at, is_running, is_paused, current_round, "
                "last_event_id, last_event_at, working_dir, config FROM sessions WHERE id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            agent_cur = self._conn.execute(
                "SELECT agent_name, cli_session_id FROM agent_state WHERE session_id = ?",
                (session_id,),
            )
            agent_sessions = {r[0]: r[1] for r in agent_cur.fetchall()}
        return {
            "id": row[0], "title": row[1], "agent_names": _parse_agents(row[2]),
            "created_at": row[3], "updated_at": row[4],
            "is_running": bool(row[5]), "is_paused": bool(row[6]),
            "current_round": row[7], "last_event_id": row[8], "last_event_at": row[9],
            "agent_sessions": agent_sessions, "working_dir": row[10],
            "config": json.loads(row[11]) if row[11] else {},
        }

    def update_title(self, session_id: str, title: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, _now(), session_id),
            )
            self._conn.commit()

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        round_number: int | None = None,
        passed: bool = False,
    ) -> dict:
        msg_id = uuid.uuid4().hex
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages (id, session_id, role, content, round_number, passed, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (msg_id, session_id, role, content, round_number, int(passed), now),
            )
            self._conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
            self._conn.commit()
        return {"id": msg_id, "created_at": now}

    def set_running(self, session_id: str, running: bool) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET is_running = ?, updated_at = ? WHERE id = ?",
                (int(running), _now(), session_id),
            )
            self._conn.commit()

    def set_current_round(self, session_id: str, round_number: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET current_round = ?, updated_at = ? WHERE id = ?",
                (round_number, _now(), session_id),
            )
            self._conn.commit()

    def get_session_state(self, session_id: str) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT is_running, is_paused, current_round, last_event_id, last_event_at FROM sessions WHERE id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "is_running": bool(row[0]),
                "is_paused": bool(row[1]),
                "current_round": row[2],
                "last_event_id": row[3],
                "last_event_at": row[4],
            }

    def reset_agent_progress(self, session_id: str, agent_names: list[str], round_number: int) -> None:
        now = _now()
        with self._lock:
            for name in agent_names:
                self._conn.execute(
                    "UPDATE agent_state SET last_round = ?, status = ?, stream_text = ?, updated_at = ? "
                    "WHERE session_id = ? AND agent_name = ?",
                    (round_number, "streaming", "", now, session_id, name),
                )
            self._conn.commit()

    def append_agent_stream(self, session_id: str, agent_name: str, round_number: int, chunk: str) -> None:
        now = _now()
        with self._lock:
            self._conn.execute(
                "UPDATE agent_state SET last_round = ?, status = ?, stream_text = stream_text || ?, updated_at = ? "
                "WHERE session_id = ? AND agent_name = ?",
                (round_number, "streaming", chunk, now, session_id, agent_name),
            )
            self._conn.commit()

    def set_agent_status(self, session_id: str, agent_name: str, status: str, round_number: int) -> None:
        now = _now()
        with self._lock:
            self._conn.execute(
                "UPDATE agent_state SET last_round = ?, status = ?, updated_at = ? "
                "WHERE session_id = ? AND agent_name = ?",
                (round_number, status, now, session_id, agent_name),
            )
            self._conn.commit()

    def get_agent_progress(self, session_id: str) -> dict[str, dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT agent_name, last_round, status, stream_text FROM agent_state WHERE session_id = ?",
                (session_id,),
            )
            return {
                row[0]: {"last_round": row[1], "status": row[2], "stream_text": row[3]}
                for row in cur.fetchall()
            }

    def clear_in_flight(self, session_id: str) -> None:
        now = _now()
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET is_running = 0, is_paused = 0, current_round = 0, updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            self._conn.execute(
                "UPDATE agent_state SET last_round = 0, status = ?, stream_text = ?, updated_at = ? WHERE session_id = ?",
                ("idle", "", now, session_id),
            )
            self._conn.commit()

    def reserve_event_id(self, session_id: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "SELECT last_event_id FROM sessions WHERE id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Unknown session: {session_id}")
            next_id = row[0] + 1
            self._conn.execute(
                "UPDATE sessions SET last_event_id = ? WHERE id = ?",
                (next_id, session_id),
            )
            self._conn.commit()
            return next_id

    def save_event(self, session_id: str, event_id: int, data: dict) -> None:
        now = _now()
        payload = json.dumps(data)
        event_type = data.get("type", "unknown")
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO session_events (session_id, event_id, type, data, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, event_id, event_type, payload, now),
            )
            self._conn.execute(
                "UPDATE sessions SET last_event_at = ?, updated_at = ? WHERE id = ?",
                (now, now, session_id),
            )
            self._conn.execute(
                "DELETE FROM session_events WHERE session_id = ? AND event_id NOT IN ("
                "SELECT event_id FROM session_events WHERE session_id = ? ORDER BY event_id DESC LIMIT ?"
                ")",
                (session_id, session_id, _MAX_SESSION_EVENTS),
            )
            self._conn.commit()

    def get_events_since(self, session_id: str, after_event_id: int, limit: int = 500) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT data FROM session_events WHERE session_id = ? AND event_id > ? "
                "ORDER BY event_id ASC LIMIT ?",
                (session_id, after_event_id, limit),
            )
            rows = cur.fetchall()
        events = []
        for (payload,) in rows:
            try:
                events.append(json.loads(payload))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return events

    def prune_events(self, session_id: str, up_to_event_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM session_events WHERE session_id = ? AND event_id <= ?",
                (session_id, up_to_event_id),
            )
            self._conn.commit()

    def clear_events(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM session_events WHERE session_id = ?",
                (session_id,),
            )
            self._conn.commit()

    def get_status(self, session_id: str) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT is_running, is_paused, current_round, last_event_at FROM sessions WHERE id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "is_running": bool(row[0]),
                "is_paused": bool(row[1]),
                "current_round": row[2],
                "last_event_time": row[3],
            }

    def get_messages(self, session_id: str) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, role, content, round_number, passed, created_at FROM messages WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            )
            return [
                {"id": row[0], "role": row[1], "content": row[2], "round_number": row[3], "passed": bool(row[4]), "created_at": row[5]}
                for row in cur.fetchall()
            ]

    def save_agent_session_id(self, session_id: str, agent_name: str, cli_session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE agent_state SET cli_session_id = ? WHERE session_id = ? AND agent_name = ?",
                (cli_session_id, session_id, agent_name),
            )
            self._conn.commit()

    def get_agent_session_ids(self, session_id: str) -> dict[str, str | None]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT agent_name, cli_session_id FROM agent_state WHERE session_id = ?",
                (session_id,),
            )
            return {row[0]: row[1] for row in cur.fetchall()}

    def update_agents(self, session_id: str, agents: list[dict]) -> None:
        """Update the agent list for a session."""
        now = _now()
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET agent_names = ?, updated_at = ? WHERE id = ?",
                (json.dumps(agents), now, session_id),
            )
            self._conn.commit()

    def add_agent_state(self, session_id: str, agent_name: str) -> None:
        """Add agent_state row for a newly added agent."""
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO agent_state (session_id, agent_name) VALUES (?, ?)",
                (session_id, agent_name),
            )
            self._conn.commit()

    def remove_agent_state(self, session_id: str, agent_name: str) -> None:
        """Remove agent_state row for a removed agent."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM agent_state WHERE session_id = ? AND agent_name = ?",
                (session_id, agent_name),
            )
            self._conn.commit()

    # -- Card persistence ---------------------------------------------------

    def save_card(self, session_id: str, card_dict: dict) -> None:
        """Upsert a full card state."""
        history = json.dumps(card_dict.get("history", []))
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cards "
                "(id, session_id, title, description, status, planner, implementer, reviewer, "
                "coordinator, coordination_stage, previous_phase, history, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    card_dict["id"],
                    session_id,
                    card_dict.get("title", ""),
                    card_dict.get("description", ""),
                    card_dict.get("status", "backlog"),
                    card_dict.get("planner", ""),
                    card_dict.get("implementer", ""),
                    card_dict.get("reviewer", ""),
                    card_dict.get("coordinator", ""),
                    card_dict.get("coordination_stage", ""),
                    card_dict.get("previous_phase"),
                    history,
                    card_dict.get("created_at", _now()),
                ),
            )
            self._conn.commit()

    def get_cards(self, session_id: str) -> list[dict]:
        """Load all cards for a session."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, title, description, status, planner, implementer, reviewer, "
                "coordinator, coordination_stage, previous_phase, history, created_at "
                "FROM cards WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            )
            rows = cur.fetchall()
        results = []
        for row in rows:
            try:
                history = json.loads(row[10])
            except (json.JSONDecodeError, TypeError):
                history = []
            results.append({
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "status": row[3],
                "planner": row[4],
                "implementer": row[5],
                "reviewer": row[6],
                "coordinator": row[7],
                "coordination_stage": row[8],
                "previous_phase": row[9],
                "history": history,
                "created_at": row[11],
            })
        return results

    def delete_card(self, session_id: str, card_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM cards WHERE id = ? AND session_id = ?",
                (card_id, session_id),
            )
            self._conn.commit()

    def delete_session(self, session_id: str) -> None:
        """Delete a session and all related data (cascades via FK)."""
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._conn.commit()
