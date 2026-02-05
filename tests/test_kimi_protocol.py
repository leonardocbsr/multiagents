import asyncio
import json

import pytest

from src.agents.protocols.base import TextDelta, TurnComplete
from src.agents.protocols.kimi import KimiProtocol


class _FakeStdin:
    def __init__(self, on_line):
        self._on_line = on_line
        self._buf = ""
        self.lines: list[str] = []

    def write(self, data: bytes) -> None:
        self._buf += data.decode()
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if not line:
                continue
            self.lines.append(line)
            self._on_line(line)

    async def drain(self) -> None:
        return None


class _FakeProc:
    def __init__(self) -> None:
        self.stdout = asyncio.StreamReader()
        self.returncode = None
        self.stdin = _FakeStdin(self._handle_line)

    def _emit(self, obj: dict) -> None:
        self.stdout.feed_data((json.dumps(obj) + "\n").encode())

    def _handle_line(self, line: str) -> None:
        obj = json.loads(line)
        method = obj.get("method")
        req_id = obj.get("id")

        if method == "initialize":
            assert isinstance(req_id, str)
            self._emit(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"protocol_version": "1.2"},
                }
            )
            return

        if method == "prompt":
            assert isinstance(req_id, str)
            self._emit(
                {
                    "jsonrpc": "2.0",
                    "id": "req-1",
                    "method": "request",
                    "params": {"type": "ApprovalRequest", "payload": {"id": "apr-1"}},
                }
            )
            self._emit(
                {
                    "jsonrpc": "2.0",
                    "method": "event",
                    "params": {
                        "type": "ContentPart",
                        "payload": {"type": "text", "text": "Hi"},
                    },
                }
            )
            self._emit(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"status": "finished", "sessionId": "sid-1"},
                }
            )


@pytest.mark.asyncio
async def test_kimi_protocol_wire_v12_initialize_prompt_and_request_response():
    proc = _FakeProc()
    proto = KimiProtocol()
    proto.proc = proc

    await proto.send_message("hello")
    events = []
    async for event in proto.read_events():
        events.append(event)

    text_events = [e for e in events if isinstance(e, TextDelta)]
    assert text_events
    assert text_events[0].text == "Hi"

    turn = next(e for e in events if isinstance(e, TurnComplete))
    assert turn.text == "Hi"
    assert turn.session_id == "sid-1"

    outbound = [json.loads(line) for line in proc.stdin.lines]
    methods = [m.get("method") for m in outbound if "method" in m]
    assert methods[:2] == ["initialize", "prompt"]
    assert isinstance(outbound[0]["id"], str)
    assert isinstance(outbound[1]["id"], str)

    approval_responses = [
        m for m in outbound if m.get("id") == "req-1" and "result" in m
    ]
    assert approval_responses
    assert approval_responses[0]["result"]["response"] == "approve"
