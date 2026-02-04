from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable

from ..agents.base import AgentNotice as BaseAgentNotice, AgentResponse, BaseAgent
from .events import (
    AgentCompleted,
    AgentInterrupted,
    AgentNotice,
    AgentPromptAssembled,
    AgentStderr,
    AgentStreamChunk,
    ChatEvent,
    DiscussionEnded,
    RoundEnded,
    RoundPaused,
    RoundStarted,
    UserMessageReceived,
)
from .router import detect_pass, extract_shareable, format_prompt, format_round_prompt, format_session_context, PLACEHOLDER

log = logging.getLogger("multiagents")


class ChatRoom:
    def __init__(
        self,
        agents: list[BaseAgent],
        timeout: float = 1800.0,
        context_provider: "Callable[[str], dict[str, str]] | None" = None,
        working_dir: str = "",
        participants: list[dict] | None = None,
        roles: dict[str, str] | None = None,
    ) -> None:
        self.agents = agents
        self.timeout = timeout
        self.history: list[dict] = []
        self.context_provider = context_provider
        self.working_dir = working_dir
        self.participants = participants
        self.roles = roles or {}
        self._user_queue: asyncio.Queue[str] = asyncio.Queue()
        self._stop_events: dict[str, asyncio.Event] = {}
        self._restart_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._resume_event = asyncio.Event()
        self._any_stopped_this_round = False
        self._pause_on_stop = True
        self._add_agent_queue: asyncio.Queue[BaseAgent] = asyncio.Queue()
        self._remove_agent_queue: asyncio.Queue[str] = asyncio.Queue()
        self._dm_debounce_timers: dict[str, asyncio.TimerHandle] = {}
        self._dm_debounce_texts: dict[str, list[str]] = {}

    def add_agent(self, agent: BaseAgent) -> None:
        """Queue an agent to join. If a round is in progress, it joins immediately."""
        self._add_agent_queue.put_nowait(agent)

    def remove_agent(self, name: str) -> None:
        """Queue an agent for removal. Stops it if mid-round."""
        self._remove_agent_queue.put_nowait(name)
        event = self._stop_events.get(name)
        if event:
            event.set()

    def inject_user_message(self, text: str) -> None:
        self._user_queue.put_nowait(text)

    def stop_agent(self, name: str) -> None:
        """Stop a single agent mid-round by setting its stop event."""
        event = self._stop_events.get(name)
        if event:
            event.set()

    def stop_round(self, pause: bool = True) -> None:
        """Stop all running agents in the current round."""
        self._pause_on_stop = pause
        for event in self._stop_events.values():
            event.set()

    def resume(self) -> None:
        """Resume after a paused round (triggered by stop)."""
        self._resume_event.set()

    async def restart_agent(self, name: str, dm_text: str) -> None:
        """Stop an agent and queue it for restart with a DM prompt.

        Multiple DMs within 500ms are coalesced into a single restart
        with the messages joined by newlines.
        """
        # Cancel any pending debounce timer for this agent
        timer = self._dm_debounce_timers.pop(name, None)
        if timer is not None:
            timer.cancel()

        # Accumulate text
        self._dm_debounce_texts.setdefault(name, []).append(dm_text)

        # Stop the agent immediately (idempotent if already stopped)
        event = self._stop_events.get(name)
        if event:
            event.set()

        # Schedule the actual restart after 500ms of silence
        loop = asyncio.get_running_loop()

        def _fire() -> None:
            self._dm_debounce_timers.pop(name, None)
            texts = self._dm_debounce_texts.pop(name, [])
            combined = "\n".join(texts)
            self._restart_queue.put_nowait((name, combined))

        self._dm_debounce_timers[name] = loop.call_later(0.5, _fire)

    def _cancel_debounce_timers(self) -> None:
        """Cancel all pending debounce timers and discard accumulated texts."""
        for timer in self._dm_debounce_timers.values():
            timer.cancel()
        self._dm_debounce_timers.clear()
        self._dm_debounce_texts.clear()

    def _drain_restart_queue(self) -> None:
        """Discard any stale restart requests from a previous round."""
        while not self._restart_queue.empty():
            try:
                self._restart_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def run(
        self, initial_prompt: str | None = None, start_round: int = 0,
    ) -> AsyncGenerator[ChatEvent, None]:
        if initial_prompt:
            self.history.append({"role": "user", "content": initial_prompt})
        round_number = start_round

        while True:
            # Check for user injection before each round
            while not self._user_queue.empty():
                text = self._user_queue.get_nowait()
                self.history.append({"role": "user", "content": text})
                yield UserMessageReceived(text=text)

            round_number += 1
            self._any_stopped_this_round = False
            self._pause_on_stop = True
            agent_names = [a.name for a in self.agents]
            yield RoundStarted(round_number=round_number, agents=agent_names)

            # Run all agents concurrently
            responses: dict[str, AgentResponse] = {}
            passed: dict[str, bool] = {}

            event_queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue()

            # Create per-agent stop events for this round
            self._stop_events = {a.name: asyncio.Event() for a in self.agents}
            # Discard stale restart requests from previous rounds
            self._drain_restart_queue()

            async def run_agent(agent: BaseAgent, prompt_override: str | None = None) -> None:
                if prompt_override is not None:
                    prompt = (
                        f"## Direct Message from User\n{prompt_override}\n\n"
                        "Respond to this directive. If you have nothing to add, respond with [PASS]."
                    )
                else:
                    extra = self.context_provider(agent.name) if self.context_provider else None
                    agent_role = self.roles.get(agent.name, "")
                    if agent.session_id is not None:
                        # Agent has a CLI session — send only the round delta
                        prompt = format_round_prompt(
                            self.history, agent.name, round_number,
                            extra_context=extra,
                        )
                    else:
                        # Stateless agent or first run — send full prompt
                        prompt = format_prompt(
                            self.history, agent.name, round_number,
                            has_session=False,
                            extra_context=extra,
                            working_dir=self.working_dir,
                            participants=self.participants,
                            role=agent_role,
                        )

                    # Emit prompt visibility event
                    prompt_sections = dict(extra) if extra else {}
                    # Add system prompt on first run (no session yet)
                    if agent.session_id is None:
                        prompt_sections["system"] = format_session_context(
                            agent.name, working_dir=self.working_dir,
                            participants=self.participants, role=agent_role,
                        )
                    # Add the round delta (the assembled round prompt minus extra context)
                    prompt_sections["round_delta"] = format_round_prompt(
                        self.history, agent.name, round_number,
                    )
                    await event_queue.put(AgentPromptAssembled(
                        agent_name=agent.name,
                        round_number=round_number,
                        sections=prompt_sections,
                    ))

                stop_event = self._stop_events[agent.name]
                partial_chunks: list[str] = []

                async def consume_stream() -> None:
                    async for item in agent.stream(prompt, self.timeout):
                        if isinstance(item, AgentResponse):
                            is_pass = detect_pass(item.response)
                            responses[agent.name] = item
                            passed[agent.name] = is_pass
                            if item.stderr:
                                await event_queue.put(
                                    AgentStderr(agent_name=agent.name, text=item.stderr)
                                )
                            await event_queue.put(
                                AgentCompleted(
                                    agent_name=agent.name,
                                    response=item,
                                    passed=is_pass,
                                )
                            )
                        elif isinstance(item, BaseAgentNotice):
                            await event_queue.put(
                                AgentNotice(agent_name=item.agent, message=item.message)
                            )
                        elif isinstance(item, str):
                            partial_chunks.append(item)
                            await event_queue.put(
                                AgentStreamChunk(agent_name=agent.name, text=item)
                            )

                try:
                    stream_task = asyncio.create_task(consume_stream())
                    stop_task = asyncio.create_task(stop_event.wait())

                    done, pending = await asyncio.wait(
                        [stream_task, stop_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for p in pending:
                        p.cancel()
                        try:
                            await p
                        except (asyncio.CancelledError, Exception):
                            pass

                    # If stream_task finished, re-raise any exception it had
                    if stream_task in done:
                        exc = stream_task.exception()
                        if exc is not None:
                            raise exc

                    # If stop event won (agent was stopped)
                    if stop_event.is_set() and agent.name not in responses:
                        partial_text = "".join(partial_chunks).strip() or "(stopped)"
                        resp = AgentResponse(
                            agent=agent.name,
                            response=partial_text,
                            success=False,
                            latency_ms=0,
                        )
                        responses[agent.name] = resp
                        passed[agent.name] = False
                        await event_queue.put(
                            AgentCompleted(
                                agent_name=agent.name,
                                response=resp,
                                passed=False,
                                stopped=True,
                            )
                        )

                except asyncio.CancelledError:
                    log.info("[%s] cancelled", agent.name)
                    raise
                except Exception as e:
                    log.exception("[%s] error: %s", agent.name, e)
                    if agent.name not in responses:
                        responses[agent.name] = AgentResponse(
                            agent=agent.name,
                            response=str(e),
                            success=False,
                            latency_ms=0,
                        )
                        passed[agent.name] = False
                        await event_queue.put(
                            AgentCompleted(
                                agent_name=agent.name,
                                response=responses[agent.name],
                                passed=False,
                            )
                        )
                finally:
                    if agent.name not in responses:
                        responses[agent.name] = AgentResponse(
                            agent=agent.name,
                            response="Agent did not produce a response",
                            success=False,
                            latency_ms=0,
                        )
                        passed[agent.name] = False
                        await event_queue.put(
                            AgentCompleted(
                                agent_name=agent.name,
                                response=responses[agent.name],
                                passed=False,
                            )
                        )

            tasks = [asyncio.create_task(run_agent(a)) for a in self.agents]

            # Yield events as they arrive
            done_count = 0
            pending_restarts: dict[str, str] = {}
            deferred_stops: dict[str, AgentCompleted] = {}
            total = len(self.agents)
            max_parse_timeout = max(
                (getattr(a, "parse_timeout", 0.0) for a in self.agents),
                default=0.0,
            )
            max_hard_timeout = max(
                (getattr(a, "hard_timeout", 0.0) or 0.0 for a in self.agents),
                default=0.0,
            )
            base_timeout = max(self.timeout, max_hard_timeout)
            round_timeout = base_timeout + max_parse_timeout + 5.0
            loop = asyncio.get_running_loop()
            deadline = loop.time() + round_timeout
            while done_count < total:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    log.warning("round %d timed out waiting for agents", round_number)
                    break

                # Process mid-round agent additions
                while not self._add_agent_queue.empty():
                    try:
                        new_agent = self._add_agent_queue.get_nowait()
                        self.agents.append(new_agent)
                        self._stop_events[new_agent.name] = asyncio.Event()
                        new_task = asyncio.create_task(run_agent(new_agent))
                        tasks.append(new_task)
                        total += 1
                    except asyncio.QueueEmpty:
                        break

                # Process mid-round agent removals
                while not self._remove_agent_queue.empty():
                    try:
                        remove_name = self._remove_agent_queue.get_nowait()
                        self.agents = [a for a in self.agents if a.name != remove_name]
                        if remove_name in responses:
                            # Already completed this round — just remove from tracking
                            done_count -= 1
                            total -= 1
                            responses.pop(remove_name, None)
                            passed.pop(remove_name, None)
                        else:
                            # Still running — stop event already set via remove_agent(), just adjust total
                            total -= 1
                        total = max(total, 0)
                    except asyncio.QueueEmpty:
                        break

                # Check for pending restart requests (non-blocking)
                try:
                    restart_name, dm_text = self._restart_queue.get_nowait()
                    pending_restarts[restart_name] = dm_text
                except asyncio.QueueEmpty:
                    pass

                # Handle restarts for agents that already completed this round
                # (their AgentCompleted was already yielded, so the event-based
                # restart path below will never fire for them).
                for agent_key in list(pending_restarts):
                    if agent_key in responses:
                        dm_text = pending_restarts.pop(agent_key)
                        partial = responses[agent_key].response if responses[agent_key] else ""
                        yield AgentInterrupted(
                            agent_name=agent_key,
                            round_number=round_number,
                            partial_text=partial,
                        )
                        responses.pop(agent_key, None)
                        passed.pop(agent_key, None)
                        done_count -= 1
                        agent_obj = next((a for a in self.agents if a.name == agent_key), None)
                        if agent_obj:
                            self._stop_events[agent_key] = asyncio.Event()
                            new_task = asyncio.create_task(run_agent(agent_obj, prompt_override=dm_text))
                            tasks.append(new_task)

                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=min(0.1, remaining))
                except asyncio.TimeoutError:
                    # Also keep looping if debounce timers are pending (restart about to fire)
                    has_pending = pending_restarts or self._dm_debounce_texts or deferred_stops
                    if all(t.done() for t in tasks) and event_queue.empty() and not has_pending:
                        break
                    # Check if any deferred stops can now be processed
                    for agent_key in list(deferred_stops):
                        if agent_key in pending_restarts:
                            evt = deferred_stops.pop(agent_key)
                            await event_queue.put(evt)
                    continue
                if event is None:
                    break

                # If this is a stopped completion and a restart is pending or debounce
                # is still accumulating, handle the restart.
                if isinstance(event, AgentCompleted) and event.stopped:
                    agent_key = event.agent_name
                    # Check both the fired queue (pending_restarts) and the
                    # debounce buffer (texts not yet fired).
                    if agent_key in pending_restarts:
                        dm_text = pending_restarts.pop(agent_key)
                    elif agent_key in self._dm_debounce_texts:
                        # Debounce hasn't fired yet — defer this event until it does
                        deferred_stops[agent_key] = event
                        continue
                    else:
                        dm_text = None

                    if dm_text is not None:
                        partial = event.response.response if event.response else ""
                        yield AgentInterrupted(
                            agent_name=agent_key,
                            round_number=round_number,
                            partial_text=partial,
                        )
                        responses.pop(agent_key, None)
                        passed.pop(agent_key, None)
                        agent_obj = next((a for a in self.agents if a.name == agent_key), None)
                        if agent_obj:
                            self._stop_events[agent_key] = asyncio.Event()
                            new_task = asyncio.create_task(run_agent(agent_obj, prompt_override=dm_text))
                            tasks.append(new_task)
                        continue

                # Also handle: completed (not stopped) agent that has a pending restart
                # This covers the case where a DM arrives after the agent already finished
                if isinstance(event, AgentCompleted) and not event.stopped:
                    agent_key = event.agent_name
                    if agent_key in pending_restarts:
                        dm_text = pending_restarts.pop(agent_key)
                    elif agent_key in self._dm_debounce_texts:
                        deferred_stops[agent_key] = event
                        continue
                    else:
                        dm_text = None

                    if dm_text is not None:
                        partial = event.response.response if event.response else ""
                        yield AgentInterrupted(
                            agent_name=agent_key,
                            round_number=round_number,
                            partial_text=partial,
                        )
                        responses.pop(agent_key, None)
                        passed.pop(agent_key, None)
                        agent_obj = next((a for a in self.agents if a.name == agent_key), None)
                        if agent_obj:
                            self._stop_events[agent_key] = asyncio.Event()
                            new_task = asyncio.create_task(run_agent(agent_obj, prompt_override=dm_text))
                            tasks.append(new_task)
                        continue

                yield event
                if isinstance(event, AgentCompleted):
                    done_count += 1
                    if event.stopped:
                        self._any_stopped_this_round = True

            if done_count < total:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                while not event_queue.empty():
                    event = event_queue.get_nowait()
                    if event is None:
                        break
                    yield event
                    if isinstance(event, AgentCompleted):
                        done_count += 1
                for agent in self.agents:
                    if agent.name not in responses:
                        resp = AgentResponse(
                            agent=agent.name,
                            response="Agent did not complete before timeout",
                            success=False,
                            latency_ms=0,
                        )
                        responses[agent.name] = resp
                        passed[agent.name] = False
                        yield AgentCompleted(
                            agent_name=agent.name,
                            response=resp,
                            passed=False,
                        )
            else:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Clear stop events and debounce timers after round completes
            self._stop_events = {}
            self._cancel_debounce_timers()

            # Add non-pass responses to history (extracting only shareable content)
            all_passed = True
            for agent in self.agents:
                resp = responses.get(agent.name)
                if resp and not passed.get(agent.name, False):
                    shareable = extract_shareable(resp.response)
                    self.history.append({
                        "role": agent.name,
                        "content": shareable or PLACEHOLDER,
                        "round": round_number,
                    })
                    all_passed = False
                elif resp and passed.get(agent.name, False):
                    self.history.append({
                        "role": agent.name,
                        "content": "[PASS]",
                        "round": round_number,
                    })

            yield RoundEnded(round_number=round_number, all_passed=all_passed)

            # Process between-round additions/removals
            while not self._add_agent_queue.empty():
                try:
                    new_agent = self._add_agent_queue.get_nowait()
                    self.agents.append(new_agent)
                except asyncio.QueueEmpty:
                    break
            while not self._remove_agent_queue.empty():
                try:
                    remove_name = self._remove_agent_queue.get_nowait()
                    self.agents = [a for a in self.agents if a.name != remove_name]
                except asyncio.QueueEmpty:
                    break

            if all_passed:
                yield DiscussionEnded(reason="all_passed")
                return

            # If any agent was stopped this round, pause and wait for resume
            if self._any_stopped_this_round and self._pause_on_stop:
                self._any_stopped_this_round = False
                self._resume_event.clear()
                yield RoundPaused(round_number=round_number)
                # Wait for resume signal or user message
                while not self._resume_event.is_set() and self._user_queue.empty():
                    await asyncio.sleep(0.1)
                self._resume_event.clear()

            # Check for user messages before next round
            if not self._user_queue.empty():
                continue

            # Small delay to allow user injection window
            await asyncio.sleep(0.05)
