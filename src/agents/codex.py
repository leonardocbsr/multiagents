import json
import logging

from .base import BaseAgent
from .prompts import build_agent_system_prompt
from .protocols.codex import CodexProtocol

log = logging.getLogger("multiagents")


class CodexAgent(BaseAgent):
    name = "codex"
    agent_type = "codex"
    permission_mode: str = "bypass"
    _HISTORY_CONFIG = 'history={persistence="save-all", truncation="auto"}'

    def _dev_instructions_config(self) -> str:
        """Return the -c flag value that injects our system prompt as developer_instructions."""
        prompt = build_agent_system_prompt(self.project_dir, self.system_prompt_override, agent_name=self.name)
        return f"developer_instructions={json.dumps(prompt)}"

    def _build_persistent_args(self) -> list[str]:
        args = ["codex", "app-server",
                "-c", self._HISTORY_CONFIG,
                "-c", self._dev_instructions_config()]
        if self.model:
            args.extend(["-c", f'model="{self.model}"'])
        return args

    def _build_persistent_resume_args(self, session_id: str) -> list[str]:
        # Codex resume is done at the protocol level (thread/resume), not CLI args
        return self._build_persistent_args()

    def _get_protocol(self) -> CodexProtocol:
        policy_map = {
            "bypass": ("never", "danger-full-access"),
            "auto": ("auto-edit", "danger-full-access"),
            "manual": ("suggest", "danger-full-access"),
        }
        policy, sandbox = policy_map.get(self.permission_mode, ("never", "danger-full-access"))
        return CodexProtocol(approval_policy=policy, sandbox=sandbox)
