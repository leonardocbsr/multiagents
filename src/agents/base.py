import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

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

_MAX_COLLECTED_CHARS = 2 * 1024 * 1024  # In-memory buffer cap before spilling to disk.
_MAX_PARSE_CHARS = 20 * 1024 * 1024  # Hard cap to avoid huge parse payloads.


def _stdout_tail(stdout: str, limit: int = 400) -> str:
    if not stdout:
        return ""
    tail = stdout[-limit:]
    return tail.replace("\r", "\\r").replace("\n", "\\n")


class HardTimeoutError(Exception):
    """Raised when an agent exceeds its hard runtime limit."""


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


def _try_parse_json(line: str, *, agent: str, context: str) -> Any | None:
    """Try to parse a JSON line, logging at DEBUG on failure. Returns None on error."""
    try:
        return json.loads(line)
    except (json.JSONDecodeError, ValueError):
        truncated = line[:200] + "..." if len(line) > 200 else line
        log.debug("[%s] json parse failed (%s): %s", agent, context, truncated.rstrip())
        return None


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
    parse_timeout: float = 120.0
    hard_timeout: float | None = None
    extra_env: dict[str, str] | None = None

    @abstractmethod
    def _build_args(self, prompt: str) -> list[str]:
        """Return the CLI argv for this agent."""

    @abstractmethod
    def _parse_output(self, stdout: str) -> tuple[str, Any]:
        """Parse decoded stdout into (text, raw_data)."""

    def _parse_stream_line(self, line: str) -> str | None:
        """Parse a single streamed line into display text. Return None to skip."""
        return line

    def _build_first_args(self, prompt: str) -> list[str]:
        """CLI args for the first prompt (no session yet). Default: same as _build_args."""
        return self._build_args(prompt)

    def _build_resume_args(self, prompt: str) -> list[str]:
        """CLI args to resume an existing session. Default: same as _build_args."""
        return self._build_args(prompt)

    def _extract_session_id(self, stdout: str) -> str | None:
        """Extract session ID from completed stdout. Default: None (no session tracking)."""
        return None

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

    def _reset_stream_state(self) -> None:
        """Reset per-stream state. Override in subclasses that track cumulative text."""

    async def _try_compact(self, *, stdout: str, stderr: str) -> bool:
        """Try to compact/repair the session before retrying.

        Called when a retry is about to happen.  If this returns True the retry
        keeps the current ``session_id`` (compaction succeeded).  If False,
        ``session_id`` is cleared and a fresh session starts.

        Default: False (no compaction support).
        """
        return False

    def _should_retry_without_session(
        self,
        *,
        returncode: int | None,
        stderr: str,
        stdout: str,
        timed_out: bool,
        attempted_resume: bool,
    ) -> bool:
        """Check if we should retry without session ID after failure.

        Override in subclasses that support session resumption.
        Default: don't retry.
        """
        return False

    async def stream(
        self, prompt: str, timeout: float = 1800.0,
    ) -> AsyncGenerator[str | AgentResponse, None]:
        """Stream stdout lines, then yield a final AgentResponse."""
        self._reset_stream_state()
        start = time.monotonic()
        collected: list[str] = []
        collected_size = 0
        spill_file: tempfile.NamedTemporaryFile | None = None
        spill_path: str | None = None
        stdout_seen = False
        proc: asyncio.subprocess.Process | None = None
        hard_deadline = start + self.hard_timeout if self.hard_timeout else None
        did_retry = False
        def _append_stdout(chunk: str) -> None:
            nonlocal collected_size, spill_file, spill_path, stdout_seen
            stdout_seen = True
            if spill_file is None and collected_size + len(chunk) > _MAX_COLLECTED_CHARS:
                spill_file = tempfile.NamedTemporaryFile(mode="w+", delete=False)
                spill_path = spill_file.name
                if collected:
                    spill_file.write("".join(collected))
                    collected.clear()
                    collected_size = 0
            if spill_file:
                spill_file.write(chunk)
            else:
                collected.append(chunk)
                collected_size += len(chunk)

        def _reset_stdout_buffer() -> None:
            nonlocal collected_size, spill_file, spill_path, stdout_seen
            collected.clear()
            collected_size = 0
            stdout_seen = False
            if spill_file is not None:
                try:
                    spill_file.close()
                finally:
                    if spill_path:
                        try:
                            os.unlink(spill_path)
                        except OSError:
                            pass
            spill_file = None
            spill_path = None

        def _final_stdout() -> tuple[str, int]:
            nonlocal spill_file, spill_path, collected_size
            if spill_file is not None:
                spill_file.flush()
                spill_file.close()
                spill_file = None
                file_size = os.path.getsize(spill_path) if spill_path else 0
                tail = "".join(collected)
                total_size = file_size + len(tail)
                if total_size > _MAX_PARSE_CHARS:
                    return "", total_size
                file_text = ""
                if spill_path:
                    with open(spill_path, "r") as handle:
                        file_text = handle.read()
                return file_text + tail, total_size
            total_size = collected_size
            if total_size > _MAX_PARSE_CHARS:
                return "", total_size
            return "".join(collected), total_size

        try:
            while True:
                used_resume = self.session_id is not None
                args = self._build_resume_args(prompt) if used_resume else self._build_first_args(prompt)
                binary = args[0]
                if shutil.which(binary) is None:
                    raise FileNotFoundError(
                        f"Agent '{self.name}' requires '{binary}' but it was not found on PATH. "
                        f"Please install it or check your configuration."
                    )
                log.info("[%s] started%s", self.name, " (retry)" if did_retry else "")
                log.debug("[%s] exec: %s", self.name, " ".join(args))
                env = None
                if self.extra_env:
                    env = {**os.environ, **self.extra_env}
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL,
                    cwd=self._get_cwd(),
                    env=env,
                    limit=10 * 1024 * 1024,  # 10 MB — agent JSON lines can be large
                )
                timed_out = False
                try:
                    loop = asyncio.get_event_loop()
                    async with asyncio.timeout(timeout) as deadline:
                        async for raw_line in proc.stdout:
                            line = raw_line.decode()
                            deadline.reschedule(loop.time() + timeout)
                            _append_stdout(line)
                            log.debug("[%s] stdout: %s", self.name, line.rstrip())
                            parsed = self._parse_stream_line(line)
                            if parsed is not None:
                                yield parsed
                            if hard_deadline and time.monotonic() > hard_deadline:
                                raise HardTimeoutError("hard timeout")
                        await proc.wait()
                except asyncio.TimeoutError:
                    timed_out = True
                    proc.kill()
                    await proc.wait()

                stdout = "".join(collected)
                if stdout_seen and not stdout:
                    stdout = "<spilled>"
                stderr_text = ""
                if proc.stderr is not None:
                    stderr_text = (await proc.stderr.read()).decode()

                if timed_out:
                    should_retry = (
                        not did_retry
                        and self._should_retry_without_session(
                            returncode=proc.returncode,
                            stderr=stderr_text,
                            stdout=stdout,
                            timed_out=True,
                            attempted_resume=used_resume,
                        )
                    )
                    if should_retry:
                        compacted = await self._try_compact(stdout=stdout, stderr=stderr_text)
                        if compacted:
                            log.info("[%s] compacted session, retrying with same thread", self.name)
                            yield AgentNotice(agent=self.name, message="Context compacted — retrying with same thread")
                        else:
                            self._log_metric(
                                "agent_resume_retry",
                                reason="timeout",
                                attempted_resume=used_resume,
                            )
                            log.info("[%s] retrying without session_id after idle timeout", self.name)
                            yield AgentNotice(agent=self.name, message="Session reset — starting fresh thread (timeout)")
                            self.session_id = None
                        self._reset_stream_state()
                        _reset_stdout_buffer()
                        did_retry = True
                        continue
                    log.warning("[%s] idle timeout after %.1fs", self.name, timeout)
                    yield AgentResponse(
                        agent=self.name,
                        response="Timeout",
                        success=False,
                        latency_ms=(time.monotonic() - start) * 1000,
                        stderr=stderr_text or None,
                    )
                    return

                if proc.returncode != 0:
                    log.warning(
                        "[%s] exit %d — stderr: %s — stdout_chars=%d stdout_tail=%s",
                        self.name, proc.returncode, stderr_text.rstrip(),
                        len(stdout), _stdout_tail(stdout),
                    )
                    should_retry = (
                        not did_retry
                        and self._should_retry_without_session(
                            returncode=proc.returncode,
                            stderr=stderr_text,
                            stdout=stdout,
                            timed_out=False,
                            attempted_resume=used_resume,
                        )
                    )
                    if should_retry:
                        compacted = await self._try_compact(stdout=stdout, stderr=stderr_text)
                        if compacted:
                            log.info("[%s] compacted session, retrying with same thread", self.name)
                            yield AgentNotice(agent=self.name, message="Context compacted — retrying with same thread")
                        else:
                            reason = "context window exhausted" if "context window" in stdout else "session expired"
                            self._log_metric(
                                "agent_resume_retry",
                                reason="exit",
                                returncode=proc.returncode,
                                attempted_resume=used_resume,
                            )
                            log.info("[%s] retrying without session_id (%s)", self.name, reason)
                            yield AgentNotice(agent=self.name, message=f"Session reset — starting fresh thread ({reason})")
                            self.session_id = None
                        self._reset_stream_state()
                        _reset_stdout_buffer()
                        did_retry = True
                        continue
                    yield AgentResponse(
                        agent=self.name,
                        response=stderr_text,
                        success=False,
                        latency_ms=(time.monotonic() - start) * 1000,
                        stderr=stderr_text,
                    )
                    return
                break

            stdout, stdout_size = _final_stdout()
            if stdout_size > _MAX_PARSE_CHARS:
                log.warning(
                    "[%s] output too large to parse chars=%d limit=%d",
                    self.name,
                    stdout_size,
                    _MAX_PARSE_CHARS,
                )
                yield AgentResponse(
                    agent=self.name,
                    response="Output too large to parse",
                    success=False,
                    latency_ms=(time.monotonic() - start) * 1000,
                )
                return
            try:
                text, raw_data = await asyncio.wait_for(
                    asyncio.to_thread(self._parse_output, stdout),
                    timeout=self.parse_timeout,
                )
            except asyncio.TimeoutError:
                log.warning(
                    "[%s] parse timeout reason=parse_timeout after=%.1fs stdout_chars=%d stdout_tail=%s",
                    self.name,
                    self.parse_timeout,
                    len(stdout),
                    _stdout_tail(stdout),
                )
                yield AgentResponse(
                    agent=self.name,
                    response="Output parsing timed out",
                    success=False,
                    latency_ms=(time.monotonic() - start) * 1000,
                )
                return
            except Exception as e:
                log.exception(
                    "[%s] parse error reason=parse_error stdout_chars=%d stdout_tail=%s error=%s",
                    self.name,
                    len(stdout),
                    _stdout_tail(stdout),
                    e,
                )
                yield AgentResponse(
                    agent=self.name,
                    response=str(e),
                    success=False,
                    latency_ms=(time.monotonic() - start) * 1000,
                )
                return

            if self.session_id is None:
                self.session_id = self._extract_session_id(stdout)

            latency_ms = (time.monotonic() - start) * 1000
            log.info("[%s] finished — %.0fms", self.name, latency_ms)

            if not text:
                yield AgentResponse(
                    agent=self.name,
                    response="No output parsed from agent response",
                    success=False,
                    latency_ms=latency_ms,
                    raw_output=raw_data,
                )
            else:
                yield AgentResponse(
                    agent=self.name,
                    response=text,
                    success=True,
                    latency_ms=latency_ms,
                    raw_output=raw_data,
                    session_id=self.session_id,
                )
        except asyncio.TimeoutError:
            log.warning("[%s] idle timeout after %.1fs", self.name, timeout)
            yield AgentResponse(
                agent=self.name,
                response="Timeout",
                success=False,
                latency_ms=timeout * 1000,
            )
        except HardTimeoutError:
            if proc and proc.returncode is None:
                proc.kill()
                await proc.wait()
            log.warning("[%s] hard timeout after %.1fs", self.name, (time.monotonic() - start))
            yield AgentResponse(
                agent=self.name,
                response="Hard timeout",
                success=False,
                latency_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            log.exception("[%s] error: %s", self.name, e)
            yield AgentResponse(
                agent=self.name,
                response=str(e),
                success=False,
                latency_ms=(time.monotonic() - start) * 1000,
            )
        finally:
            _reset_stdout_buffer()
