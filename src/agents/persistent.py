"""PersistentAgent — long-lived agent process with bidirectional pipe."""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, AsyncIterator

from .protocols.base import AgentEvent, ProcessRestarted, TurnComplete

if TYPE_CHECKING:
    from .protocols.base import ProtocolAdapter

log = logging.getLogger("multiagents")

_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds


def _spawn_preview(args: list[str], max_chars: int = 220) -> str:
    """Compact process argv for logs to avoid dumping huge prompt/config payloads."""
    if not args:
        return ""
    head = args[:3]
    preview = " ".join(head)
    if len(args) > 3:
        preview += f" ... (+{len(args) - 3} args)"
    if len(preview) > max_chars:
        preview = preview[: max_chars - 3] + "..."
    return preview


class PersistentAgent:
    """Wraps a ProtocolAdapter with process lifecycle management.

    The process stays alive between turns. If it dies, it is respawned
    with session resume args and the failed message is retried.
    """

    def __init__(
        self,
        agent_name: str,
        build_args_fn: Callable[[], list[str]],
        build_resume_args_fn: Callable[[str], list[str]],
        get_protocol_fn: Callable[[], "ProtocolAdapter"],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.agent_name = agent_name
        self._build_args = build_args_fn
        self._build_resume_args = build_resume_args_fn
        self._get_protocol = get_protocol_fn
        self._cwd = cwd
        self._env = env
        self.proc: asyncio.subprocess.Process | None = None
        self.protocol = None
        self._session_id: str | None = None
        self._stderr_task: asyncio.Task | None = None
        self._stderr_buffer: list[str] = []

    async def ensure_running(self) -> None:
        """Spawn the process if not already running."""
        if self.proc and self.proc.returncode is None:
            return

        # Build args — resume if we have a session
        if self._session_id:
            args = self._build_resume_args(self._session_id)
        else:
            args = self._build_args()

        log.info("[%s] spawning persistent process: %s", self.agent_name, _spawn_preview(args))

        env = None
        if self._env:
            env = {**os.environ, **self._env}

        self.proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
            env=env,
            limit=10 * 1024 * 1024,
        )

        # Create a new protocol instance and wire it to the process
        self.protocol = self._get_protocol()
        self.protocol.proc = self.proc

        # Drain stderr in background
        self._stderr_buffer = []
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        # Run protocol handshake
        if self._session_id and hasattr(self.protocol, "start_resume"):
            await self.protocol.start_resume(self._session_id)
        else:
            await self.protocol.start()

    async def _drain_stderr(self) -> None:
        """Read stderr in the background to prevent pipe buffer deadlock."""
        try:
            assert self.proc and self.proc.stderr
            async for raw_line in self.proc.stderr:
                line = raw_line.decode()
                self._stderr_buffer.append(line)
                if self.agent_name.lower() == "kimi":
                    log.info("[%s][stderr] %s", self.agent_name, line.rstrip())
                else:
                    log.debug("[%s] stderr: %s", self.agent_name, line.rstrip())
        except Exception:
            pass

    async def send_and_stream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """Send a message and yield response events, with crash recovery."""
        retries = 0
        while retries <= _MAX_RETRIES:
            try:
                await self.ensure_running()
                await self.protocol.send_message(prompt)
                saw_turn_complete = False
                async for event in self.protocol.read_events():
                    if isinstance(event, TurnComplete) and event.session_id:
                        self._session_id = event.session_id
                    if isinstance(event, TurnComplete):
                        saw_turn_complete = True
                    yield event
                if not saw_turn_complete:
                    raise RuntimeError("turn ended without completion marker")
                return
            except (BrokenPipeError, ConnectionResetError, ProcessLookupError, OSError, RuntimeError) as e:
                retries += 1
                if retries > _MAX_RETRIES:
                    log.error("[%s] max retries exceeded after process crash", self.agent_name)
                    raise
                backoff = _BACKOFF_BASE * (2 ** (retries - 1))
                log.warning(
                    "[%s] process died (%s), respawning in %.1fs (retry %d/%d)",
                    self.agent_name, e, backoff, retries, _MAX_RETRIES,
                )
                yield ProcessRestarted(reason=str(e), retry=retries)
                await asyncio.sleep(backoff)
                # Kill stale process if still around
                if self.proc and self.proc.returncode is None:
                    self.proc.kill()
                    await self.proc.wait()
                self.proc = None
                self.protocol = None

    async def cancel(self) -> None:
        """Interrupt the current turn."""
        if self.protocol:
            await self.protocol.cancel()

    async def shutdown(self) -> None:
        """Graceful shutdown of the persistent process."""
        if self.protocol:
            try:
                await self.protocol.shutdown()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass

        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()

        self.proc = None
        self.protocol = None

    def get_stderr(self) -> str:
        return "".join(self._stderr_buffer)
