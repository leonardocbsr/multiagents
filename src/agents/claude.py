import json
import os
import uuid

from .base import BaseAgent
from .prompts import build_agent_system_prompt
from .protocols.claude import ClaudeProtocol

_CLAUDE_BASE_FLAGS = [
    "--verbose",
    "--output-format", "stream-json",
    "--disable-slash-commands",
]


class ClaudeAgent(BaseAgent):
    name = "claude"
    agent_type = "claude"
    permission_mode: str = "bypass"

    def _cli_flags(self) -> list[str]:
        flags = ["--system-prompt", build_agent_system_prompt(self.project_dir, self.system_prompt_override, agent_name=self.name), *_CLAUDE_BASE_FLAGS]
        if self.model:
            flags.extend(["--model", self.model])

        if self.permission_mode == "bypass":
            flags.extend(["--setting-sources", "", "--dangerously-skip-permissions"])
        else:
            # Use dontAsk mode — auto-denies unless pre-approved
            flags.extend(["--setting-sources", "", "--permission-mode", "dontAsk"])
            if self.permission_mode == "auto":
                # Pre-approve read-only tools
                flags.extend(["--settings", json.dumps({
                    "permissions": {"allow": ["Read", "Glob", "Grep", "WebSearch", "WebFetch"]}
                })])
            # In "manual" mode, no pre-approvals — everything gets denied and forwarded to user
        return flags

    def _get_cwd(self) -> str:
        if self.project_dir:
            return self.project_dir
        if self._work_dir is None:
            self._work_dir = f"/tmp/multiagents-claude-{uuid.uuid4()}"
            os.makedirs(self._work_dir, exist_ok=True)
        return self._work_dir

    def _build_persistent_args(self) -> list[str]:
        return ["claude", "-p", "--input-format", "stream-json", *self._cli_flags()]

    def _build_persistent_resume_args(self, session_id: str) -> list[str]:
        return ["claude", "-p", "--input-format", "stream-json", "--resume", session_id, *self._cli_flags()]

    def _get_protocol(self) -> ClaudeProtocol:
        return ClaudeProtocol()
