"""Tests for the permission event system.

Covers:
- Protocol-level PermissionRequest/PermissionResponse dataclasses
- Claude protocol: permission_denials extraction from result events
- Codex protocol: approval policy mapping from permission_mode
- Kimi protocol: Future-based interactive approval
- ChatRoom: permission events flow through to event queue
- event_to_dict: AgentPermissionRequested serialization
- Settings: permission defaults exist
- Agent CLI flags: permission_mode affects CLI args
"""
import asyncio

import pytest

from src.agents.protocols.base import PermissionRequest, PermissionResponse
from src.agents.base import AgentPermissionRequest, AgentResponse
from src.chat.events import AgentDeliveryAcked, AgentPermissionRequested
from src.chat.room import ChatRoom
from src.server.protocol import event_to_dict
from src.server.settings import DEFAULTS


# ── Dataclass construction ────────────────────────────────────────────────

def test_permission_request_defaults():
    pr = PermissionRequest()
    assert pr.request_id == ""
    assert pr.tool_name == ""
    assert pr.tool_input == {}
    assert pr.description == ""


def test_permission_request_with_values():
    pr = PermissionRequest(
        request_id="req-1",
        tool_name="Write",
        tool_input={"file_path": "/tmp/test.txt"},
        description="Write a file",
    )
    assert pr.request_id == "req-1"
    assert pr.tool_name == "Write"
    assert pr.tool_input == {"file_path": "/tmp/test.txt"}


def test_permission_response_defaults():
    resp = PermissionResponse()
    assert resp.request_id == ""
    assert resp.approved is False


def test_permission_response_approved():
    resp = PermissionResponse(request_id="req-1", approved=True)
    assert resp.approved is True


def test_agent_permission_request_construction():
    apr = AgentPermissionRequest(
        agent="claude",
        request_id="req-1",
        tool_name="Bash",
        tool_input={"command": "ls"},
        description="Run ls",
    )
    assert apr.agent == "claude"
    assert apr.request_id == "req-1"


# ── Settings defaults ─────────────────────────────────────────────────────

def test_permission_settings_defaults_exist():
    assert "agents.claude.permissions" in DEFAULTS
    assert "agents.codex.permissions" in DEFAULTS
    assert "agents.kimi.permissions" in DEFAULTS
    assert "permissions.timeout" in DEFAULTS


def test_permission_settings_default_values():
    assert DEFAULTS["agents.claude.permissions"] == "bypass"
    assert DEFAULTS["agents.codex.permissions"] == "bypass"
    assert DEFAULTS["agents.kimi.permissions"] == "bypass"
    assert DEFAULTS["permissions.timeout"] == 120


# ── event_to_dict serialization ──────────────────────────────────────────

def test_event_to_dict_permission_requested():
    event = AgentPermissionRequested(
        agent_name="claude",
        round_number=1,
        request_id="req-42",
        tool_name="Write",
        tool_input={"file_path": "/tmp/test.txt"},
        description="Claude wants to use Write",
    )
    d = event_to_dict(event)
    assert d["type"] == "permission_request"
    assert d["agent"] == "claude"
    assert d["round"] == 1
    assert d["request_id"] == "req-42"
    assert d["tool_name"] == "Write"
    assert d["tool_input"] == {"file_path": "/tmp/test.txt"}
    assert d["description"] == "Claude wants to use Write"
    assert "created_at" in d


def test_event_to_dict_delivery_acked():
    event = AgentDeliveryAcked(
        delivery_id="d42",
        recipient="codex",
        sender="claude",
        round_number=3,
    )
    d = event_to_dict(event)
    assert d["type"] == "delivery_acked"
    assert d["delivery_id"] == "d42"
    assert d["recipient"] == "codex"
    assert d["sender"] == "claude"
    assert d["round"] == 3
    assert "created_at" in d


# ── Claude agent CLI flags ───────────────────────────────────────────────

