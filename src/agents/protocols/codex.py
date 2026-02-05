"""Codex app-server protocol adapter.

Wire format (per codex app-server generate-json-schema):
  The protocol is JSON-RPC 2.0 but the "jsonrpc":"2.0" header is OMITTED.
  Messages are newline-delimited JSON over stdio.

  Requests:  {"method": str, "id": int, "params": obj}
  Responses: {"id": int, "result": obj} or {"id": int, "error": {...}}
  Notifications: {"method": str, "params": obj}  (no "id")
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from .base import AgentEvent, ProtocolAdapter, TextDelta, ThinkingDelta, ToolBadge, ToolOutput, TurnComplete
from ..base import _short_path

log = logging.getLogger("multiagents")


def _rpc_request(id: int, method: str, params: dict) -> str:
    """Build a JSON-RPC request (no jsonrpc header per Codex wire format)."""
    return json.dumps({"method": method, "id": id, "params": params}) + "\n"


def _rpc_notification(method: str, params: dict | None = None) -> str:
    """Build a JSON-RPC notification (no jsonrpc header per Codex wire format)."""
    msg: dict = {"method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg) + "\n"


def _extract_file_change_label(kind: dict | str) -> str:
    """Extract label from a PatchChangeKind (object with "type" field, or legacy string)."""
    if isinstance(kind, dict):
        t = kind.get("type", "update")
    else:
        t = kind
    return "Write" if t == "add" else "Update"


class CodexProtocol(ProtocolAdapter):
    """Adapter for Codex CLI app-server."""

    _thread_id: str | None = None
    _turn_id: str | None = None

    def __init__(self, approval_policy: str = "never", sandbox: str = "danger-full-access") -> None:
        self._id_counter = 0
        self._approval_policy = approval_policy
        self._sandbox = sandbox

    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter

    @staticmethod
    def _extract_thread_id(result: dict | None) -> str | None:
        if not isinstance(result, dict):
            return None
        # Direct threadId field
        if isinstance(result.get("threadId"), str):
            return result["threadId"]
        # Nested thread object (thread/start and thread/resume responses)
        thread = result.get("thread")
        if isinstance(thread, dict):
            tid = thread.get("id")
            if isinstance(tid, str):
                return tid
        return None

    async def _send_rpc(self, data: str) -> None:
        assert self.proc and self.proc.stdin
        try:
            payload = json.loads(data)
            log.debug("[codex-proto] -> method=%s id=%s", payload.get("method"), payload.get("id"))
        except (json.JSONDecodeError, ValueError):
            log.debug("[codex-proto] -> raw=%s", data[:200].rstrip())
        self.proc.stdin.write(data.encode())
        await self.proc.stdin.drain()

    async def _read_line(self) -> dict | None:
        assert self.proc and self.proc.stdout
        raw = await self.proc.stdout.readline()
        if not raw:
            return None
        try:
            return json.loads(raw.decode())
        except (json.JSONDecodeError, ValueError):
            log.debug("[codex-proto] json parse failed: %s", raw[:200])
            return None

    async def _wait_for_result(self, expected_id: int, timeout: float = 30.0) -> dict | None:
        """Read lines until we get a response with the expected id (with timeout)."""
        log.debug("[codex-proto] waiting for response id=%d timeout=%.1fs", expected_id, timeout)
        try:
            async with asyncio.timeout(timeout):
                while True:
                    obj = await self._read_line()
                    if obj is None:
                        log.warning("[codex-proto] stream ended while waiting for response id=%d", expected_id)
                        return None
                    if obj.get("id") == expected_id:
                        log.debug("[codex-proto] <- response id=%d keys=%s", expected_id, ",".join(sorted(obj.keys())))
                        return obj
        except asyncio.TimeoutError:
            log.warning("[codex-proto] timeout waiting for response id=%d", expected_id)
            return None

    async def _wait_for_thread_id(self, request_id: int, timeout: float = 30.0) -> tuple[str | None, dict | None]:
        """Wait for a thread id coming from response or notification."""
        response_obj: dict | None = None
        log.debug("[codex-proto] waiting for thread id request_id=%d timeout=%.1fs", request_id, timeout)
        try:
            async with asyncio.timeout(timeout):
                while True:
                    obj = await self._read_line()
                    if obj is None:
                        log.warning("[codex-proto] stream ended while waiting for thread id request_id=%d", request_id)
                        return None, response_obj

                    if obj.get("id") == request_id:
                        response_obj = obj
                        if "error" in obj:
                            raise RuntimeError(str(obj["error"]))
                        thread_id = self._extract_thread_id(obj.get("result"))
                        if thread_id:
                            return thread_id, response_obj
                        continue

                    method = obj.get("method", "")
                    if method == "thread/started":
                        thread_id = self._extract_thread_id(obj.get("params"))
                        if thread_id:
                            return thread_id, response_obj
        except asyncio.TimeoutError:
            log.warning("[codex-proto] timeout waiting for thread id (request id=%d)", request_id)
        return None, response_obj

    async def _handshake(self) -> None:
        """Send initialize -> initialized handshake."""
        init_id = self._next_id()
        await self._send_rpc(_rpc_request(init_id, "initialize", {
            "clientInfo": {"name": "multiagents", "version": "1.0.0"},
        }))

        result = await self._wait_for_result(init_id)
        if result is None:
            raise RuntimeError("Codex initialize handshake failed (no response)")
        if "error" in result:
            raise RuntimeError(f"Codex initialize failed: {result['error']}")

        await self._send_rpc(_rpc_notification("initialized"))

    async def start(self) -> None:
        """Run initialize handshake and start a thread."""
        await self._handshake()

        req_id = self._next_id()
        await self._send_rpc(_rpc_request(req_id, "thread/start", {
            "approvalPolicy": self._approval_policy,
            "sandbox": self._sandbox,
        }))

        thread, result = await self._wait_for_thread_id(req_id)
        if not thread:
            raise RuntimeError(f"Codex thread/start returned no threadId: {result}")
        self._thread_id = thread
        log.info("[codex-proto] started thread %s", self._thread_id)

    async def start_resume(self, thread_id: str) -> None:
        """Resume an existing thread after respawn."""
        await self._handshake()

        resume_id = self._next_id()
        await self._send_rpc(_rpc_request(resume_id, "thread/resume", {
            "threadId": thread_id,
            "approvalPolicy": self._approval_policy,
            "sandbox": self._sandbox,
        }))
        resumed_thread, result = await self._wait_for_thread_id(resume_id)
        if resumed_thread:
            self._thread_id = resumed_thread
        elif result and "error" in result:
            raise RuntimeError(f"Codex thread/resume failed: {result['error']}")
        else:
            # Resume acknowledged but no explicit id in payload — use the one we sent.
            self._thread_id = thread_id
        log.info("[codex-proto] resumed thread %s", self._thread_id)

    async def send_message(self, text: str) -> None:
        if not self._thread_id:
            raise RuntimeError("Must call start() or start_resume() first")
        req_id = self._next_id()
        await self._send_rpc(_rpc_request(req_id, "turn/start", {
            "threadId": self._thread_id,
            "input": [{"type": "text", "text": text}],
        }))
        log.info("[codex-proto] turn/start sent id=%d thread=%s chars=%d", req_id, self._thread_id, len(text))

    async def read_events(self) -> AsyncIterator[AgentEvent]:
        assert self.proc and self.proc.stdout

        async for raw_line in self.proc.stdout:
            line = raw_line.decode()
            if not line.strip():
                continue

            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                log.debug("[codex-proto] json parse failed: %s", line[:200].rstrip())
                continue

            method = obj.get("method", "")
            params = obj.get("params", {})

            # ── Turn lifecycle ──────────────────────────────────────

            if method == "turn/started":
                turn = params.get("turn", {})
                tid = turn.get("id")
                if isinstance(tid, str):
                    self._turn_id = tid
                    log.debug("[codex-proto] turn/started turnId=%s", tid)
                continue

            if method == "turn/completed":
                turn = params.get("turn", {}) if isinstance(params, dict) else {}
                status = turn.get("status")
                turn_error = turn.get("error") if isinstance(turn, dict) else None
                error_message = ""
                if isinstance(turn_error, dict):
                    error_message = str(turn_error.get("message") or "")
                success = status in (None, "completed")

                log.info(
                    "[codex-proto] turn/completed thread=%s status=%s",
                    self._thread_id,
                    status or "<unknown>",
                )
                self._turn_id = None
                yield TurnComplete(
                    session_id=self._thread_id,
                    success=success,
                    error=error_message or None,
                )
                return

            # ── Streaming deltas ────────────────────────────────────

            # Agent text output (primary response text)
            if method == "item/agentMessage/delta":
                delta = params.get("delta", "")
                if delta:
                    yield TextDelta(text=delta)
                continue

            # Reasoning text delta — streams during thinking (can last minutes)
            if method == "item/reasoning/textDelta":
                delta = params.get("delta", "")
                if delta:
                    yield ThinkingDelta(text=delta)
                continue

            # Reasoning summary delta — streams the visible summary
            if method == "item/reasoning/summaryTextDelta":
                delta = params.get("delta", "")
                if delta:
                    yield ThinkingDelta(text=delta)
                continue

            # Reasoning summary part added — new summary section started
            if method == "item/reasoning/summaryPartAdded":
                continue

            # Plan delta — streams plan text (experimental)
            if method == "item/plan/delta":
                delta = params.get("delta", "")
                if delta:
                    yield ThinkingDelta(text=delta)
                continue

            # Command execution output delta — command stdout/stderr
            if method == "item/commandExecution/outputDelta":
                delta = params.get("delta", "")
                if delta:
                    yield ToolOutput(tool_name="Run", text=delta[:500])
                continue

            # Terminal interaction during command execution
            if method == "item/commandExecution/terminalInteraction":
                output = params.get("output", "")
                if output:
                    yield ToolOutput(tool_name="Run", text=output[:500])
                continue

            # File change output delta
            if method == "item/fileChange/outputDelta":
                delta = params.get("delta", "")
                if delta:
                    yield ToolOutput(tool_name="Write", text=delta[:500])
                continue

            # MCP tool call progress
            if method == "item/mcpToolCall/progress":
                message = params.get("message", "")
                if message:
                    yield ToolBadge(label="MCP", detail=message[:80])
                continue

            # ── Item started ────────────────────────────────────────

            if method == "item/started":
                item = params.get("item", {})
                itype = item.get("type", "")
                if itype == "commandExecution":
                    cmd = item.get("command", "")
                    if " -lc " in cmd:
                        cmd = cmd.split(" -lc ", 1)[1].strip("'\"")
                    short = cmd[:80] + "..." if len(cmd) > 80 else cmd
                    yield ToolBadge(label="Run", detail=short)
                elif itype == "mcpToolCall":
                    tool = item.get("tool", "")
                    server = item.get("server", "")
                    label = f"{server}/{tool}" if server else tool
                    yield ToolBadge(label="MCP", detail=label[:80])
                elif itype == "webSearch":
                    query = item.get("query", "")
                    yield ToolBadge(label="Search", detail=query[:80])
                elif itype == "reasoning":
                    yield ToolBadge(label="Thinking", detail="")
                elif itype == "fileChange":
                    changes = item.get("changes", [])
                    if changes:
                        for ch in changes:
                            label = _extract_file_change_label(ch.get("kind", {}))
                            yield ToolBadge(label=label, detail=_short_path(ch.get("path", "")))
                    else:
                        yield ToolBadge(label="Write", detail="")
                elif itype == "plan":
                    yield ToolBadge(label="Planning", detail="")
                elif itype == "collabAgentToolCall":
                    tool = item.get("tool", "")
                    yield ToolBadge(label="Agent", detail=tool)
                elif itype == "contextCompaction":
                    yield ToolBadge(label="Compacting", detail="")
                elif itype == "imageView":
                    path = item.get("path", "")
                    yield ToolBadge(label="Image", detail=_short_path(path) if path else "")
                elif itype not in ("agentMessage", "userMessage"):
                    log.debug("[codex-proto] unhandled item/started type=%s", itype)
                continue

            # ── Item completed ──────────────────────────────────────

            if method == "item/completed":
                item = params.get("item", {})
                item_type = item.get("type", "")

                if item_type == "agentMessage":
                    # Full text already streamed via item/agentMessage/delta.
                    pass
                elif item_type == "reasoning":
                    # Summary already streamed via deltas; emit final if present
                    # and not already streamed.
                    parts = item.get("summary", []) or item.get("content", [])
                    text = "\n".join(parts) if parts else ""
                    if text:
                        yield ThinkingDelta(text=text)
                elif item_type == "plan":
                    # Plan text already streamed via item/plan/delta.
                    pass
                elif item_type == "commandExecution":
                    cmd = item.get("command", "")
                    if " -lc " in cmd:
                        cmd = cmd.split(" -lc ", 1)[1].strip("'\"")
                    short = cmd[:80] + "..." if len(cmd) > 80 else cmd
                    yield ToolBadge(label="Run", detail=short)
                elif item_type == "fileChange":
                    for ch in item.get("changes", []):
                        label = _extract_file_change_label(ch.get("kind", {}))
                        yield ToolBadge(label=label, detail=_short_path(ch.get("path", "")))
                elif item_type == "mcpToolCall":
                    tool = item.get("tool", "")
                    server = item.get("server", "")
                    label = f"{server}/{tool}" if server else tool
                    yield ToolBadge(label="MCP", detail=label[:80])
                elif item_type == "webSearch":
                    query = item.get("query", "")
                    yield ToolBadge(label="Search", detail=query[:80])
                elif item_type == "collabAgentToolCall":
                    tool = item.get("tool", "")
                    yield ToolBadge(label="Agent", detail=tool)
                continue

            # ── JSON-RPC responses and errors ───────────────────────

            if "id" in obj and "result" in obj:
                continue

            if method == "error":
                msg = params.get("error", {}).get("message", str(params))
                log.warning("[codex-proto] error notification: %s", msg)
                continue

            # ── Informational notifications (no UI) ─────────────────

            if method in (
                "thread/started", "thread/name/updated",
                "thread/tokenUsage/updated", "thread/compacted",
                "turn/diff/updated", "turn/plan/updated",
                "account/updated", "account/rateLimits/updated",
                "account/login/completed", "configWarning",
                "deprecationNotice", "sessionConfigured",
                "mcpServer/oauthLogin/completed",
                "authStatusChange", "loginChatGptComplete",
                "rawResponseItem/completed",
                "windows/worldWritableWarning",
            ):
                continue

            # Log anything we haven't explicitly handled
            if method:
                log.debug("[codex-proto] unhandled method=%s keys=%s", method, ",".join(sorted(obj.keys())))

        raise RuntimeError("codex process ended before turn/completed")

    async def cancel(self) -> None:
        if self.proc and self.proc.stdin:
            if not self._thread_id:
                return
            cancel_id = self._next_id()
            params: dict = {"threadId": self._thread_id}
            if self._turn_id:
                params["turnId"] = self._turn_id
            else:
                log.warning("[codex-proto] cancel called without turnId, sending threadId only")
            try:
                await self._send_rpc(_rpc_request(cancel_id, "turn/interrupt", params))
                log.info("[codex-proto] turn/interrupt sent id=%d thread=%s turn=%s",
                         cancel_id, self._thread_id, self._turn_id or "<unknown>")
            except (BrokenPipeError, ConnectionResetError):
                pass

    async def shutdown(self) -> None:
        if self.proc and self.proc.stdin:
            try:
                shutdown_id = self._next_id()
                await self._send_rpc(_rpc_request(shutdown_id, "shutdown", {}))
                await self._send_rpc(_rpc_notification("exit"))
                log.debug("[codex-proto] shutdown sent id=%d", shutdown_id)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def get_session_id(self) -> str | None:
        return self._thread_id
