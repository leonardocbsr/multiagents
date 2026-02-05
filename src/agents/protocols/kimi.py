"""Kimi JSON-RPC wire protocol adapter.

Wire format:
  Send: JSON-RPC requests (prompt, cancel)
  Recv: JSON-RPC notifications (ContentPart, TurnEnd, etc.)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncIterator

from .base import AgentEvent, ProtocolAdapter, TextDelta, ThinkingDelta, ToolBadge, TurnComplete
from ..base import _extract_tool_detail

log = logging.getLogger("multiagents")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07")


class KimiProtocol(ProtocolAdapter):
    """Adapter for Kimi CLI with --wire mode (JSON-RPC 2.0)."""

    _session_id: str | None = None

    def __init__(self) -> None:
        self._id_counter = 0
        self._last_prompt_id: str | None = None
        self._initialized = False

    def _next_id(self) -> str:
        self._id_counter += 1
        return str(self._id_counter)

    async def _send_rpc(self, method: str, params: dict | None = None) -> str:
        assert self.proc and self.proc.stdin
        req_id = self._next_id()
        msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        data = json.dumps(msg) + "\n"
        self.proc.stdin.write(data.encode())
        await self.proc.stdin.drain()
        return req_id

    async def _send_response(self, req_id: object, result: dict) -> None:
        assert self.proc and self.proc.stdin
        msg = {"jsonrpc": "2.0", "id": req_id, "result": result}
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        await self.proc.stdin.drain()

    async def _read_json_line(self) -> dict | None:
        assert self.proc and self.proc.stdout
        raw = await self.proc.stdout.readline()
        if not raw:
            return None
        line = _ANSI_RE.sub("", raw.decode())
        try:
            return json.loads(line)
        except (json.JSONDecodeError, ValueError):
            log.debug("[kimi-proto] json parse failed during init: %s", line[:200].rstrip())
            return None

    async def _wait_for_response(self, expected_id: str, timeout: float = 10.0) -> dict | None:
        try:
            async with asyncio.timeout(timeout):
                while True:
                    obj = await self._read_json_line()
                    if obj is None:
                        return None
                    if str(obj.get("id")) == expected_id and ("result" in obj or "error" in obj):
                        return obj
        except asyncio.TimeoutError:
            return None

    async def start(self) -> None:
        if self._initialized:
            return
        req_id = await self._send_rpc(
            "initialize",
            {
                "protocol_version": "1.2",
                "client": {"name": "multiagents", "version": "1.0.0"},
            },
        )
        resp = await self._wait_for_response(req_id)
        if resp is None:
            raise RuntimeError("kimi initialize timed out")
        if "error" in resp:
            raise RuntimeError(f"kimi initialize error: {resp['error']}")
        self._initialized = True
        log.info("[kimi-proto] initialized wire protocol")

    async def send_message(self, text: str) -> None:
        if not self._initialized:
            await self.start()
        log.info("[kimi-proto] send prompt chars=%d", len(text))
        self._last_prompt_id = await self._send_rpc("prompt", {"user_input": text})

    async def read_events(self) -> AsyncIterator[AgentEvent]:
        assert self.proc and self.proc.stdout
        streamed_text: list[str] = []
        rpc_error: object | None = None
        line_count = 0
        text_events = 0
        thinking_events = 0
        tool_events = 0
        methods_seen: dict[str, int] = {}

        def _bump_method(name: str) -> None:
            key = name or "<none>"
            methods_seen[key] = methods_seen.get(key, 0) + 1

        async for raw_line in self.proc.stdout:
            line = raw_line.decode()
            if not line.strip():
                continue
            line_count += 1

            # Strip ANSI codes before parsing
            line = _ANSI_RE.sub("", line)

            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                log.debug("[kimi-proto] json parse failed: %s", line[:200].rstrip())
                continue

            method = obj.get("method", "")
            method_norm = method.lower() if isinstance(method, str) else ""
            params = obj.get("params", {})
            _bump_method(method_norm)

            # Wire protocol wrapper: event notifications carry typed payloads.
            if method_norm == "event" and isinstance(params, dict):
                method_norm = str(params.get("type", "")).lower()
                params = params.get("payload", {})
                _bump_method(f"event:{method_norm}")

            # Wire protocol request: must respond or the turn can block forever.
            if method_norm == "request" and isinstance(params, dict):
                req_id = obj.get("id")
                req_type = str(params.get("type", ""))
                payload = params.get("payload", {}) if isinstance(params.get("payload"), dict) else {}
                if req_id is not None:
                    if req_type == "ApprovalRequest":
                        response_id = payload.get("id") or payload.get("request_id") or ""
                        await self._send_response(req_id, {"request_id": response_id, "response": "approve"})
                        log.info("[kimi-proto] auto-approved request id=%s", response_id)
                    elif req_type == "ToolCallRequest":
                        tool_call_id = payload.get("id") or payload.get("tool_call_id") or ""
                        await self._send_response(
                            req_id,
                            {
                                "tool_call_id": tool_call_id,
                                "return_value": {
                                    "is_error": True,
                                    "output": "",
                                    "message": "external tool bridge not configured",
                                    "display": [],
                                },
                            },
                        )
                        log.info("[kimi-proto] rejected external tool request id=%s", tool_call_id)
                    else:
                        await self._send_response(req_id, {"ok": True})
                        log.info("[kimi-proto] acknowledged request type=%s", req_type)
                continue

            # Content part notification
            if method_norm in {"contentpart", "content_part", "content/part"}:
                part = params.get("part", params) if isinstance(params, dict) else {}
                part_type = str(part.get("type", "")).lower()
                if part_type == "text":
                    text = _ANSI_RE.sub("", part.get("text", "") or part.get("delta", ""))
                    if text:
                        streamed_text.append(text)
                        text_events += 1
                        yield TextDelta(text=text)
                elif part_type in {"think", "thinking"}:
                    text = part.get("think", "") or part.get("thinking", "")
                    if text:
                        thinking_events += 1
                        yield ThinkingDelta(text=text)
                elif part_type in {"tool_call", "toolcall"} or ("function" in part):
                    fn = part.get("function", {})
                    name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except (json.JSONDecodeError, ValueError):
                        args = {}
                    tool_events += 1
                    yield ToolBadge(label=name, detail=_extract_tool_detail(args))
                continue

            # Turn end notification
            if method_norm in {"turnend", "turn/end", "turn_completed", "turncompleted"}:
                result = params.get("result", "") if isinstance(params, dict) else ""
                text = ""
                if isinstance(result, dict):
                    text = str(result.get("text", "") or result.get("content", ""))
                elif isinstance(result, str):
                    text = result
                self._session_id = (
                    params.get("session_id") if isinstance(params, dict) else None
                ) or (params.get("sessionId") if isinstance(params, dict) else None)
                log.info(
                    "[kimi-proto] turn complete via method=%s lines=%d text_events=%d think_events=%d tool_events=%d session_id=%s",
                    method_norm,
                    line_count,
                    text_events,
                    thinking_events,
                    tool_events,
                    self._session_id,
                )
                yield TurnComplete(text=text, session_id=self._session_id)
                return

            # Response object (JSON-RPC response to our request) — may contain session_id
            if "id" in obj and "result" in obj:
                result = obj["result"]
                if isinstance(result, dict) and "session_id" in result:
                    self._session_id = result["session_id"]
                if isinstance(result, dict) and "sessionId" in result:
                    self._session_id = result["sessionId"]
                if self._last_prompt_id is not None and str(obj.get("id")) == self._last_prompt_id:
                    status = result.get("status") if isinstance(result, dict) else None
                    log.info(
                        "[kimi-proto] prompt completed via RPC result status=%s lines=%d text_events=%d session_id=%s",
                        status,
                        line_count,
                        text_events,
                        self._session_id,
                    )
                    yield TurnComplete(text="".join(streamed_text), session_id=self._session_id)
                    return
                continue
            if "id" in obj and "error" in obj:
                rpc_error = obj["error"]
                err_id = obj.get("id")
                if self._last_prompt_id is None or err_id == self._last_prompt_id:
                    raise RuntimeError(f"kimi prompt RPC error: {rpc_error}")
                continue

            # Fallback: some kimi builds emit stream-json style assistant objects.
            if obj.get("type") == "text":
                text = _ANSI_RE.sub("", obj.get("text", ""))
                if text:
                    streamed_text.append(text)
                    text_events += 1
                    yield TextDelta(text=text)
                continue

            if obj.get("role") == "assistant":
                for part in obj.get("content", []) or []:
                    if not isinstance(part, dict):
                        continue
                    ptype = str(part.get("type", "")).lower()
                    if ptype == "text":
                        text = _ANSI_RE.sub("", part.get("text", ""))
                        if text:
                            streamed_text.append(text)
                            text_events += 1
                            yield TextDelta(text=text)
                    elif ptype in {"think", "thinking"}:
                        thinking = part.get("think", "") or part.get("thinking", "")
                        if thinking:
                            thinking_events += 1
                            yield ThinkingDelta(text=thinking)
                    elif ptype in {"tool_call", "toolcall"}:
                        fn = part.get("function", {})
                        name = fn.get("name", "")
                        try:
                            args = json.loads(fn.get("arguments", "{}"))
                        except (json.JSONDecodeError, ValueError):
                            args = {}
                        tool_events += 1
                        yield ToolBadge(label=name, detail=_extract_tool_detail(args))
                continue

            event_type = str(obj.get("type", "")).lower()
            if event_type in {"turnend", "turn_end", "done", "result"}:
                result = obj.get("result", "")
                text = ""
                if isinstance(result, dict):
                    text = str(result.get("text", "") or result.get("content", ""))
                elif isinstance(result, str):
                    text = result
                self._session_id = obj.get("session_id") or obj.get("sessionId") or self._session_id
                log.info(
                    "[kimi-proto] turn complete via type=%s lines=%d text_events=%d think_events=%d tool_events=%d session_id=%s",
                    event_type,
                    line_count,
                    text_events,
                    thinking_events,
                    tool_events,
                    self._session_id,
                )
                yield TurnComplete(text=text, session_id=self._session_id)
                return

            if line_count <= 5 or (line_count % 50 == 0):
                log.debug(
                    "[kimi-proto] unhandled line=%d keys=%s method=%s type=%s sample=%s",
                    line_count,
                    sorted(obj.keys()) if isinstance(obj, dict) else [],
                    method_norm,
                    event_type,
                    line[:200].rstrip(),
                )

        if rpc_error is not None:
            log.warning(
                "[kimi-proto] rpc error after lines=%d text_events=%d methods=%s error=%s",
                line_count,
                text_events,
                methods_seen,
                rpc_error,
            )
            raise RuntimeError(f"kimi RPC error: {rpc_error}")
        if streamed_text:
            # Some kimi builds end the stdout stream without an explicit TurnEnd event.
            # Preserve real-time behavior by completing the turn from streamed text.
            log.warning(
                "[kimi-proto] eof without completion marker; using streamed text lines=%d text_events=%d methods=%s",
                line_count,
                text_events,
                methods_seen,
            )
            yield TurnComplete(text="".join(streamed_text), session_id=self._session_id)
            return

        log.error(
            "[kimi-proto] eof before completion and no text lines=%d methods=%s",
            line_count,
            methods_seen,
        )
        raise RuntimeError("kimi process ended before TurnEnd")

    async def cancel(self) -> None:
        if self.proc and self.proc.stdin:
            try:
                await self._send_rpc("cancel")
            except (BrokenPipeError, ConnectionResetError):
                pass

    def get_session_id(self) -> str | None:
        return self._session_id
