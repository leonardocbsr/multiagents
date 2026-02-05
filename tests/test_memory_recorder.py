import json
from pathlib import Path

from src.memory.recorder import SessionRecorder


def test_creates_transcript_file(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    with SessionRecorder(tmp_path, "sess-1") as rec:
        rec.record_event("test", {"key": "val"})
    assert rec.transcript_path.exists()
    assert rec.transcript_path.parent.name == "transcripts"


def test_appends_jsonl_lines(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    with SessionRecorder(tmp_path, "sess-1") as rec:
        rec.record_event("round_started", {"round": 1})
        rec.record_event("agent_completed", {"agent": "claude"})
    lines = rec.transcript_path.read_text().strip().split("\n")
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["type"] == "round_started"
    assert "ts" in first


def test_read_transcript(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    with SessionRecorder(tmp_path, "sess-1") as rec:
        rec.record_event("a", {})
        rec.record_event("b", {})
    events = SessionRecorder.read_transcript(rec.transcript_path)
    assert len(events) == 2
    assert events[0]["type"] == "a"


def test_typed_methods(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    with SessionRecorder(tmp_path, "sess-1") as rec:
        rec.record_user_message("Hello")
        rec.record_round_started(1, ["claude", "codex"])
        rec.record_agent_completed("claude", "Response", False, 1500.0, 1)
        rec.record_round_ended(1, False)
        rec.record_discussion_ended("all_passed", 2)
    events = SessionRecorder.read_transcript(rec.transcript_path)
    types = [e["type"] for e in events]
    assert types == ["user_message", "round_started", "agent_completed", "round_ended", "discussion_ended"]
    assert events[0]["data"]["text"] == "Hello"
    assert events[2]["data"]["agent"] == "claude"
    assert events[2]["data"]["latency_ms"] == 1500.0


def test_appends_to_existing(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    with SessionRecorder(tmp_path, "sess-1") as r1:
        r1.record_event("first", {})
    with SessionRecorder(tmp_path, "sess-1") as r2:
        r2.record_event("second", {})
    events = SessionRecorder.read_transcript(r2.transcript_path)
    assert len(events) == 2
