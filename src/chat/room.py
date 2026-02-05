from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from collections.abc import AsyncGenerator, Callable

from ..agents.base import AgentNotice as BaseAgentNotice, AgentPermissionRequest, AgentResponse, BaseAgent
from .events import (
    AgentCompleted,
    AgentDeliveryAcked,
    AgentInterrupted,
    AgentNotice,
    AgentPermissionRequested,
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

_PERSISTENT_REPLY_DIRECTIVE = (
    "Respond directly. Put all user-visible content inside <Share>...</Share>. "
    "If no action is needed, respond with exactly [PASS]."
)
_RELAY_DEDUP_COOLDOWN_SECONDS = 8.0
_RELAY_DEDUP_MAX_ENTRIES = 2048


@dataclass
class _PersistentState:
    round_number: int
    event_queue: asyncio.Queue[ChatEvent | None]
    agent_idle: dict[str, bool]
    agent_passed: dict[str, bool]
    agent_initialized: dict[str, bool]
    agent_tasks: dict[str, asyncio.Task]
    settlement_signaled: bool = False
    round_has_activity: bool = False
    round_open: bool = True


type InboxEvent = tuple[str, str, int | None, str | None]


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
        self._system_queue: asyncio.Queue[str] = asyncio.Queue()
        self._stop_events: dict[str, asyncio.Event] = {}
        self._restart_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._resume_event = asyncio.Event()
        self._any_stopped_this_round = False
        self._pause_on_stop = True
        self._add_agent_queue: asyncio.Queue[BaseAgent] = asyncio.Queue()
        self._remove_agent_queue: asyncio.Queue[str] = asyncio.Queue()
        self._dm_debounce_timers: dict[str, asyncio.TimerHandle] = {}
        self._dm_debounce_texts: dict[str, list[str]] = {}
        self._inboxes: dict[str, asyncio.Queue[InboxEvent]] = {}
        self._recent_relays: dict[tuple[str, str, str], float] = {}
        self._delivery_seq = 0
        self._delivery_pending: dict[str, set[str]] = {}

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

    def inject_system_message(self, text: str) -> None:
        self._system_queue.put_nowait(text)

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

    def respond_to_permission(self, agent_name: str, response: object) -> None:
        """Forward a permission response to the named agent."""
        agent = next((a for a in self.agents if a.name == agent_name), None)
        if agent:
            asyncio.create_task(agent.respond_to_permission(response))

    async def restart_agent(self, name: str, dm_text: str) -> None:
        """Queue a DM for an agent.

        Multiple DMs within 500ms are coalesced into a single inbox event
        with the messages joined by newlines.
        """
        # Cancel any pending debounce timer for this agent
        timer = self._dm_debounce_timers.pop(name, None)
        if timer is not None:
            timer.cancel()

        # Accumulate text
        self._dm_debounce_texts.setdefault(name, []).append(dm_text)

        # Schedule the DM delivery after 500ms of silence
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

    def _dm_to_inbox(self, name: str, text: str) -> None:
        """Queue a DM to a specific agent's persistent-mode inbox."""
        inbox = self._inboxes.get(name)
        if inbox:
            delivery_id = self._next_delivery_id()
            self._delivery_pending[delivery_id] = {name}
            inbox.put_nowait(("dm", text, None, delivery_id))

    def _next_delivery_id(self) -> str:
        self._delivery_seq += 1
        return f"d{self._delivery_seq}"

    def _enqueue_delivery(
        self,
        *,
        sender: str,
        message: str,
        round_number: int | None,
        recipients: list[str],
    ) -> str | None:
        if not recipients:
            return None
        delivery_id = self._next_delivery_id()
        self._delivery_pending[delivery_id] = set(recipients)
        for recipient in recipients:
            inbox = self._inboxes.get(recipient)
            if inbox is None:
                continue
            inbox.put_nowait((sender, message, round_number, delivery_id))
        return delivery_id

    def _ack_delivery(
        self,
        *,
        event_queue: asyncio.Queue[ChatEvent | None],
        delivery_id: str | None,
        recipient: str,
        sender: str,
        round_number: int | None,
    ) -> None:
        if not delivery_id:
            return
        pending = self._delivery_pending.get(delivery_id)
        if not pending or recipient not in pending:
            return
        pending.discard(recipient)
        event_queue.put_nowait(
            AgentDeliveryAcked(
                delivery_id=delivery_id,
                recipient=recipient,
                sender=sender,
                round_number=round_number,
            )
        )
        if not pending:
            self._delivery_pending.pop(delivery_id, None)

    def _drop_agent_pending_deliveries(self, name: str) -> None:
        stale = []
        for delivery_id, pending in self._delivery_pending.items():
            pending.discard(name)
            if not pending:
                stale.append(delivery_id)
        for delivery_id in stale:
            self._delivery_pending.pop(delivery_id, None)

    @staticmethod
    def _normalize_relay_text(text: str) -> str:
        return " ".join(text.split()).strip().lower()

    def _prune_recent_relays(self, now: float) -> None:
        cutoff = now - _RELAY_DEDUP_COOLDOWN_SECONDS
        stale = [k for k, ts in self._recent_relays.items() if ts < cutoff]
        for key in stale:
            self._recent_relays.pop(key, None)
        if len(self._recent_relays) <= _RELAY_DEDUP_MAX_ENTRIES:
            return
        # Keep most recent entries only.
        ordered = sorted(self._recent_relays.items(), key=lambda item: item[1], reverse=True)
        self._recent_relays = dict(ordered[:_RELAY_DEDUP_MAX_ENTRIES])

    def _should_relay_share(self, sender: str, target: str, shareable: str) -> bool:
        now = time.monotonic()
        self._prune_recent_relays(now)
        normalized = self._normalize_relay_text(shareable)
        if not normalized:
            return False
        key = (sender.lower(), target.lower(), normalized)
        last = self._recent_relays.get(key)
        if last is not None and (now - last) < _RELAY_DEDUP_COOLDOWN_SECONDS:
            return False
        self._recent_relays[key] = now
        return True

    def _format_persistent_prompt(
        self,
        agent: BaseAgent,
        sender: str,
        message: str,
        is_first_message: bool,
    ) -> str:
        """Build a consistent event-style prompt for persistent messaging."""
        prelude = ""
        if is_first_message:
            extra = self.context_provider(agent.name) if self.context_provider else None
            agent_role = self.roles.get(agent.name, "")
            context = format_session_context(
                agent.name,
                working_dir=self.working_dir,
                participants=self.participants,
                role=agent_role,
            )
            extra_sections = ""
            if extra:
                extra_sections = "\n\n".join(v for v in extra.values() if v) + "\n\n"
            prelude = f"{context}\n\n{extra_sections}"

        if sender == "user":
            return (
                f"{prelude}"
                "## Incoming Event\n"
                f"[User]: {message}\n\n"
                f"{_PERSISTENT_REPLY_DIRECTIVE}"
            )

        if sender == "dm":
            return (
                f"{prelude}"
                "## Direct Message from User\n"
                f"{message}\n\n"
                "Treat this as a targeted directive for you.\n"
                f"{_PERSISTENT_REPLY_DIRECTIVE}"
            )

        if sender == "system":
            return (
                f"{prelude}"
                "## Incoming Event\n"
                f"[System]: {message}\n\n"
                f"{_PERSISTENT_REPLY_DIRECTIVE}"
            )

        # Relay from another agent
        return (
            f"{prelude}"
            "## Incoming Event\n"
            f"[{sender.capitalize()}] shared:\n{message}\n\n"
            "Only respond if you can add net-new value or concrete next action.\n"
            f"{_PERSISTENT_REPLY_DIRECTIVE}"
        )

    @staticmethod
    def _format_incoming_event(sender: str, message: str) -> str:
        if sender == "user":
            return f"[User]: {message}"
        if sender == "dm":
            return f"[Direct message from user]: {message}"
        if sender == "system":
            return f"[System]: {message}"
        return f"[{sender.capitalize()}] shared:\n{message}"

    def _drain_inbox_batch(
        self,
        agent_name: str,
        first_event: InboxEvent,
    ) -> list[InboxEvent]:
        """Drain currently buffered inbox items so one turn can process a batch."""
        inbox = self._inboxes.get(agent_name)
        events = [first_event]
        if inbox is None:
            return events
        while True:
            try:
                events.append(inbox.get_nowait())
            except asyncio.QueueEmpty:
                break
        return events

    def _init_persistent_state(
        self,
        initial_prompt: str | None,
        start_round: int,
    ) -> _PersistentState:
        round_number = start_round + 1
        event_queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue()

        self._inboxes = {a.name: asyncio.Queue() for a in self.agents}
        agent_idle = {a.name: False for a in self.agents}
        agent_passed = {a.name: False for a in self.agents}
        agent_initialized = {a.name: False for a in self.agents}
        self._stop_events = {a.name: asyncio.Event() for a in self.agents}

        seed_text = initial_prompt
        if not seed_text:
            for msg in reversed(self.history):
                if msg["role"] == "user":
                    seed_text = msg["content"]
                    break
        if seed_text:
            self._enqueue_delivery(
                sender="user",
                message=seed_text,
                round_number=round_number,
                recipients=[a.name for a in self.agents],
            )

        return _PersistentState(
            round_number=round_number,
            event_queue=event_queue,
            agent_idle=agent_idle,
            agent_passed=agent_passed,
            agent_initialized=agent_initialized,
            agent_tasks={},
            settlement_signaled=False,
            round_has_activity=bool(seed_text),
            round_open=True,
        )

    def _try_signal_persistent_settlement(self, state: _PersistentState) -> None:
        if state.settlement_signaled:
            return
        if not state.round_has_activity:
            return
        if not all(state.agent_idle.values()):
            return
        if not all(q.empty() for q in self._inboxes.values()):
            return
        state.settlement_signaled = True
        state.event_queue.put_nowait(None)

    async def _consume_persistent_stream(
        self,
        *,
        agent: BaseAgent,
        prompt: str,
        message_round: int,
        partial_chunks: list[str],
        event_queue: asyncio.Queue[ChatEvent | None],
    ) -> AgentResponse | None:
        response: AgentResponse | None = None
        async for item in agent.stream(prompt, self.timeout):
            if isinstance(item, AgentResponse):
                response = item
                is_pass = detect_pass(item.response)
                if item.stderr:
                    await event_queue.put(
                        AgentStderr(
                            agent_name=agent.name,
                            round_number=message_round,
                            text=item.stderr,
                        )
                    )
                await event_queue.put(
                    AgentCompleted(
                        agent_name=agent.name,
                        round_number=message_round,
                        response=item,
                        passed=is_pass,
                    )
                )
            elif isinstance(item, AgentPermissionRequest):
                await event_queue.put(
                    AgentPermissionRequested(
                        agent_name=item.agent,
                        round_number=message_round,
                        request_id=item.request_id,
                        tool_name=item.tool_name,
                        tool_input=item.tool_input,
                        description=item.description,
                    )
                )
            elif isinstance(item, BaseAgentNotice):
                await event_queue.put(
                    AgentNotice(agent_name=item.agent, message=item.message)
                )
            elif isinstance(item, str):
                partial_chunks.append(item)
                await event_queue.put(
                    AgentStreamChunk(
                        agent_name=agent.name,
                        round_number=message_round,
                        text=item,
                    )
                )
        return response

    async def _handle_persistent_timeout(
        self,
        *,
        agent: BaseAgent,
        message_round: int,
        state: _PersistentState,
    ) -> None:
        response = AgentResponse(
            agent=agent.name,
            response="Timeout",
            success=False,
            latency_ms=0,
        )
        await state.event_queue.put(
            AgentCompleted(
                agent_name=agent.name,
                round_number=message_round,
                response=response,
                passed=False,
                stopped=True,
            )
        )
        self._any_stopped_this_round = True
        self._stop_events[agent.name] = asyncio.Event()
        state.agent_passed[agent.name] = False
        state.agent_idle[agent.name] = True
        self._try_signal_persistent_settlement(state)

    async def _handle_persistent_stopped_stream(
        self,
        *,
        agent: BaseAgent,
        message_round: int,
        partial_chunks: list[str],
        state: _PersistentState,
    ) -> None:
        partial_text = "".join(partial_chunks).strip() or "(stopped)"
        response = AgentResponse(
            agent=agent.name,
            response=partial_text,
            success=False,
            latency_ms=0,
        )
        await state.event_queue.put(
            AgentCompleted(
                agent_name=agent.name,
                round_number=message_round,
                response=response,
                passed=False,
                stopped=True,
            )
        )
        self._any_stopped_this_round = True
        self._stop_events[agent.name] = asyncio.Event()
        state.agent_passed[agent.name] = False
        state.agent_idle[agent.name] = True
        self._try_signal_persistent_settlement(state)

    def _process_persistent_agent_response(
        self,
        *,
        agent: BaseAgent,
        response: AgentResponse,
        message_round: int,
        state: _PersistentState,
    ) -> None:
        is_pass = detect_pass(response.response)
        if is_pass:
            state.agent_passed[agent.name] = True
            state.agent_idle[agent.name] = True
            self.history.append({
                "role": agent.name, "content": "[PASS]",
                "round": message_round,
            })
            self._try_signal_persistent_settlement(state)
            return

        state.agent_passed[agent.name] = False
        shareable = extract_shareable(response.response)
        self.history.append({
            "role": agent.name,
            "content": shareable or PLACEHOLDER,
            "round": message_round,
        })
        state.agent_idle[agent.name] = True
        if shareable and shareable != PLACEHOLDER:
            targets: list[str] = []
            for other in self.agents:
                if other.name != agent.name and self._should_relay_share(agent.name, other.name, shareable):
                    targets.append(other.name)
                    state.agent_idle[other.name] = False
            self._enqueue_delivery(
                sender=agent.name,
                message=shareable,
                round_number=message_round,
                recipients=targets,
            )

    def _restart_dead_persistent_loops(
        self,
        state: _PersistentState,
        agent_loop_factory: Callable[[BaseAgent], asyncio.Task],
    ) -> None:
        for agent in self.agents:
            task = state.agent_tasks.get(agent.name)
            if task and task.done():
                state.agent_tasks[agent.name] = agent_loop_factory(agent)

    def _format_persistent_events_prompt(
        self,
        agent: BaseAgent,
        events: list[InboxEvent],
        is_first_message: bool,
    ) -> str:
        if len(events) == 1:
            sender, message, _, _ = events[0]
            return self._format_persistent_prompt(
                agent=agent,
                sender=sender,
                message=message,
                is_first_message=is_first_message,
            )

        prelude = ""
        if is_first_message:
            extra = self.context_provider(agent.name) if self.context_provider else None
            agent_role = self.roles.get(agent.name, "")
            context = format_session_context(
                agent.name,
                working_dir=self.working_dir,
                participants=self.participants,
                role=agent_role,
            )
            extra_sections = ""
            if extra:
                extra_sections = "\n\n".join(v for v in extra.values() if v) + "\n\n"
            prelude = f"{context}\n\n{extra_sections}"

        incoming = "\n\n".join(
            self._format_incoming_event(sender, message)
            for sender, message, _, _ in events
        )
        return (
            f"{prelude}"
            "## Incoming Events\n"
            f"{incoming}\n\n"
            "Respond once to the combined context. Prioritize direct user requests.\n"
            f"{_PERSISTENT_REPLY_DIRECTIVE}"
        )

    async def run_persistent(
        self, initial_prompt: str | None = None, start_round: int = 0,
    ) -> AsyncGenerator[ChatEvent, None]:
        """Real-time message-passing mode for persistent pipe agents.

        Each agent has an inbox. Shares are relayed immediately to other agents.
        The user can broadcast (inject_user_message) or DM (_dm_to_inbox).
        Rounds are implicit: a round settles when all agents are idle and inboxes
        are empty; non-consensus settlements immediately advance to a fresh round.
        """
        if initial_prompt:
            self.history.append({"role": "user", "content": initial_prompt})
        state = self._init_persistent_state(initial_prompt, start_round)

        self._any_stopped_this_round = False
        self._pause_on_stop = True
        yield RoundStarted(round_number=state.round_number, agents=[a.name for a in self.agents])

        async def agent_loop(agent: BaseAgent) -> None:
            """Each agent loops: wait for inbox → send to agent → stream → relay shares."""
            while True:
                # Wait for a message in our inbox
                try:
                    sender, message, inbox_round, delivery_id = await asyncio.wait_for(
                        self._inboxes[agent.name].get(), timeout=0.2,
                    )
                except asyncio.TimeoutError:
                    self._try_signal_persistent_settlement(state)
                    if state.settlement_signaled:
                        await asyncio.sleep(0.05)
                    continue

                state.agent_idle[agent.name] = False
                state.agent_passed[agent.name] = False
                batched_events = self._drain_inbox_batch(
                    agent.name, (sender, message, inbox_round, delivery_id),
                )
                for batch_sender, _, batch_round, batch_delivery_id in batched_events:
                    self._ack_delivery(
                        event_queue=state.event_queue,
                        delivery_id=batch_delivery_id,
                        recipient=agent.name,
                        sender=batch_sender,
                        round_number=batch_round,
                    )
                round_markers = [
                    r for _, _, r, _ in batched_events if isinstance(r, int)
                ]
                message_round = max(round_markers) if round_markers else state.round_number

                # Format the message for the agent
                prompt = self._format_persistent_events_prompt(
                    agent=agent,
                    events=batched_events,
                    is_first_message=not state.agent_initialized[agent.name],
                )
                if not state.agent_initialized[agent.name]:
                    state.agent_initialized[agent.name] = True

                # Emit prompt visibility event
                await state.event_queue.put(AgentPromptAssembled(
                    agent_name=agent.name,
                    round_number=message_round,
                    sections={"message": prompt},
                ))

                # Stream the response
                stop_event = self._stop_events[agent.name]
                partial_chunks: list[str] = []
                response: AgentResponse | None = None

                try:
                    stream_task = asyncio.create_task(
                        self._consume_persistent_stream(
                            agent=agent,
                            prompt=prompt,
                            message_round=message_round,
                            partial_chunks=partial_chunks,
                            event_queue=state.event_queue,
                        )
                    )
                    stop_task = asyncio.create_task(stop_event.wait())

                    done, pending = await asyncio.wait(
                        [stream_task, stop_task],
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=min(
                            self.timeout,
                            max(getattr(agent, "parse_timeout", self.timeout), 1.0),
                        ) + 1.0,
                    )
                    if not done:
                        log.warning(
                            "[%s] persistent wait timed out after %.1fs; forcing cancel",
                            agent.name,
                            self.timeout + 1.0,
                        )
                        try:
                            await agent.cancel_turn()
                        except Exception:
                            log.debug("[%s] cancel after wait timeout failed", agent.name, exc_info=True)
                        for p in pending:
                            p.cancel()
                            try:
                                await p
                            except (asyncio.CancelledError, Exception):
                                pass
                        await self._handle_persistent_timeout(
                            agent=agent,
                            message_round=message_round,
                            state=state,
                        )
                        continue

                    if stop_task in done and not stream_task.done():
                        try:
                            await agent.cancel_turn()
                        except Exception:
                            log.debug("[%s] persistent cancel failed", agent.name, exc_info=True)

                    for p in pending:
                        p.cancel()
                        try:
                            await p
                        except (asyncio.CancelledError, Exception):
                            pass

                    if stream_task in done:
                        exc = stream_task.exception()
                        if exc is not None:
                            raise exc
                        response = stream_task.result()

                    # Stopped mid-stream
                    if stop_event.is_set() and response is None:
                        await self._handle_persistent_stopped_stream(
                            agent=agent,
                            message_round=message_round,
                            partial_chunks=partial_chunks,
                            state=state,
                        )
                        continue

                except asyncio.CancelledError:
                    return
                except Exception as e:
                    log.exception("[%s] persistent stream error: %s", agent.name, e)
                    if response is None:
                        response = AgentResponse(
                            agent=agent.name, response=str(e),
                            success=False, latency_ms=0,
                        )
                        await state.event_queue.put(
                            AgentCompleted(
                                agent_name=agent.name,
                                round_number=message_round,
                                response=response,
                                passed=False,
                            )
                        )

                if response is None:
                    continue

                self._process_persistent_agent_response(
                    agent=agent,
                    response=response,
                    message_round=message_round,
                    state=state,
                )
                if state.settlement_signaled:
                    return

        # Start agent loops
        for agent in self.agents:
            state.agent_tasks[agent.name] = asyncio.create_task(
                agent_loop(agent), name=f"persistent-{agent.name}",
            )

        def _restart_dead_loops() -> None:
            self._restart_dead_persistent_loops(
                state,
                lambda a: asyncio.create_task(agent_loop(a), name=f"persistent-{a.name}"),
            )

        # Main event pump: yield events to caller, handle user injections
        try:
            while True:
                # Process user message injections
                while not self._user_queue.empty():
                    if not state.round_open:
                        self._any_stopped_this_round = False
                        self._pause_on_stop = True
                        state.round_open = True
                        yield RoundStarted(
                            round_number=state.round_number,
                            agents=[a.name for a in self.agents],
                        )
                    text = self._user_queue.get_nowait()
                    self.history.append({"role": "user", "content": text})
                    yield UserMessageReceived(text=text)
                    # Reset settlement so agents can re-engage
                    state.settlement_signaled = False
                    state.round_has_activity = True
                    # Broadcast to all agents
                    for a in self.agents:
                        state.agent_idle[a.name] = False
                        state.agent_passed[a.name] = False
                    self._enqueue_delivery(
                        sender="user",
                        message=text,
                        round_number=state.round_number,
                        recipients=[a.name for a in self.agents],
                    )
                    _restart_dead_loops()

                # Process system message injections
                while not self._system_queue.empty():
                    if not state.round_open:
                        self._any_stopped_this_round = False
                        self._pause_on_stop = True
                        state.round_open = True
                        yield RoundStarted(
                            round_number=state.round_number,
                            agents=[a.name for a in self.agents],
                        )
                    text = self._system_queue.get_nowait()
                    self.history.append({"role": "system", "content": text})
                    yield AgentNotice(agent_name="system", message=text)
                    state.settlement_signaled = False
                    state.round_has_activity = True
                    for a in self.agents:
                        state.agent_idle[a.name] = False
                        state.agent_passed[a.name] = False
                    self._enqueue_delivery(
                        sender="system",
                        message=text,
                        round_number=state.round_number,
                        recipients=[a.name for a in self.agents],
                    )
                    _restart_dead_loops()

                # Process DM restarts
                while not self._restart_queue.empty():
                    try:
                        name, dm_text = self._restart_queue.get_nowait()
                        if name in self._inboxes:
                            if not state.round_open:
                                self._any_stopped_this_round = False
                                self._pause_on_stop = True
                                state.round_open = True
                                yield RoundStarted(
                                    round_number=state.round_number,
                                    agents=[a.name for a in self.agents],
                                )
                            state.agent_idle[name] = False
                            state.agent_passed[name] = False
                            state.settlement_signaled = False
                            state.round_has_activity = True
                            self._enqueue_delivery(
                                sender="dm",
                                message=dm_text,
                                round_number=state.round_number,
                                recipients=[name],
                            )
                            _restart_dead_loops()
                    except asyncio.QueueEmpty:
                        break

                # Process agent additions
                while not self._add_agent_queue.empty():
                    try:
                        new_agent = self._add_agent_queue.get_nowait()
                        self.agents.append(new_agent)
                        self._inboxes[new_agent.name] = asyncio.Queue()
                        state.agent_idle[new_agent.name] = False
                        state.agent_passed[new_agent.name] = False
                        state.agent_initialized[new_agent.name] = False
                        self._stop_events[new_agent.name] = asyncio.Event()
                        # Seed the new agent with the last user message so it has context
                        last_user_msg = None
                        for msg in reversed(self.history):
                            if msg["role"] == "user":
                                last_user_msg = msg["content"]
                                break
                        if last_user_msg:
                            if not state.round_open:
                                self._any_stopped_this_round = False
                                self._pause_on_stop = True
                                state.round_open = True
                                yield RoundStarted(
                                    round_number=state.round_number,
                                    agents=[a.name for a in self.agents],
                                )
                            self._inboxes[new_agent.name].put_nowait(
                                ("user", last_user_msg, state.round_number, None)
                            )
                            state.settlement_signaled = False
                            state.round_has_activity = True
                        state.agent_tasks[new_agent.name] = asyncio.create_task(
                            agent_loop(new_agent), name=f"persistent-{new_agent.name}",
                        )
                    except asyncio.QueueEmpty:
                        break

                # Process agent removals
                while not self._remove_agent_queue.empty():
                    try:
                        remove_name = self._remove_agent_queue.get_nowait()
                        self.agents = [a for a in self.agents if a.name != remove_name]
                        self._inboxes.pop(remove_name, None)
                        state.agent_idle.pop(remove_name, None)
                        state.agent_passed.pop(remove_name, None)
                        state.agent_initialized.pop(remove_name, None)
                        self._drop_agent_pending_deliveries(remove_name)
                        stop_ev = self._stop_events.pop(remove_name, None)
                        if stop_ev:
                            stop_ev.set()
                        task = state.agent_tasks.pop(remove_name, None)
                        if task and not task.done():
                            task.cancel()
                    except asyncio.QueueEmpty:
                        break

                try:
                    event = await asyncio.wait_for(state.event_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                if event is None:
                    # All agents settled — emit round end and check termination
                    all_passed = all(state.agent_passed.values())
                    yield RoundEnded(round_number=state.round_number, all_passed=all_passed)
                    if self._any_stopped_this_round and self._pause_on_stop:
                        self._any_stopped_this_round = False
                        self._resume_event.clear()
                        yield RoundPaused(round_number=state.round_number)
                        while (
                            not self._resume_event.is_set()
                            and self._user_queue.empty()
                            and self._system_queue.empty()
                            and self._restart_queue.empty()
                            and self._add_agent_queue.empty()
                        ):
                            await asyncio.sleep(0.1)
                        self._resume_event.clear()
                        state.settlement_signaled = False
                        continue
                    # Advance to the next round after every settled cycle. For non-consensus
                    # settlements, immediately open the next round so pass-heavy idle states
                    # don't strand the room on a stale round number.
                    state.round_number += 1
                    state.settlement_signaled = False
                    state.round_has_activity = False
                    if all_passed:
                        state.round_open = False
                    else:
                        state.round_open = True
                        yield RoundStarted(
                            round_number=state.round_number,
                            agents=[a.name for a in self.agents],
                        )
                    continue

                yield event

        except asyncio.CancelledError:
            log.info("persistent session cancelled")
            raise
        finally:
            for task in state.agent_tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*state.agent_tasks.values(), return_exceptions=True)
            self._stop_events = {}
            self._inboxes = {}
            self._recent_relays = {}
            self._delivery_pending = {}

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
            while not self._system_queue.empty():
                text = self._system_queue.get_nowait()
                self.history.append({"role": "system", "content": text})
                yield AgentNotice(agent_name="system", message=text)

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
                                    AgentStderr(
                                        agent_name=agent.name,
                                        round_number=round_number,
                                        text=item.stderr,
                                    )
                                )
                            await event_queue.put(
                                AgentCompleted(
                                    agent_name=agent.name,
                                    round_number=round_number,
                                    response=item,
                                    passed=is_pass,
                                )
                            )
                        elif isinstance(item, AgentPermissionRequest):
                            await event_queue.put(
                                AgentPermissionRequested(
                                    agent_name=item.agent,
                                    round_number=round_number,
                                    request_id=item.request_id,
                                    tool_name=item.tool_name,
                                    tool_input=item.tool_input,
                                    description=item.description,
                                )
                            )
                        elif isinstance(item, BaseAgentNotice):
                            await event_queue.put(
                                AgentNotice(agent_name=item.agent, message=item.message)
                            )
                        elif isinstance(item, str):
                            partial_chunks.append(item)
                            await event_queue.put(
                                AgentStreamChunk(
                                    agent_name=agent.name,
                                    round_number=round_number,
                                    text=item,
                                )
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
                                round_number=round_number,
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
                                round_number=round_number,
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
                                round_number=round_number,
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

                # Drain pending restart requests (non-blocking)
                while not self._restart_queue.empty():
                    try:
                        restart_name, dm_text = self._restart_queue.get_nowait()
                        pending_restarts[restart_name] = dm_text
                    except asyncio.QueueEmpty:
                        break

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
                            round_number=round_number,
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
                while (
                    not self._resume_event.is_set()
                    and self._user_queue.empty()
                    and self._system_queue.empty()
                ):
                    await asyncio.sleep(0.1)
                self._resume_event.clear()

            # Check for user/system messages before next round
            if not self._user_queue.empty() or not self._system_queue.empty():
                continue

            # Small delay to allow user injection window
            await asyncio.sleep(0.05)