def test_claude_bypass_mode_flags():
    from src.agents.claude import ClaudeAgent
    agent = ClaudeAgent()
    agent.permission_mode = "bypass"
    args = agent._build_persistent_args()
    assert "--dangerously-skip-permissions" in args
    assert "--permission-mode" not in args


def test_claude_auto_mode_flags():
    from src.agents.claude import ClaudeAgent
    agent = ClaudeAgent()
    agent.permission_mode = "auto"
    args = agent._build_persistent_args()
    assert "--dangerously-skip-permissions" not in args
    assert "--permission-mode" in args
    idx = args.index("--permission-mode")
    assert args[idx + 1] == "dontAsk"
    # Should have --settings with pre-approved tools
    assert "--settings" in args


def test_claude_manual_mode_flags():
    from src.agents.claude import ClaudeAgent
    agent = ClaudeAgent()
    agent.permission_mode = "manual"
    args = agent._build_persistent_args()
    assert "--dangerously-skip-permissions" not in args
    assert "--permission-mode" in args
    # Manual mode should NOT have --settings with pre-approvals
    assert "--settings" not in args


# ── Codex approval policy mapping ────────────────────────────────────────

def test_codex_bypass_policy():
    from src.agents.codex import CodexAgent
    agent = CodexAgent()
    agent.permission_mode = "bypass"
    proto = agent._get_protocol()
    assert proto._approval_policy == "never"
    assert proto._sandbox == "danger-full-access"


def test_codex_auto_policy():
    from src.agents.codex import CodexAgent
    agent = CodexAgent()
    agent.permission_mode = "auto"
    proto = agent._get_protocol()
    assert proto._approval_policy == "auto-edit"


def test_codex_manual_policy():
    from src.agents.codex import CodexAgent
    agent = CodexAgent()
    agent.permission_mode = "manual"
    proto = agent._get_protocol()
    assert proto._approval_policy == "suggest"


# ── Kimi --yolo flag ─────────────────────────────────────────────────────

def test_kimi_bypass_includes_yolo():
    from src.agents.kimi import KimiAgent
    agent = KimiAgent()
    agent.permission_mode = "bypass"
    args = agent._build_persistent_args()
    assert "--yolo" in args


def test_kimi_auto_excludes_yolo():
    from src.agents.kimi import KimiAgent
    agent = KimiAgent()
    agent.permission_mode = "auto"
    args = agent._build_persistent_args()
    assert "--yolo" not in args


def test_kimi_manual_excludes_yolo():
    from src.agents.kimi import KimiAgent
    agent = KimiAgent()
    agent.permission_mode = "manual"
    args = agent._build_persistent_args()
    assert "--yolo" not in args


def test_kimi_protocol_receives_permission_mode():
    from src.agents.kimi import KimiAgent
    agent = KimiAgent()
    agent.permission_mode = "manual"
    agent.permission_timeout = 42
    proto = agent._get_protocol()
    assert proto._permission_mode == "manual"
    assert proto._permission_timeout == 42


# ── Kimi protocol Future-based approval ──────────────────────────────────

@pytest.mark.asyncio
async def test_kimi_protocol_respond_to_permission():
    from src.agents.protocols.kimi import KimiProtocol
    proto = KimiProtocol(permission_mode="manual")

    # Simulate pending permission
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    proto._pending_permissions["req-1"] = future

    # Respond
    await proto.respond_to_permission(PermissionResponse(request_id="req-1", approved=True))

    assert future.done()
    assert future.result().approved is True


@pytest.mark.asyncio
async def test_kimi_protocol_respond_unknown_request():
    from src.agents.protocols.kimi import KimiProtocol
    proto = KimiProtocol(permission_mode="manual")

    # Responding to unknown request_id should not raise
    await proto.respond_to_permission(PermissionResponse(request_id="nonexistent", approved=False))
    assert len(proto._pending_permissions) == 0


# ── ChatRoom permission event flow ───────────────────────────────────────

