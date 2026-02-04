import json
import os
import uuid
from typing import Any

from .base import BaseAgent, _tool_badge, _extract_tool_detail, _try_parse_json
from .prompts import build_agent_system_prompt

_CLAUDE_BASE_FLAGS = [
    "--verbose",
    "--output-format", "stream-json",
    "--disable-slash-commands",
    "--setting-sources", "",
    "--dangerously-skip-permissions",
]


class ClaudeAgent(BaseAgent):
    name = "claude"
    agent_type = "claude"
    _last_cumulative: str = ""
    _last_thinking: str = ""
    _seen_tools: int = 0
    _last_message_id: str | None = None

    def _cli_flags(self) -> list[str]:
        flags = ["--system-prompt", build_agent_system_prompt(self.project_dir, self.system_prompt_override, agent_name=self.name), *_CLAUDE_BASE_FLAGS]
        if self.model:
            flags.extend(["--model", self.model])
        return flags

    def _build_args(self, prompt: str) -> list[str]:
        return ["claude", "-p", prompt, *self._cli_flags()]

    def _get_cwd(self) -> str:
        if self.project_dir:
            return self.project_dir
        if self._work_dir is None:
            self._work_dir = f"/tmp/multiagents-claude-{uuid.uuid4()}"
            os.makedirs(self._work_dir, exist_ok=True)
        return self._work_dir

    def _reset_stream_state(self) -> None:
        self._last_cumulative = ""
        self._last_thinking = ""
        self._seen_tools = 0
        self._last_message_id = None

    def _build_first_args(self, prompt: str) -> list[str]:
        return ["claude", "-p", prompt, *self._cli_flags()]

    def _build_resume_args(self, prompt: str) -> list[str]:
        return [
            "claude",
            "--resume", self.session_id,
            "-p", prompt,
            *self._cli_flags(),
        ]

    def _should_retry_without_session(
        self,
        *,
        returncode: int | None,
        stderr: str,
        stdout: str,
        timed_out: bool,
        attempted_resume: bool,
    ) -> bool:
        """Check if we should retry without a session ID.
        
        Claude CLI hangs/exit when given an invalid session ID.
        We detect this by checking for empty stderr and exit code != 0
        when we were trying to resume a session.
        """
        if not attempted_resume:
            return False
        if timed_out:
            # Invalid --resume can block waiting for interactive input.
            # Only retry if no stdout was produced.
            return not stdout or len(stdout.strip()) == 0
        if returncode and returncode != 0:
            # When --resume with invalid session, Claude may emit initial
            # JSON to stdout before failing.  Don't require stdout to be
            # empty — retry whenever stderr is empty (no clear error reason).
            return not stderr or len(stderr.strip()) == 0
        return False

    def _extract_session_id(self, stdout: str) -> str | None:
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            obj = _try_parse_json(line, agent=self.name, context="extract_session_id")
            if obj is None:
                continue
            if obj.get("type") == "result":
                sid = obj.get("session_id")
                if sid:
                    return sid
        return None

    def _parse_stream_line(self, line: str) -> str | None:
        obj = _try_parse_json(line, agent=self.name, context="stream")
        if obj is None:
            return None
        msg = obj.get("message", {})
        content = msg.get("content", [])
        if not content:
            return None

        # Detect new assistant turn (content resets after tool use).
        # Each turn has a unique message ID; when it changes, the cumulative
        # content array starts fresh so our accumulators must reset.
        msg_id = msg.get("id")
        if msg_id and msg_id != self._last_message_id:
            self._last_message_id = msg_id
            self._last_cumulative = ""
            self._last_thinking = ""
            self._seen_tools = 0

        chunks: list[str] = []

        # Thinking events → emit delta as <thinking> tags
        thinking_parts = [p.get("thinking", "") for p in content if p.get("type") == "thinking"]
        if thinking_parts:
            cumulative_thinking = "".join(thinking_parts)
            delta_thinking = cumulative_thinking[len(self._last_thinking):]
            self._last_thinking = cumulative_thinking
            if delta_thinking.strip():
                chunks.append(f"<thinking>{delta_thinking}</thinking>\n")

        # Tool use events → emit badges only for newly-seen tools
        # (Claude stream-json sends cumulative content arrays, so previous
        # tool_use parts reappear in every subsequent event.)
        tools = [p for p in content if p.get("type") == "tool_use"]
        new_tools = tools[self._seen_tools:]
        if new_tools:
            for t in new_tools:
                chunks.append(_tool_badge(t["name"], _extract_tool_detail(t.get("input", {}))))
            self._seen_tools = len(tools)

        # Text events → emit delta
        texts = [part["text"] for part in content if part.get("type") == "text"]
        if texts:
            cumulative = "".join(texts)
            delta = cumulative[len(self._last_cumulative):]
            self._last_cumulative = cumulative
            if delta:
                chunks.append(delta)

        return "".join(chunks) if chunks else None

    def _parse_output(self, stdout: str) -> tuple[str, Any]:
        # stream-json is JSONL, but also handle legacy JSON array
        lines = stdout.strip().split("\n")
        objects = []
        for line in lines:
            if not line.strip():
                continue
            obj = _try_parse_json(line, agent=self.name, context="parse_output")
            if obj is not None:
                objects.append(obj)
        # If it parsed as a single JSON array (legacy format), unwrap
        if len(objects) == 1 and isinstance(objects[0], list):
            objects = objects[0]
        for obj in objects:
            if isinstance(obj, dict) and obj.get("type") == "result":
                return obj.get("result", ""), objects
        return "", objects
