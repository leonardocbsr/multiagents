from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    query       TEXT NOT NULL DEFAULT '',
    summary     TEXT NOT NULL DEFAULT '',
    rounds      INTEGER NOT NULL DEFAULT 0,
    converged   INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    agents      TEXT NOT NULL DEFAULT '[]',
    tags        TEXT NOT NULL DEFAULT '[]',
    transcript_path TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_episodes (
    episode_id           TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    agent_name           TEXT NOT NULL,
    response_time_ms     INTEGER NOT NULL DEFAULT 0,
    agreed_with_consensus INTEGER NOT NULL DEFAULT 0,
    unique_contributions TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (episode_id, agent_name)
);

CREATE TABLE IF NOT EXISTS agent_profiles (
    agent_name               TEXT PRIMARY KEY,
    strengths                TEXT NOT NULL DEFAULT '[]',
    weaknesses               TEXT NOT NULL DEFAULT '[]',
    notable_behaviors        TEXT NOT NULL DEFAULT '[]',
    avg_response_time_ms     REAL NOT NULL DEFAULT 0,
    consensus_agreement_rate REAL NOT NULL DEFAULT 0,
    unique_contribution_rate REAL NOT NULL DEFAULT 0,
    role_scores              TEXT NOT NULL DEFAULT '{}',
    best_role                TEXT NOT NULL DEFAULT '',
    total_sessions           INTEGER NOT NULL DEFAULT 0,
    updated_at               TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ensemble_patterns (
    key        TEXT PRIMARY KEY,
    category   TEXT NOT NULL,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
    query, summary, tags,
    content='episodes', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS episodes_ai AFTER INSERT ON episodes BEGIN
    INSERT INTO episodes_fts(rowid, query, summary, tags)
    VALUES (new.rowid, new.query, new.summary, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS episodes_ad AFTER DELETE ON episodes BEGIN
    INSERT INTO episodes_fts(episodes_fts, rowid, query, summary, tags)
    VALUES ('delete', old.rowid, old.query, old.summary, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS episodes_au AFTER UPDATE ON episodes BEGIN
    INSERT INTO episodes_fts(episodes_fts, rowid, query, summary, tags)
    VALUES ('delete', old.rowid, old.query, old.summary, old.tags);
    INSERT INTO episodes_fts(rowid, query, summary, tags)
    VALUES (new.rowid, new.query, new.summary, new.tags);
END;

CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id);
CREATE INDEX IF NOT EXISTS idx_episodes_created ON episodes(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_episodes_agent ON agent_episodes(agent_name);
"""


_FTS_STRIP = re.compile(r"[^\w\s]", re.UNICODE)


def _sanitize_fts_query(query: str) -> str:
    """Strip FTS5 special characters and quote each term for safe matching."""
    cleaned = _FTS_STRIP.sub(" ", query)
    terms = cleaned.split()
    if not terms:
        return ""
    return " OR ".join(f'"{t}"' for t in terms)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, project_root: Path) -> None:
        self.db_path = project_root / ".multiagents" / "memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save_episode(
        self,
        session_id: str,
        query: str = "",
        summary: str = "",
        rounds: int = 0,
        converged: bool = False,
        duration_ms: int = 0,
        agents: list[str] | None = None,
        tags: list[str] | None = None,
        transcript_path: str = "",
    ) -> str:
        ep_id = uuid.uuid4().hex
        now = _now()
        agents_list = agents or []
        tags_list = tags or []
        with self._lock:
            self._conn.execute(
                "INSERT INTO episodes (id,session_id,query,summary,rounds,converged,"
                "duration_ms,agents,tags,transcript_path,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ep_id, session_id, query, summary, rounds, int(converged),
                    duration_ms, json.dumps(agents_list), json.dumps(tags_list),
                    transcript_path, now, now,
                ),
            )
            self._conn.commit()
        return ep_id

    def get_episode(self, episode_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id,session_id,query,summary,rounds,converged,duration_ms,"
                "agents,tags,transcript_path,created_at,updated_at "
                "FROM episodes WHERE id=?",
                (episode_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def episode_exists_for_session(self, session_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM episodes WHERE session_id=? LIMIT 1",
                (session_id,),
            ).fetchone()
        return row is not None

    def search_episodes(self, query: str, limit: int = 10) -> list[dict]:
        sanitized = _sanitize_fts_query(query)
        if not sanitized:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT e.id,e.session_id,e.query,e.summary,e.rounds,e.converged,"
                "e.duration_ms,e.agents,e.tags,e.transcript_path,e.created_at,e.updated_at "
                "FROM episodes_fts f JOIN episodes e ON f.rowid=e.rowid "
                "WHERE episodes_fts MATCH ? ORDER BY rank LIMIT ?",
                (sanitized, limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_episodes(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id,session_id,query,summary,rounds,converged,duration_ms,"
                "agents,tags,transcript_path,created_at,updated_at "
                "FROM episodes ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # -- agent_episodes CRUD --------------------------------------------------

    def save_agent_episode(
        self,
        episode_id: str,
        agent_name: str,
        response_time_ms: int = 0,
        agreed_with_consensus: bool = False,
        unique_contributions: list[str] | None = None,
    ) -> None:
        contribs = json.dumps(unique_contributions or [])
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO agent_episodes "
                "(episode_id, agent_name, response_time_ms, agreed_with_consensus, unique_contributions) "
                "VALUES (?,?,?,?,?)",
                (episode_id, agent_name, response_time_ms, int(agreed_with_consensus), contribs),
            )
            self._conn.commit()

    def get_agent_episodes(self, agent_name: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT episode_id, agent_name, response_time_ms, agreed_with_consensus, unique_contributions "
                "FROM agent_episodes WHERE agent_name=?",
                (agent_name,),
            ).fetchall()
        return [
            {
                "episode_id": r[0],
                "agent_name": r[1],
                "response_time_ms": r[2],
                "agreed_with_consensus": bool(r[3]),
                "unique_contributions": json.loads(r[4]),
            }
            for r in rows
        ]

    # -- agent_profiles CRUD ---------------------------------------------------

    def update_agent_profile(
        self,
        agent_name: str,
        strengths: list[str] | None = None,
        weaknesses: list[str] | None = None,
        notable_behaviors: list[str] | None = None,
        avg_response_time_ms: float = 0.0,
        consensus_agreement_rate: float = 0.0,
        unique_contribution_rate: float = 0.0,
        role_scores: dict[str, float] | None = None,
        best_role: str = "",
        total_sessions: int = 0,
    ) -> None:
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO agent_profiles "
                "(agent_name, strengths, weaknesses, notable_behaviors, "
                "avg_response_time_ms, consensus_agreement_rate, unique_contribution_rate, "
                "role_scores, best_role, total_sessions, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    agent_name,
                    json.dumps(strengths or []),
                    json.dumps(weaknesses or []),
                    json.dumps(notable_behaviors or []),
                    avg_response_time_ms,
                    consensus_agreement_rate,
                    unique_contribution_rate,
                    json.dumps(role_scores or {}),
                    best_role,
                    total_sessions,
                    now,
                ),
            )
            self._conn.commit()

    def get_agent_profiles(self, agent_names: list[str] | None = None) -> list[dict]:
        with self._lock:
            if agent_names:
                placeholders = ",".join("?" for _ in agent_names)
                rows = self._conn.execute(
                    f"SELECT agent_name, strengths, weaknesses, notable_behaviors, "
                    f"avg_response_time_ms, consensus_agreement_rate, unique_contribution_rate, "
                    f"role_scores, best_role, total_sessions, updated_at "
                    f"FROM agent_profiles WHERE agent_name IN ({placeholders})",
                    agent_names,
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT agent_name, strengths, weaknesses, notable_behaviors, "
                    "avg_response_time_ms, consensus_agreement_rate, unique_contribution_rate, "
                    "role_scores, best_role, total_sessions, updated_at "
                    "FROM agent_profiles ORDER BY agent_name",
                ).fetchall()
        return [self._profile_row_to_dict(r) for r in rows]

    def _profile_row_to_dict(self, row: tuple) -> dict:
        return {
            "agent_name": row[0],
            "strengths": json.loads(row[1]),
            "weaknesses": json.loads(row[2]),
            "notable_behaviors": json.loads(row[3]),
            "avg_response_time_ms": row[4],
            "consensus_agreement_rate": row[5],
            "unique_contribution_rate": row[6],
            "role_scores": json.loads(row[7]),
            "best_role": row[8],
            "total_sessions": row[9],
            "updated_at": row[10],
        }

    # -- ensemble_patterns CRUD ------------------------------------------------

    def save_ensemble_pattern(self, key: str, category: str, value: dict | list | str) -> None:
        now = _now()
        val = json.dumps(value) if not isinstance(value, str) else value
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO ensemble_patterns (key, category, value, updated_at) "
                "VALUES (?,?,?,?)",
                (key, category, val, now),
            )
            self._conn.commit()

    def get_ensemble_patterns(self, category: str | None = None) -> list[dict]:
        with self._lock:
            if category:
                rows = self._conn.execute(
                    "SELECT key, category, value, updated_at "
                    "FROM ensemble_patterns WHERE category=? ORDER BY key",
                    (category,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT key, category, value, updated_at "
                    "FROM ensemble_patterns ORDER BY category, key",
                ).fetchall()
        results = []
        for r in rows:
            try:
                val = json.loads(r[2])
            except (json.JSONDecodeError, TypeError):
                val = r[2]
            results.append({
                "key": r[0],
                "category": r[1],
                "value": val,
                "updated_at": r[3],
            })
        return results

    # -- helpers ---------------------------------------------------------------

    def _row_to_dict(self, row: tuple) -> dict:
        return {
            "id": row[0],
            "session_id": row[1],
            "query": row[2],
            "summary": row[3],
            "rounds": row[4],
            "converged": bool(row[5]),
            "duration_ms": row[6],
            "agents": json.loads(row[7]),
            "tags": json.loads(row[8]),
            "transcript_path": row[9],
            "created_at": row[10],
            "updated_at": row[11],
        }