class FakeAgentWithPermission:
    """Fake agent that yields a permission request on round 1, then passes on round 2."""

    def __init__(self, name: str):
        self.name = name
        self.session_id = None
        self._call = 0

    async def stream(self, prompt, timeout=120.0):
        self._call += 1
        if self._call == 1:
            yield AgentPermissionRequest(
                agent=self.name,
                request_id="req-99",
                tool_name="Bash",
                tool_input={"command": "rm -rf /"},
                description="Run dangerous command",
            )
            yield "Some response after permission"
            yield AgentResponse(
                agent=self.name,
                response="Some response after permission",
                success=True,
                latency_ms=50.0,
            )
        else:
            yield "[PASS]"
            yield AgentResponse(
                agent=self.name, response="[PASS]", success=True, latency_ms=10.0
            )


class FakePassAgent:
    def __init__(self, name: str, responses=None):
        self.name = name
        self.session_id = None
        self._responses = iter(responses or ["[PASS]"])

    async def stream(self, prompt, timeout=120.0):
        text = next(self._responses, "[PASS]")
        yield text
        yield AgentResponse(
            agent=self.name, response=text, success=True, latency_ms=10.0
        )


@pytest.mark.asyncio
async def test_chatroom_yields_permission_event():
    agents = [
        FakeAgentWithPermission("claude"),
        FakePassAgent("codex", ["Hi!", "[PASS]"]),
    ]
    room = ChatRoom(agents)
    events = []
    async for event in room.run("Do something"):
        events.append(event)

    perm_events = [e for e in events if isinstance(e, AgentPermissionRequested)]
    assert len(perm_events) >= 1
    pe = perm_events[0]
    assert pe.agent_name == "claude"
    assert pe.request_id == "req-99"
    assert pe.tool_name == "Bash"
    assert pe.tool_input == {"command": "rm -rf /"}


@pytest.mark.asyncio
async def test_chatroom_respond_to_permission():
    """Test that respond_to_permission routes to the correct agent."""
    from src.agents.base import BaseAgent

    called_with = {}

    class MockAgent:
        def __init__(self, name):
            self.name = name
            self.session_id = None

        async def respond_to_permission(self, response):
            called_with[self.name] = response

        async def stream(self, prompt, timeout=120.0):
            yield "[PASS]"
            yield AgentResponse(
                agent=self.name, response="[PASS]", success=True, latency_ms=10.0
            )

    agents = [MockAgent("claude"), MockAgent("codex")]
    room = ChatRoom(agents)

    resp = PermissionResponse(request_id="req-1", approved=True)
    room.respond_to_permission("claude", resp)
    # Give the task a moment to run
    await asyncio.sleep(0.05)

    assert "claude" in called_with
    assert called_with["claude"].approved is True
    assert "codex" not in called_with


# ── Runner permission config application ─────────────────────────────────

def test_apply_config_sets_permission_mode():
    """Test that _apply_config_to_agents applies permission_mode from config."""
    from src.agents.claude import ClaudeAgent
    from src.agents.codex import CodexAgent

    agent_c = ClaudeAgent()
    agent_x = CodexAgent()

    # Simulate what runner._apply_config_to_agents does
    config = {
        "agents.claude.permissions": "manual",
        "agents.codex.permissions": "auto",
    }
    for agent in [agent_c, agent_x]:
        agent_type = agent.agent_type or agent.name
        perm_mode = config.get(f"agents.{agent_type}.permissions", "bypass")
        if hasattr(agent, "permission_mode"):
            agent.permission_mode = perm_mode

    assert agent_c.permission_mode == "manual"
    assert agent_x.permission_mode == "auto"


def test_apply_config_sets_permission_timeout():
    """Test that _apply_config_to_agents applies permissions.timeout to agents."""
    import tempfile
    from pathlib import Path

    from src.agents.kimi import KimiAgent
    from src.server.runner import SessionRunner
    from src.server.sessions import SessionStore

    db_path = Path(tempfile.mkdtemp()) / "test.db"
    runner = SessionRunner(store=SessionStore(db_path))
    agent = KimiAgent()
    assert agent.permission_timeout == 120.0

    runner._apply_config_to_agents([agent], {"permissions.timeout": 15})
    assert agent.permission_timeout == 15.0
