import json
import logging
from typing import Any

from .base import BaseAgent, _tool_badge, _short_path, _try_parse_json
from .prompts import build_agent_system_prompt

log = logging.getLogger("multiagents")


class CodexAgent(BaseAgent):
    name = "codex"
    agent_type = "codex"

    def _should_retry_without_session(
        self,
        *,
        returncode: int | None,
        stderr: str,
        stdout: str,
        timed_out: bool,
        attempted_resume: bool,
    ) -> bool:
        """Retry with a fresh thread when Codex reports context window exhaustion.

        The error appears in stdout JSON:
          {"type":"error","message":"Codex ran out of room in the model's context window..."}
        Only retry if we were resuming a thread — a fresh thread with the same
        prompt won't have less history.
        """
        if not attempted_resume:
            return False
        if "context window" in stdout:
            return True
        # Generic resume failure (invalid/expired thread ID)
        if returncode and returncode != 0:
            return True
        return False

    # Enable auto-truncation so the Responses API drops older turns instead of
    # failing with "context window exhausted".  persistence="save-all" keeps
    # sessions resumable.
    _HISTORY_CONFIG = 'history={persistence="save-all", truncation="auto"}'

    def _dev_instructions_config(self) -> str:
        """Return the -c flag value that injects our system prompt as developer_instructions."""
        prompt = build_agent_system_prompt(self.project_dir, self.system_prompt_override, agent_name=self.name)
        return f"developer_instructions={json.dumps(prompt)}"

    def _cli_flags(self) -> list[str]:
        flags = [
            "--skip-git-repo-check", "--json",
            "-c", self._HISTORY_CONFIG,
            "-c", self._dev_instructions_config(),
        ]
        if self.model:
            flags.extend(["-c", f'model="{self.model}"'])
        return flags

    def _build_args(self, prompt: str) -> list[str]:
        return ["codex", "exec", prompt, *self._cli_flags()]

    def _build_first_args(self, prompt: str) -> list[str]:
        return ["codex", "exec", prompt, "--dangerously-bypass-approvals-and-sandbox", *self._cli_flags()]

    def _build_resume_args(self, prompt: str) -> list[str]:
        return ["codex", "exec", "resume", self.session_id, prompt, "--dangerously-bypass-approvals-and-sandbox", *self._cli_flags()]

    def _parse_stream_line(self, line: str) -> str | None:
        obj = _try_parse_json(line, agent=self.name, context="stream")
        if obj is None:
            return None
        if obj.get("type") == "response.output_text.delta":
            return obj.get("delta", "")
        # Command execution start → emit badge
        if obj.get("type") == "item.started":
            item = obj.get("item", {})
            if item.get("type") == "command_execution":
                cmd = item.get("command", "")
                if " -lc " in cmd:
                    cmd = cmd.split(" -lc ", 1)[1].strip("'\"")
                short = cmd[:80] + "..." if len(cmd) > 80 else cmd
                return _tool_badge("Run", short)
        if obj.get("type") == "item.completed":
            item = obj.get("item", {})
            item_type = item.get("type", "")
            # Reasoning → thinking tag
            if item_type == "reasoning":
                text = item.get("text", "")
                if text:
                    return f"<thinking>{text}</thinking>\n"
            # Command execution completed → show output
            if item_type == "command_execution":
                output = item.get("aggregated_output", "")
                if output:
                    short = output[:500] + "..." if len(output) > 500 else output
                    return f"<system>{short.rstrip()}</system>\n"
            # File changes → emit badges
            if item_type == "file_change":
                badges = []
                for ch in item.get("changes", []):
                    kind = ch.get("kind", "update")
                    label = "Write" if kind == "create" else "Update"
                    badges.append(_tool_badge(label, _short_path(ch.get("path", ""))))
                return "".join(badges) if badges else None
            # Agent message text
            text = item.get("text")
            if text:
                return text + "\n\n"
        return None

    def _extract_session_id(self, stdout: str) -> str | None:
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            obj = _try_parse_json(line, agent=self.name, context="extract_session_id")
            if obj is None:
                continue
            if obj.get("type") == "thread.started":
                return obj.get("thread_id")
        return None

    def _parse_output(self, stdout: str) -> tuple[str, Any]:
        lines = stdout.strip().split("\n")
        events = []
        for line in lines:
            if not line.strip():
                continue
            obj = _try_parse_json(line, agent=self.name, context="parse_output")
            if obj is not None:
                events.append(obj)
        for event in events:
            if event.get("type") == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    return item.get("text", ""), events
        return "", events
