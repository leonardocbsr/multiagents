import asyncio
import json
import logging
import os
import shutil
import time
from abc import ABC
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .persistent import PersistentAgent
    from .protocols.base import ProtocolAdapter

log = logging.getLogger("multiagents")

# Maps CLI tool names to user-friendly display labels.
_TOOL_LABELS: dict[str, str] = {
    "Read": "Read", "Edit": "Update", "Write": "Write", "Bash": "Run",
    "Glob": "Search", "Grep": "Search", "WebFetch": "Fetch",
    "ReadFile": "Read", "Shell": "Run", "EditFile": "Update",
    "WriteFile": "Write", "read_file": "Read", "edit_file": "Update",
    "write_file": "Write",
    # Kimi Code tool names
    "StrReplaceFile": "Update", "CreateFile": "Write",
    "ListDir": "Search", "SearchFiles": "Search",
    "SetTodoList": "Plan",
}

def _tool_badge(tool_name: str, detail: str = "") -> str:
    """Return a <tool> tag that the frontend renders as an inline badge."""
    label = _TOOL_LABELS.get(tool_name, tool_name)
    body = f"{label} {detail}".strip() if detail else label
    return f"<tool>{body}</tool>\n"


def _short_path(p: str) -> str:
    """Shorten an absolute file path or command for display."""
    if not p:
        return ""
    home = os.path.expanduser("~")
    if p.startswith(home):
        return "~" + p[len(home):]
    return p


def _extract_tool_detail(params: dict) -> str:
    """Extract and shorten the most relevant detail from tool parameters."""
    raw = params.get("path") or params.get("file_path") or params.get("command", "")
    return _short_path(raw)



@dataclass
class AgentNotice:
    """In-band notice from an agent (e.g. session reset). Yielded alongside str/AgentResponse."""
    agent: str
    message: str


@dataclass
class AgentResponse:
    agent: str
    response: str
    success: bool
    latency_ms: float
    raw_output: dict[str, Any] | None = field(default=None)
    session_id: str | None = field(default=None)
    stderr: str | None = field(default=None)


class BaseAgent(ABC):
    name: str
    agent_type: str = ""  # "claude", "codex", "kimi"
    model: str | None = None
    system_prompt_override: str | None = None
    session_id: str | None = None
    project_dir: str | None = None
    _work_dir: str | None = None
    parse_timeout: float = 1200.0
    hard_timeout: float | None = None
    extra_env: dict[str, str] | None = None
    _persistent: "PersistentAgent | None" = None

    def _get_cwd(self) -> str | None:
        """Working directory for the subprocess. None = inherit current dir."""
        return self.project_dir

    def _system_prompt_prefix(self) -> str:
        """Return the working-directory section of the system prompt."""
        if self.project_dir:
            return (
                f"IMPORTANT: The project directory is {self.project_dir}. "
                "You are working directly in this directory."
            )
        return (
            "IMPORTANT: You are running in an isolated working directory, NOT the project "
            "root. Always use absolute file paths (e.g. /Users/user/project/src/file.py) "
            "when reading, editing, or referencing project files. Relative paths will "
            "resolve to your temp directory and fail."
        )

    def _log_metric(self, name: str, **fields: object) -> None:
        payload = {"metric": name, "ts": time.time(), "agent": self.name, **fields}
        log.info("metric %s", json.dumps(payload, separators=(",", ":"), sort_keys=True))

    def cleanup(self) -> None:
        """Remove the agent's temp working directory if one was created."""
        if self._work_dir and os.path.isdir(self._work_dir):
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._work_dir = None

    # -- Persistent pipe hooks (override in subclasses) --

    def _build_persistent_args(self) -> list[str]:
        """CLI args to spawn the persistent process (no prompt — it goes via stdin)."""
        raise NotImplementedError(f"{type(self).__name__} does not support persistent pipes")

    def _build_persistent_resume_args(self, session_id: str) -> list[str]:
        """CLI args to respawn with session resume after a crash."""
        return self._build_persistent_args()

    def _get_protocol(self) -> "ProtocolAdapter":
        """Return a fresh ProtocolAdapter instance for this agent type."""
        raise NotImplementedError(f"{type(self).__name__} does not support persistent pipes")

    def _ensure_persistent(self) -> "PersistentAgent":
        if self._persistent is None:
            from .persistent import PersistentAgent as PA
            self._persistent = PA(
                agent_name=self.name,
                build_args_fn=self._build_persistent_args,
                build_resume_args_fn=self._build_persistent_resume_args,
                get_protocol_fn=self._get_protocol,
                cwd=self._get_cwd(),
                env=self.extra_env,
            )
        return self._persistent

    async def _stream_persistent(
        self, prompt: str, timeout: float,
    ) -> AsyncGenerator[str | AgentResponse | AgentNotice, None]:
        """Persistent-pipe streaming: delegates to PersistentAgent, translates events."""
        from .protocols.base import TextDelta, ThinkingDelta, ToolBadge, TurnComplete

        pa = self._ensure_persistent()
        start = time.monotonic()
        full_text_parts: list[str] = []

        turn_timeout = timeout
        if self.parse_timeout and self.parse_timeout > 0:
            turn_timeout = min(turn_timeout, self.parse_timeout)
        try:
            async with asyncio.timeout(turn_timeout):
                async for event in pa.send_and_stream(prompt):
                    if isinstance(event, TextDelta):
                        full_text_parts.append(event.text)
                        yield event.text
                    elif isinstance(event, ThinkingDelta):
                        yield f"<thinking>{event.text}</thinking>\n"
                    elif isinstance(event, ToolBadge):
                        yield _tool_badge(event.label, event.detail)
                    elif isinstance(event, TurnComplete):
                        text = event.text or "".join(full_text_parts)
                        self.session_id = event.session_id or pa._session_id or self.session_id
                        yield AgentResponse(
                            agent=self.name,
                            response=text,
                            success=True,
                            latency_ms=(time.monotonic() - start) * 1000,
                            session_id=self.session_id,
                            stderr=pa.get_stderr() or None,
                        )
        except asyncio.TimeoutError:
            log.warning("[%s] persistent turn timed out after %.1fs", self.name, turn_timeout)
            try:
                await pa.cancel()
            except Exception:
                log.debug("[%s] cancel after timeout failed", self.name, exc_info=True)
            yield AgentResponse(
                agent=self.name,
                response="Timeout",
                success=False,
                latency_ms=(time.monotonic() - start) * 1000,
                stderr=pa.get_stderr() or None,
            )
        except Exception as e:
            log.exception("[%s] persistent stream error: %s", self.name, e)
            yield AgentResponse(
                agent=self.name,
                response=str(e),
                success=False,
                latency_ms=(time.monotonic() - start) * 1000,
            )

    async def shutdown_persistent(self) -> None:
        """Shut down the persistent agent process if running."""
        if self._persistent:
            await self._persistent.shutdown()
            self._persistent = None

    async def cancel_turn(self) -> None:
        """Best-effort cancellation of the current turn."""
        if self._persistent:
            await self._persistent.cancel()

    async def stream(
        self, prompt: str, timeout: float = 1800.0,
    ) -> AsyncGenerator[str | AgentResponse, None]:
        """Stream stdout lines, then yield a final AgentResponse."""
        async for item in self._stream_persistent(prompt, timeout):
            yield item
