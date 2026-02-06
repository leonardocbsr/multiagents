from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.agents.persistent import PersistentAgent
from src.agents.protocols.base import ProcessRestarted, ProtocolAdapter, TextDelta, TurnComplete


class _LineProtocol(ProtocolAdapter):
    """Tiny test protocol for line-based JSON subprocess fixtures."""

    async def send_message(self, text: str) -> None:
        assert self.proc and self.proc.stdin
        self.proc.stdin.write((text + "\n").encode())
        await self.proc.stdin.drain()

    async def start_resume(self, session_id: str) -> None:
        return

    async def start(self) -> None:
        return

    async def shutdown(self) -> None:
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()

    async def cancel(self) -> None:
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()

    async def read_events(self):
        assert self.proc and self.proc.stdout
        saw_complete = False
        async for raw in self.proc.stdout:
            data = json.loads(raw.decode())
            t = data.get("type")
            if t == "text":
                yield TextDelta(text=data.get("text", ""))
            elif t == "done":
                saw_complete = True
                yield TurnComplete(text=data.get("text", ""), session_id=data.get("sid", "sid-test"))
                return
        if not saw_complete:
            raise RuntimeError("turn ended without completion marker")


def _write_flaky_agent_script(path: Path) -> None:
    path.write_text(
        "import json\n"
        "import pathlib\n"
        "import sys\n"
        "\n"
        "counter = pathlib.Path(sys.argv[1])\n"
        "n = 0\n"
        "if counter.exists():\n"
        "    n = int(counter.read_text() or '0')\n"
        "n += 1\n"
        "counter.write_text(str(n))\n"
        "_ = sys.stdin.readline()\n"
        "if n == 1:\n"
        "    raise SystemExit(1)\n"
        "print(json.dumps({'type':'text','text':'ok after restart'}), flush=True)\n"
        "print(json.dumps({'type':'done','text':'ok after restart','sid':'sid-2'}), flush=True)\n"
    )


def _write_always_crash_script(path: Path) -> None:
    path.write_text(
        "import sys\n"
        "_ = sys.stdin.readline()\n"
        "raise SystemExit(1)\n"
    )


@pytest.mark.asyncio
async def test_persistent_agent_recovers_after_subprocess_crash(tmp_path):
    script = tmp_path / "flaky_agent.py"
    counter = tmp_path / "counter.txt"
    _write_flaky_agent_script(script)

    agent = PersistentAgent(
        agent_name="test",
        build_args_fn=lambda: [sys.executable, str(script), str(counter)],
        build_resume_args_fn=lambda _sid: [sys.executable, str(script), str(counter)],
        get_protocol_fn=_LineProtocol,
    )

    events = []
    try:
        async for ev in agent.send_and_stream("hello"):
            events.append(ev)
    finally:
        await agent.shutdown()

    assert any(isinstance(e, ProcessRestarted) and e.retry == 1 for e in events)
    assert any(isinstance(e, TextDelta) and "ok after restart" in e.text for e in events)
    done = next(e for e in events if isinstance(e, TurnComplete))
    assert done.session_id == "sid-2"


@pytest.mark.asyncio
async def test_persistent_agent_raises_after_max_retries(tmp_path):
    script = tmp_path / "always_crash.py"
    _write_always_crash_script(script)

    agent = PersistentAgent(
        agent_name="test",
        build_args_fn=lambda: [sys.executable, str(script)],
        build_resume_args_fn=lambda _sid: [sys.executable, str(script)],
        get_protocol_fn=_LineProtocol,
    )

    events = []
    with pytest.raises(RuntimeError):
        try:
            async for ev in agent.send_and_stream("hello"):
                events.append(ev)
        finally:
            await agent.shutdown()

    restart_events = [e for e in events if isinstance(e, ProcessRestarted)]
    assert [e.retry for e in restart_events] == [1, 2, 3]
