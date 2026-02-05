"""Claude NDJSON stream-json protocol adapter.

Wire format:
  Send: {"type":"user","message":{"role":"user","content":"..."}}\n
  Recv: NDJSON lines — assistant messages, tool use, result events
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from .base import AgentEvent, ProtocolAdapter, TextDelta, ThinkingDelta, ToolBadge, TurnComplete
from ..base import _extract_tool_detail

log = logging.getLogger("multiagents")


class ClaudeProtocol(ProtocolAdapter):
    """Adapter for Claude CLI with --input-format stream-json --output-format stream-json."""

    _session_id: str | None = None
    _last_cumulative: str = ""
    _last_thinking: str = ""
    _seen_tools: int = 0
    _last_message_id: str | None = None

    def _reset_turn_state(self) -> None:
        self._last_cumulative = ""
        self._last_thinking = ""
        self._seen_tools = 0
        self._last_message_id = None

    async def send_message(self, text: str) -> None:
        assert self.proc and self.proc.stdin
        log.info("[claude-proto] send message chars=%d", len(text))
        payload = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": text},
        })
        self.proc.stdin.write((payload + "\n").encode())
        await self.proc.stdin.drain()

    async def read_events(self) -> AsyncIterator[AgentEvent]:
        assert self.proc and self.proc.stdout
        self._reset_turn_state()

        async for raw_line in self.proc.stdout:
            line = raw_line.decode()
            if not line.strip():
                continue

            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                log.debug("[claude-proto] json parse failed: %s", line[:200].rstrip())
                continue

            event_type = obj.get("type", "")

            # System init events — skip
            if event_type == "system":
                log.debug("[claude-proto] system event, skipping")
                continue

            # Result event → turn complete
            if event_type == "result":
                self._session_id = obj.get("session_id")
                log.info("[claude-proto] turn complete session_id=%s", self._session_id)
                yield TurnComplete(
                    text=obj.get("result", ""),
                    session_id=self._session_id,
                )
                return

            # Assistant message events — extract deltas
            msg = obj.get("message", {})
            content = msg.get("content", [])
            if not content:
                continue

            # Detect new assistant turn (content resets after tool use)
            msg_id = msg.get("id")
            if msg_id and msg_id != self._last_message_id:
                log.debug("[claude-proto] new assistant turn msg_id=%s", msg_id)
                self._last_message_id = msg_id
                self._last_cumulative = ""
                self._last_thinking = ""
                self._seen_tools = 0

            # Thinking deltas
            thinking_parts = [p.get("thinking", "") for p in content if p.get("type") == "thinking"]
            if thinking_parts:
                cumulative_thinking = "".join(thinking_parts)
                delta = cumulative_thinking[len(self._last_thinking):]
                self._last_thinking = cumulative_thinking
                if delta.strip():
                    yield ThinkingDelta(text=delta)

            # Tool use badges (cumulative — only emit new ones)
            tools = [p for p in content if p.get("type") == "tool_use"]
            new_tools = tools[self._seen_tools:]
            for t in new_tools:
                yield ToolBadge(
                    label=t.get("name", ""),
                    detail=_extract_tool_detail(t.get("input", {})),
                )
            self._seen_tools = len(tools)

            # Text deltas (cumulative)
            texts = [p["text"] for p in content if p.get("type") == "text"]
            if texts:
                cumulative = "".join(texts)
                delta = cumulative[len(self._last_cumulative):]
                self._last_cumulative = cumulative
                if delta:
                    yield TextDelta(text=delta)

        log.warning("[claude-proto] process ended before result event")
        raise RuntimeError("claude process ended before result event")

    async def cancel(self) -> None:
        log.debug("[claude-proto] cancel requested")
        if self.proc and self.proc.stdin:
            # Send a cancel/interrupt — Claude doesn't have a wire-level cancel,
            # but we can close stdin to signal end of input
            pass

    def get_session_id(self) -> str | None:
        return self._session_id
