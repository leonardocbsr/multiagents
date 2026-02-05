"""Claude NDJSON stream-json protocol adapter.

Wire format (per Claude Agent SDK TypeScript reference):
  Send: {"type":"user","message":{"role":"user","content":"..."}}\n
  Recv: NDJSON lines with types:
    system   — init (session info), compact_boundary
    assistant — cumulative content blocks (text, thinking, tool_use,
               server_tool_use, web_search_tool_use, code_execution_tool_use,
               mcp_tool_use, and their *_result counterparts)
    result   — turn complete (subtype: success | error_max_turns |
               error_during_execution | error_max_budget_usd |
               error_max_structured_output_retries)
    user     — replayed user messages (skipped)
    stream_event — partial streaming events (only with includePartialMessages)
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from .base import AgentEvent, PermissionRequest, ProtocolAdapter, TextDelta, ThinkingDelta, ToolBadge, ToolResult, TurnComplete
from ..base import _extract_tool_detail

log = logging.getLogger("multiagents")


class ClaudeProtocol(ProtocolAdapter):
    """Adapter for Claude CLI with --input-format stream-json --output-format stream-json."""

    _session_id: str | None = None
    _last_cumulative: str = ""
    _last_thinking: str = ""
    _seen_tools: int = 0
    _seen_server_tools: int = 0
    _seen_results: int = 0
    _last_message_id: str | None = None

    def _reset_turn_state(self) -> None:
        self._last_cumulative = ""
        self._last_thinking = ""
        self._seen_tools = 0
        self._seen_server_tools = 0
        self._seen_results = 0
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

            # System events — init, compact_boundary, etc.
            if event_type == "system":
                subtype = obj.get("subtype", "")
                if subtype == "compact_boundary":
                    log.info("[claude-proto] context compaction boundary")
                    yield ToolBadge(label="Compacting", detail="")
                else:
                    log.debug("[claude-proto] system event subtype=%s", subtype)
                continue

            # Result event → turn complete (success or error)
            if event_type == "result":
                self._session_id = obj.get("session_id")
                subtype = obj.get("subtype", "success")
                is_error = obj.get("is_error", False)
                if is_error or subtype != "success":
                    errors = obj.get("errors", [])
                    log.warning(
                        "[claude-proto] turn complete with error subtype=%s errors=%s session_id=%s",
                        subtype, errors, self._session_id,
                    )
                else:
                    log.info("[claude-proto] turn complete session_id=%s", self._session_id)

                # Yield permission denials as events BEFORE TurnComplete
                for denial in obj.get("permission_denials", []):
                    yield PermissionRequest(
                        request_id=denial.get("tool_use_id", ""),
                        tool_name=denial.get("tool_name", ""),
                        tool_input=denial.get("tool_input", {}),
                        description=f"Claude wants to use {denial.get('tool_name', 'unknown')}",
                    )

                yield TurnComplete(
                    text=obj.get("result", ""),
                    session_id=self._session_id,
                )
                return

            # Assistant message events — extract deltas
            if event_type == "assistant":
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
                    self._seen_server_tools = 0
                    self._seen_results = 0

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

                # Server tool use (web search, code execution, MCP) — emit badges
                server_tools = [p for p in content if p.get("type") in {
                    "server_tool_use", "web_search_tool_use", "code_execution_tool_use", "mcp_tool_use",
                }]
                for st in server_tools[self._seen_server_tools:]:
                    st_type = st.get("type", "")
                    if st_type == "web_search_tool_use":
                        yield ToolBadge(label="Search", detail=st.get("query", "")[:80])
                    elif st_type == "code_execution_tool_use":
                        yield ToolBadge(label="Code", detail=st.get("language", ""))
                    elif st_type == "mcp_tool_use":
                        name = st.get("name", "")
                        server = st.get("server_name", "")
                        label = f"{server}/{name}" if server else name
                        yield ToolBadge(label="MCP", detail=label[:80])
                    else:
                        yield ToolBadge(label=st.get("name", st_type), detail="")
                self._seen_server_tools = len(server_tools)

                # Tool results — yield ToolResult for completed tool calls
                tool_results = [p for p in content if p.get("type") in {
                    "tool_result", "server_tool_result", "web_search_tool_result",
                    "code_execution_tool_result", "mcp_tool_result",
                }]
                for tr in tool_results[self._seen_results:]:
                    tr_type = tr.get("type", "")
                    is_err = tr.get("is_error", False)
                    tool_name = tr_type.replace("_result", "")
                    tr_content = ""
                    raw = tr.get("content")
                    if isinstance(raw, str):
                        tr_content = raw[:300]
                    elif isinstance(raw, list):
                        tr_content = " ".join(
                            p.get("text", "")[:100]
                            for p in raw
                            if isinstance(p, dict) and p.get("type") == "text"
                        )[:300]
                    yield ToolResult(tool_name=tool_name, success=not is_err, output=tr_content)
                self._seen_results = len(tool_results)

                # Text deltas (cumulative)
                texts = [p["text"] for p in content if p.get("type") == "text"]
                if texts:
                    cumulative = "".join(texts)
                    delta = cumulative[len(self._last_cumulative):]
                    self._last_cumulative = cumulative
                    if delta:
                        yield TextDelta(text=delta)

                # Log unrecognized content block types
                known_types = {
                    "text", "thinking", "tool_use", "tool_result",
                    "server_tool_use", "server_tool_result",
                    "web_search_tool_use", "web_search_tool_result",
                    "code_execution_tool_use", "code_execution_tool_result",
                    "mcp_tool_use", "mcp_tool_result",
                }
                for p in content:
                    pt = p.get("type", "")
                    if pt and pt not in known_types:
                        log.debug("[claude-proto] unhandled content block type=%s keys=%s", pt, sorted(p.keys()))
                continue

            # User message replay — skip
            if event_type == "user":
                continue

            # Partial streaming events (includePartialMessages) — skip
            if event_type == "stream_event":
                continue

            # Log unrecognized event types for debugging silent gaps
            log.debug("[claude-proto] unhandled event type=%s keys=%s", event_type, sorted(obj.keys()))

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
