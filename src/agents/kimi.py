import os
import tempfile
import uuid

from .base import BaseAgent
from .prompts import build_agent_system_prompt
from .protocols.kimi import KimiProtocol


class KimiAgent(BaseAgent):
    name = "kimi"
    agent_type = "kimi"
    permission_mode: str = "bypass"
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

    def _build_persistent_args(self) -> list[str]:
        if self.session_id is None:
            self.session_id = str(uuid.uuid4())
        args = ["kimi", "--wire"]
        if self.permission_mode == "bypass":
            args.append("--yolo")
        args.extend([
            "--agent-file", self._ensure_agent_file(),
            "--session", self.session_id,
        ])
        return args

    def _build_persistent_resume_args(self, session_id: str) -> list[str]:
        sid = session_id or self.session_id
        if sid is None:
            sid = str(uuid.uuid4())
        self.session_id = sid
        args = ["kimi", "--wire"]
        if self.permission_mode == "bypass":
            args.append("--yolo")
        args.extend([
            "--agent-file", self._ensure_agent_file(),
            "--session", sid,
        ])
        return args

    def _get_protocol(self) -> KimiProtocol:
        return KimiProtocol(
            permission_mode=self.permission_mode,
            permission_timeout=self.permission_timeout,
        )
