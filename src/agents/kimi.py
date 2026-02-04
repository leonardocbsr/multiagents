import json
import logging
import os
import re
import tempfile
import uuid
from typing import Any

from .base import BaseAgent, _tool_badge, _extract_tool_detail, _try_parse_json
from .prompts import build_agent_system_prompt

log = logging.getLogger("multiagents")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class KimiAgent(BaseAgent):
    name = "kimi"
    agent_type = "kimi"
    _last_cumulative: str = ""
    _agent_dir: str | None = None

    _cached_model: str | None = None
    _cached_prompt: str | None = None
    _cached_project_dir: str | None = None
    _cached_name: str | None = None

    def _ensure_agent_file(self) -> str:
        """Write temp agent YAML + system prompt so Kimi gets proper system-level instructions."""
        needs_write = self._agent_dir is None
        if not needs_write:
            needs_write = (self.model != self._cached_model or
                           self.system_prompt_override != self._cached_prompt or
                           self.project_dir != self._cached_project_dir or
                           self.name != self._cached_name)
        if needs_write:
            if self._agent_dir is None:
                self._agent_dir = tempfile.mkdtemp(prefix="multiagents-kimi-agent-")
            prompt_path = os.path.join(self._agent_dir, "system.md")
            agent_path = os.path.join(self._agent_dir, "agent.yaml")
            with open(prompt_path, "w") as f:
                f.write(build_agent_system_prompt(self.project_dir, self.system_prompt_override, agent_name=self.name))
                f.write("\n\n${KIMI_AGENTS_MD}\n")
            with open(agent_path, "w") as f:
                lines = [
                    "version: 1\n",
                    "agent:\n",
                    "  extend: default\n",
                    f"  system_prompt_path: {prompt_path}\n",
                ]
                if self.model:
                    lines.append(f"  model: {self.model}\n")
                f.writelines(lines)
            self._cached_model = self.model
            self._cached_prompt = self.system_prompt_override
            self._cached_project_dir = self.project_dir
            self._cached_name = self.name
        return os.path.join(self._agent_dir, "agent.yaml")

    def cleanup(self) -> None:
        import shutil
        if self._agent_dir and os.path.isdir(self._agent_dir):
            shutil.rmtree(self._agent_dir, ignore_errors=True)
            self._agent_dir = None
        super().cleanup()

    def _cli_flags(self) -> list[str]:
        return [
            "--print", "--output-format", "stream-json",
            "--agent-file", self._ensure_agent_file(),
        ]

    def _build_args(self, prompt: str) -> list[str]:
        return ["kimi", "--command", prompt, *self._cli_flags()]

    def _build_first_args(self, prompt: str) -> list[str]:
        if self.session_id is None:
            self.session_id = str(uuid.uuid4())
        return [
            "kimi", "--command", prompt,
            *self._cli_flags(),
            "--session", self.session_id,
        ]

    def _build_resume_args(self, prompt: str) -> list[str]:
        return [
            "kimi", "--command", prompt,
            *self._cli_flags(),
            "--session", self.session_id,
        ]

    def _reset_stream_state(self) -> None:
        self._last_cumulative = ""

    def _parse_stream_line(self, line: str) -> str | None:
        obj = _try_parse_json(line, agent=self.name, context="stream")
        if obj is None:
            return None
        # Skip tool result events — these are intermediate outputs (file
        # contents, command results) that shouldn't be displayed directly.
        if obj.get("role") == "tool":
            return None
        # Tool call events → emit badges
        tool_calls = obj.get("tool_calls", [])
        if tool_calls:
            badges = []
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except (json.JSONDecodeError, ValueError):
                    log.warning("[%s] failed to parse tool arguments for %s", self.name, name)
                    args = {}
                badges.append(_tool_badge(name, _extract_tool_detail(args)))
            return "".join(badges)
        # Delta events — strip ANSI codes
        if obj.get("type") == "text":
            text = _strip_ansi(obj.get("text", ""))
            return text or None
        # Content array events (assistant messages only)
        parts = obj.get("content", [])
        if not isinstance(parts, list) or not parts:
            return None
        chunks: list[str] = []
        # Extract thinking content
        for p in parts:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "think" and p.get("think"):
                chunks.append(f"<thinking>{p['think']}</thinking>\n")
        # Extract text delta — strip ANSI codes
        texts = [p["text"] for p in parts if isinstance(p, dict) and p.get("type") == "text"]
        if texts:
            cumulative = "".join(texts)
            delta = cumulative[len(self._last_cumulative):]
            self._last_cumulative = cumulative
            if delta:
                delta = _strip_ansi(delta)
                if delta:
                    chunks.append(delta)
        return "".join(chunks) if chunks else None

    def _parse_output(self, stdout: str) -> tuple[str, Any]:
        lines = stdout.strip().split("\n")
        # Try JSONL first (stream-json format)
        objects = []
        for line in lines:
            if not line.strip():
                continue
            obj = _try_parse_json(line, agent=self.name, context="parse_output")
            if obj is not None:
                objects.append(obj)
        # Legacy: single JSON object with content array
        if len(objects) == 1 and isinstance(objects[0], dict) and "content" in objects[0]:
            parts = objects[0].get("content", [])
            text_parts = [p["text"] for p in parts if p.get("type") == "text"]
            return "\n".join(text_parts), objects[0]
        # Stream-json: multiple JSONL events
        text_parts = []
        for obj in objects:
            if isinstance(obj, dict):
                if obj.get("type") == "text":
                    text_parts.append(obj.get("text", ""))
                elif obj.get("role") == "assistant":
                    for p in obj.get("content", []):
                        if isinstance(p, dict) and p.get("type") == "text":
                            text_parts.append(p["text"])
        return "\n".join(text_parts), objects
