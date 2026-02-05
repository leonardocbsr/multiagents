from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class SessionRecorder:
    def __init__(self, project_root: Path, session_id: str) -> None:
        self.session_id = session_id
        transcript_dir = project_root / ".multiagents" / "transcripts"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_path = transcript_dir / f"{session_id}.jsonl"
        self._file = open(self.transcript_path, "a", encoding="utf-8")

    def record_event(self, event_type: str, data: dict | None = None) -> None:
        record = {
            "type": event_type,
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "data": data or {},
        }
        self._file.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._file.flush()

    def record_user_message(self, text: str) -> None:
        self.record_event("user_message", {"text": text})

    def record_round_started(self, round_number: int, agents: list[str]) -> None:
        self.record_event("round_started", {"round": round_number, "agents": agents})

    def record_agent_completed(
        self,
        agent: str,
        text: str,
        passed: bool,
        latency_ms: float,
        round_number: int,
    ) -> None:
        self.record_event("agent_completed", {
            "agent": agent,
            "text": text,
            "passed": passed,
            "latency_ms": latency_ms,
            "round": round_number,
        })

    def record_round_ended(self, round_number: int, all_passed: bool) -> None:
        self.record_event("round_ended", {"round": round_number, "all_passed": all_passed})

    def record_discussion_ended(self, reason: str, rounds: int) -> None:
        self.record_event("discussion_ended", {"reason": reason, "rounds": rounds})

    def close(self) -> None:
        if self._file and not self._file.closed:
            self._file.close()

    def __enter__(self) -> SessionRecorder:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @staticmethod
    def read_transcript(path: Path) -> list[dict]:
        events: list[dict] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return events
