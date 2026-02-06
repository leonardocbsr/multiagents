import asyncio
import json

import pytest

from src.agents.protocols.base import TurnComplete
from src.agents.protocols.codex import CodexProtocol


class _FakeProc:
    def __init__(self, events: list[dict]) -> None:
        self.stdout = asyncio.StreamReader()
        self.stdin = None
        self.returncode = None
        for obj in events:
            self.stdout.feed_data((json.dumps(obj) + "\n").encode())
        self.stdout.feed_eof()


@pytest.mark.asyncio
async def test_codex_protocol_turn_completed_failed_marks_unsuccessful() -> None:
    proto = CodexProtocol()
    proto.proc = _FakeProc(
        [
            {"method": "turn/started", "params": {"turn": {"id": "turn-1"}}},
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {
                        "id": "turn-1",
                        "status": "failed",
                        "error": {"message": "upstream disconnected"},
                    },
                },
            },
        ]
    )

    events = []
    async for event in proto.read_events():
        events.append(event)

    done = next(e for e in events if isinstance(e, TurnComplete))
    assert done.success is False
    assert done.error == "upstream disconnected"


@pytest.mark.asyncio
async def test_codex_protocol_turn_completed_interrupted_marks_unsuccessful() -> None:
    proto = CodexProtocol()
    proto.proc = _FakeProc(
        [
            {"method": "turn/started", "params": {"turn": {"id": "turn-2"}}},
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-2",
                    "turn": {"id": "turn-2", "status": "interrupted"},
                },
            },
        ]
    )

    events = []
    async for event in proto.read_events():
        events.append(event)

    done = next(e for e in events if isinstance(e, TurnComplete))
    assert done.success is False
    assert done.error is None
