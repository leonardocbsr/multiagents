from __future__ import annotations

from src.formatter import format_event


def test_agent_completed_with_share():
    event = {
        "type": "agent_completed",
        "agent": "claude",
        "text": "<thinking>internal reasoning</thinking><Share>Here is my analysis of the problem.</Share>",
        "passed": False,
        "success": True,
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert messages[0].startswith("**Claude:**")
    assert "Here is my analysis of the problem." in messages[0]
    assert "thinking" not in messages[0].lower()
    assert "<Share>" not in messages[0]


def test_agent_completed_no_share_private():
    event = {
        "type": "agent_completed",
        "agent": "codex",
        "text": "some internal reasoning without share tags",
        "passed": False,
        "success": True,
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "private" in messages[0].lower()


def test_agent_completed_pass():
    event = {
        "type": "agent_completed",
        "agent": "kimi",
        "text": "[PASS]",
        "passed": True,
        "success": True,
    }
    messages = format_event(event)
    assert messages == []


def test_agent_completed_with_tool_badges():
    event = {
        "type": "agent_completed",
        "agent": "claude",
        "text": "<tool>Read src/main.py</tool>\n<Share>I read the file and found the issue.</Share>",
        "passed": False,
        "success": True,
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "Read" in messages[0] or "🔧" in messages[0]
    assert "I read the file and found the issue." in messages[0]


def test_agent_completed_failure():
    event = {
        "type": "agent_completed",
        "agent": "codex",
        "text": "",
        "passed": False,
        "success": False,
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "failed" in messages[0].lower() or "error" in messages[0].lower()


def test_round_started():
    event = {
        "type": "round_started",
        "round": 2,
        "agents": ["claude", "codex"],
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "Round 2" in messages[0]


def test_round_started_first_round_silent():
    event = {
        "type": "round_started",
        "round": 1,
        "agents": ["claude", "codex"],
    }
    messages = format_event(event)
    assert messages == []


def test_round_ended_all_passed():
    event = {
        "type": "round_ended",
        "round": 3,
        "all_passed": True,
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "passed" in messages[0].lower()


def test_round_ended_normal():
    event = {
        "type": "round_ended",
        "round": 3,
        "all_passed": False,
    }
    messages = format_event(event)
    assert messages == []


def test_agent_interrupted():
    event = {
        "type": "agent_interrupted",
        "agent": "claude",
        "round": 2,
        "partial_text": "I was working on...",
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "Claude" in messages[0]
    assert "interrupted" in messages[0].lower()


def test_discussion_ended():
    event = {
        "type": "discussion_ended",
        "reason": "all_passed",
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "ended" in messages[0].lower() or "complete" in messages[0].lower()


def test_long_message_split():
    long_text = "A" * 3000
    event = {
        "type": "agent_completed",
        "agent": "claude",
        "text": f"<Share>{long_text}</Share>",
        "passed": False,
        "success": True,
    }
    messages = format_event(event)
    assert len(messages) >= 2
    for msg in messages:
        assert len(msg) <= 2000


def test_unknown_event_ignored():
    event = {"type": "agent_stream", "agent": "claude", "chunk": "partial"}
    messages = format_event(event)
    assert messages == []


def test_multiple_share_blocks():
    event = {
        "type": "agent_completed",
        "agent": "claude",
        "text": "<Share>First point.</Share>\n<thinking>hmm</thinking>\n<Share>Second point.</Share>",
        "passed": False,
        "success": True,
    }
    messages = format_event(event)
    assert len(messages) == 1
    assert "First point." in messages[0]
    assert "Second point." in messages[0]
