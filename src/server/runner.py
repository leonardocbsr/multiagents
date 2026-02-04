from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version as pkg_version
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from fastapi import WebSocket

from ..agents import create_agents
from ..agents.base import AgentResponse, BaseAgent
from ..cards.engine import CardEngine
from ..cards.models import Card, CardPhaseEntry, CardStatus
from ..chat.events import (
    AgentCompleted,
    AgentStreamChunk,
    RoundEnded,
    RoundPaused,
    RoundStarted,
)
from ..chat.room import ChatRoom
from ..chat.router import format_cards_section, format_session_context
from .protocol import event_to_dict
from .sessions import SessionStore
from .settings import SettingsStore

log = logging.getLogger("multiagents")
_SERVICE_NAME = "multiagents"
_T = TypeVar("_T")


def _extract_agent_names(agent_names: list[str] | list[dict]) -> list[str]:
    """Extract plain name strings from a list that may contain dicts or strings."""
    if not agent_names:
        return []
    if isinstance(agent_names[0], dict):
        return [a["name"] for a in agent_names]
    return list(agent_names)  # type: ignore[arg-type]


_DEFAULT_WARMUP_IDLE_TTL = 300.0
_DEFAULT_ACK_TTL = 300.0
try:
    _SERVICE_VERSION = pkg_version(_SERVICE_NAME)
except PackageNotFoundError:
    _SERVICE_VERSION = "dev"


@dataclass
class RoundMetrics:
    round_number: int
    started_at: float
    stream_chunks: dict[str, int] = field(default_factory=dict)
    latencies_ms: dict[str, float] = field(default_factory=dict)
    send_failures: int = 0


class SessionRunner:
    def __init__(
        self,
        store: SessionStore,
        timeout: float = 1800.0,
        send_timeout: float = 120.0,
        parse_timeout: float = 120.0,
        hard_timeout: float | None = None,
        warmup_ttl: float = _DEFAULT_WARMUP_IDLE_TTL,
        ack_ttl: float = _DEFAULT_ACK_TTL,
        settings_store: SettingsStore | None = None,
    ) -> None:
        self.store = store
        self.settings_store = settings_store
        self.timeout = timeout
        self.send_timeout = send_timeout
        self.parse_timeout = parse_timeout
        self.hard_timeout = hard_timeout
        self.warmup_ttl = warmup_ttl
        self.ack_ttl = ack_ttl
        self._tasks: dict[str, asyncio.Task] = {}
        self._rooms: dict[str, ChatRoom] = {}
        self._subscribers: dict[str, set[WebSocket]] = {}
        self._acks: dict[str, dict[WebSocket, int]] = {}
        self._ack_times: dict[str, dict[WebSocket, float]] = {}
        self._round_metrics: dict[str, RoundMetrics] = {}
        self._send_failures: dict[str, int] = {}
        self._session_send_timeouts: dict[str, float] = {}
        # Pool of pre-warmed agents: {session_id: {agent_name: BaseAgent}}
        self._agent_pools: dict[str, dict[str, BaseAgent]] = {}
        self._warmup_tasks: dict[str, asyncio.Task] = {}
        self._idle_cleanup_tasks: dict[str, asyncio.Task] = {}
        self._pending_runs: dict[str, tuple[str, list[str] | list[dict], int]] = {}
        # Card engine per session and tracking of active card phases
        self._card_engines: dict[str, CardEngine] = {}
        self._active_card_tasks: dict[str, str] = {}  # session_id -> card_id
        self._card_phase_tasks: dict[str, asyncio.Task] = {}
        self._card_phase_tokens: dict[str, int] = {}
        # Delegation tracking: collect agent responses during delegation rounds
        self._delegation_cards: dict[str, str] = {}  # session_id -> card_id
        self._delegation_responses: dict[str, dict[str, str]] = {}  # session_id -> {agent: response}

    def subscribe(self, session_id: str, ws: WebSocket) -> None:
        self._subscribers.setdefault(session_id, set()).add(ws)
        self._acks.setdefault(session_id, {})[ws] = 0
        self._ack_times.setdefault(session_id, {})[ws] = time.monotonic()
        self._cancel_idle_cleanup(session_id)

    def unsubscribe(self, session_id: str, ws: WebSocket) -> None:
        subs = self._subscribers.get(session_id)
        if subs:
            subs.discard(ws)
            if not subs:
                self._subscribers.pop(session_id, None)
        acks = self._acks.get(session_id)
        if acks:
            acks.pop(ws, None)
            if not acks:
                self._acks.pop(session_id, None)
        times = self._ack_times.get(session_id)
        if times:
            times.pop(ws, None)
            if not times:
                self._ack_times.pop(session_id, None)
        if not self._subscribers.get(session_id) and not self.is_running(session_id):
            self._schedule_idle_cleanup(session_id)

    def is_running(self, session_id: str) -> bool:
        task = self._tasks.get(session_id)
        if task is not None and not task.done():
            return True
        pending = self._pending_runs.get(session_id)
        if pending is not None:
            return True
        phase_task = self._card_phase_tasks.get(session_id)
        return phase_task is not None and not phase_task.done()

    def _log_metric(self, name: str, **fields: object) -> None:
        payload = {
            "metric": name,
            "ts": time.time(),
            "service": _SERVICE_NAME,
            "version": _SERVICE_VERSION,
            **fields,
        }
        log.info("metric %s", json.dumps(payload, separators=(",", ":"), sort_keys=True))

    async def _store_call(self, fn: Callable[..., _T], *args: object, **kwargs: object) -> _T:
        return await asyncio.to_thread(fn, *args, **kwargs)

    def _prune_stale_acks(self, session_id: str) -> None:
        if self.ack_ttl <= 0:
            return
        times = self._ack_times.get(session_id)
        if not times:
            return
        now = time.monotonic()
        stale = [ws for ws, ts in times.items() if (now - ts) > self.ack_ttl]
        if not stale:
            return
        acks = self._acks.get(session_id)
        for ws in stale:
            times.pop(ws, None)
            if acks:
                acks.pop(ws, None)
        if not times:
            self._ack_times.pop(session_id, None)
        if acks is not None and not acks:
            self._acks.pop(session_id, None)

    def _cancel_next_card_phase(self, session_id: str) -> None:
        task = self._card_phase_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    def _start_pending_run(self, session_id: str) -> None:
        pending = self._pending_runs.pop(session_id, None)
        if not pending:
            return
        prompt, agent_names, start_round = pending
        task = asyncio.create_task(
            self._execute(session_id, prompt, agent_names, start_round=start_round),
            name=f"run-{session_id}",
        )
        self._tasks[session_id] = task

    def log_client_metric(self, name: str, session_id: str | None, value: float, **fields: object) -> None:
        payload = {"session_id": session_id, "value": value, "source": "client", **fields}
        self._log_metric(name, **payload)

    async def broadcast(self, session_id: str, data: dict) -> int:
        subs = self._subscribers.get(session_id)
        if "event_id" not in data:
            try:
                data = dict(data)
                data["event_id"] = await self._store_call(self.store.reserve_event_id, session_id)
                try:
                    await self._store_call(self.store.save_event, session_id, data["event_id"], data)
                except Exception:
                    log.exception("failed to persist event %s:%s", session_id, data["event_id"])
            except Exception:
                log.exception("failed to assign event id for session %s", session_id)
        if not subs:
            log.debug("broadcast dropped (no subscribers): %s", session_id)
            return 0
        self._prune_stale_acks(session_id)
        snapshot = list(subs)
        dead: list[WebSocket] = []
        sent = 0
        timeout = self._session_send_timeouts.get(session_id, self.send_timeout)

        async def _send(ws: WebSocket) -> None:
            await asyncio.wait_for(ws.send_json(data), timeout=timeout)

        results = await asyncio.gather(*[_send(ws) for ws in snapshot], return_exceptions=True)
        for ws, result in zip(snapshot, results):
            if isinstance(result, Exception):
                log.warning("broadcast failed session=%s type=%s error=%s", session_id, data.get("type"), result)
                self._send_failures[session_id] = self._send_failures.get(session_id, 0) + 1
                metrics = self._round_metrics.get(session_id)
                if metrics:
                    metrics.send_failures += 1
                self._log_metric(
                    "ws_send_failure",
                    session_id=session_id,
                    event_type=data.get("type"),
                )
                dead.append(ws)
            else:
                sent += 1
        for ws in dead:
            subs.discard(ws)
            acks = self._acks.get(session_id)
            if acks:
                acks.pop(ws, None)
            times = self._ack_times.get(session_id)
            if times:
                times.pop(ws, None)
        if not subs:
            self._subscribers.pop(session_id, None)
            self._acks.pop(session_id, None)
            self._ack_times.pop(session_id, None)
        if sent == 0 and snapshot:
            log.warning("broadcast delivered to 0 subscribers session=%s type=%s", session_id, data.get("type"))
        return sent

    async def replay_events(self, session_id: str, after_event_id: int, ws: WebSocket) -> None:
        events = await self._store_call(self.store.get_events_since, session_id, after_event_id)
        timeout = self._session_send_timeouts.get(session_id, self.send_timeout)
        for event in events:
            try:
                await asyncio.wait_for(ws.send_json(event), timeout=timeout)
            except Exception as exc:
                log.warning("replay failed session=%s type=%s error=%s", session_id, event.get("type"), exc)
                break

    async def ack(self, session_id: str, ws: WebSocket, event_id: int) -> None:
        acks = self._acks.setdefault(session_id, {})
        acks[ws] = max(acks.get(ws, 0), event_id)
        self._ack_times.setdefault(session_id, {})[ws] = time.monotonic()
        self._prune_stale_acks(session_id)
        if not acks:
            return
        min_ack = min(acks.values())
        if min_ack > 0:
            try:
                await self._store_call(self.store.prune_events, session_id, min_ack)
            except Exception:
                log.exception("failed to prune events for session %s", session_id)

    def run_prompt(self, session_id: str, prompt: str, agent_names: list[str] | list[dict], start_round: int = 0) -> None:
        self._cancel_idle_cleanup(session_id)
        if self.is_running(session_id):
            existing = self._pending_runs.get(session_id)
            if existing is not None:
                log.info("session %s already running; replacing pending run", session_id)
            self._pending_runs[session_id] = (prompt, agent_names, start_round)
            return
        task = asyncio.create_task(
            self._execute(session_id, prompt, agent_names, start_round=start_round),
            name=f"run-{session_id}",
        )
        self._tasks[session_id] = task

    def inject_message(self, session_id: str, text: str) -> None:
        room = self._rooms.get(session_id)
        if room:
            room.inject_user_message(text)

    def stop_agent(self, session_id: str, agent_name: str) -> None:
        room = self._rooms.get(session_id)
        if room:
            room.stop_agent(agent_name)

    def stop_round(self, session_id: str) -> None:
        room = self._rooms.get(session_id)
        if room:
            room.stop_round(pause=True)

    def resume(self, session_id: str) -> None:
        room = self._rooms.get(session_id)
        if room:
            room.resume()

    async def restart_agent(self, session_id: str, agent_name: str, dm_text: str) -> None:
        """Restart an agent with a DM (cancel + continue)."""
        room = self._rooms.get(session_id)
        if room:
            await room.restart_agent(agent_name, dm_text)

    async def cancel(self, session_id: str) -> None:
        task = self._tasks.get(session_id)
        if task and not task.done():
            room = self._rooms.get(session_id)
            if room:
                room.stop_round(pause=False)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._pending_runs.pop(session_id, None)
        self._cancel_next_card_phase(session_id)

    async def warmup_agents(self, session_id: str, agent_names: list[str] | list[dict]) -> dict[str, BaseAgent]:
        """Pre-warm agents by running a minimal prompt to establish CLI sessions.

        This pays the CLI startup cost upfront so the first real message is faster.
        Returns a dict of agent_name -> BaseAgent with established sessions.
        """
        agent_session_ids = await self._store_call(self.store.get_agent_session_ids, session_id)
        session_data = await self._store_call(self.store.get_session, session_id)
        working_dir = session_data.get("working_dir", "") if session_data else ""
        agents = create_agents(
            agent_names,
            parse_timeout=self.parse_timeout,
            hard_timeout=self.hard_timeout,
        )
        # Build participants list for persona-aware prompts
        all_agents = agent_names if agent_names and isinstance(agent_names[0], dict) else None
        participants = [{"name": a["name"], "type": a["type"]} for a in all_agents] if all_agents else None
        warmed_agents: dict[str, BaseAgent] = {}

        async def warm_agent(agent: BaseAgent) -> None:
            try:
                # Use existing session ID if available
                cli_sid = agent_session_ids.get(agent.name)
                if cli_sid:
                    agent.session_id = cli_sid
                if working_dir:
                    agent.project_dir = working_dir

                # Resolve role for this agent
                agent_role = ""
                if all_agents:
                    for a in all_agents:
                        if a["name"] == agent.name:
                            agent_role = a.get("role", "")
                            break

                # Send session context (participants, role) then ask for [PASS].
                # Static directives (Share tags, coordination, round model) are
                # already in the CLI system prompt via build_agent_system_prompt().
                context = format_session_context(agent.name, working_dir, participants=participants, role=agent_role)
                warmup_prompt = context + "\n\nPlease respond with exactly [PASS]."
                async for item in agent.stream(warmup_prompt, timeout=30.0):
                    if isinstance(item, AgentResponse):
                        # Save the session ID for future resume
                        if agent.session_id:
                            await self._store_call(
                                self.store.save_agent_session_id, session_id, agent.name, agent.session_id,
                            )
                        warmed_agents[agent.name] = agent
                        log.info("[%s] warmed up in %.0fms", agent.name, item.latency_ms)
                        break
            except Exception as exc:
                log.warning("[%s] warmup failed: %s", agent.name, exc)
                # Still include the agent - it will retry on first real message
                warmed_agents[agent.name] = agent

        # Run all agents in parallel for faster warmup
        await asyncio.gather(*[warm_agent(a) for a in agents])
        
        # Store in pool for reuse
        self._agent_pools[session_id] = warmed_agents
        self._warmup_tasks.pop(session_id, None)
        log.info("session %s warmup complete: %d/%d agents ready", 
                 session_id, len(warmed_agents), len(agents))
        return warmed_agents

    def start_warmup(self, session_id: str, agent_names: list[str] | list[dict]) -> None:
        """Start agent warmup in the background (non-blocking)."""
        if session_id in self._warmup_tasks:
            return  # Already warming up
        if session_id in self._agent_pools:
            return  # Agents already warmed
        if self.is_running(session_id):
            return  # Discussion actively running, agents are in use
        self._cancel_idle_cleanup(session_id)
        
        task = asyncio.create_task(
            self.warmup_agents(session_id, agent_names),
            name=f"warmup-{session_id}"
        )
        self._warmup_tasks[session_id] = task

    async def get_warmed_agents(self, session_id: str, agent_names: list[str] | list[dict]) -> list[BaseAgent]:
        """Get pre-warmed agents if available, otherwise create fresh ones."""
        pool = self._agent_pools.get(session_id, {})
        agents = []
        fallback_items = []

        for item in agent_names:
            name = item["name"] if isinstance(item, dict) else item
            if name in pool:
                agent = pool[name]
                agent.parse_timeout = self.parse_timeout
                agent.hard_timeout = self.hard_timeout
                agents.append(agent)
            else:
                fallback_items.append(item)

        if fallback_items:
            # Restore session IDs for freshly-created agents
            agent_session_ids = await self._store_call(self.store.get_agent_session_ids, session_id)
            fresh = create_agents(fallback_items, parse_timeout=self.parse_timeout, hard_timeout=self.hard_timeout)
            for agent in fresh:
                cli_sid = agent_session_ids.get(agent.name)
                if cli_sid:
                    agent.session_id = cli_sid
            agents.extend(fresh)

        return agents

    async def add_agent(self, session_id: str, persona: dict) -> None:
        """Add a new agent to a running or idle session."""
        agents = create_agents([persona], parse_timeout=self.parse_timeout, hard_timeout=self.hard_timeout)
        agent = agents[0]
        session_data = await self._store_call(self.store.get_session, session_id)
        working_dir = session_data.get("working_dir", "") if session_data else ""
        if working_dir:
            agent.project_dir = working_dir
        pool = self._agent_pools.setdefault(session_id, {})
        pool[agent.name] = agent
        room = self._rooms.get(session_id)
        if room:
            room.add_agent(agent)

    async def remove_agent(self, session_id: str, name: str) -> None:
        """Remove an agent from a running or idle session."""
        room = self._rooms.get(session_id)
        if room:
            room.remove_agent(name)
        pool = self._agent_pools.get(session_id, {})
        agent = pool.pop(name, None)
        if agent:
            agent.cleanup()

    def cleanup_session(self, session_id: str, cancel_card_phase_tasks: bool = True) -> None:
        """Clean up warmed agents for a session."""
        self._cancel_idle_cleanup(session_id)
        self._session_send_timeouts.pop(session_id, None)
        if cancel_card_phase_tasks:
            self._cancel_next_card_phase(session_id)
        # Cancel any pending warmup
        if session_id in self._warmup_tasks:
            task = self._warmup_tasks.pop(session_id)
            if not task.done():
                task.cancel()

        # Clean up agent pool
        pool = self._agent_pools.pop(session_id, {})
        for agent in pool.values():
            agent.cleanup()

    async def delete_session(self, session_id: str) -> None:
        """Fully tear down a session: cancel tasks, clean up agents, remove from DB."""
        # Cancel running discussion
        task = self._tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.pop(session_id, None)
        self._pending_runs.pop(session_id, None)
        self._cancel_next_card_phase(session_id)

        # Clean up agents and warmup
        self.cleanup_session(session_id)

        # Remove card engine and tracking state
        self._card_engines.pop(session_id, None)
        self._active_card_tasks.pop(session_id, None)
        self._delegation_cards.pop(session_id, None)
        self._delegation_responses.pop(session_id, None)
        self._subscribers.pop(session_id, None)
        self._acks.pop(session_id, None)
        self._rooms.pop(session_id, None)
        self._round_metrics.pop(session_id, None)
        self._send_failures.pop(session_id, None)

        # Delete from database (cascades messages, agent_state, events, cards)
        await self._store_call(self.store.delete_session, session_id)

    # -- Card management -----------------------------------------------------

    def get_card_engine(self, session_id: str, agent_names: list[str] | list[dict]) -> CardEngine:
        """Lazy-create and return a CardEngine for the session, loading persisted cards."""
        if session_id not in self._card_engines:
            engine = CardEngine(_extract_agent_names(agent_names))
            saved = self.store.get_cards(session_id)
            if saved:
                cards = [self._dict_to_card(d) for d in saved]
                engine.load_cards(cards)
            self._card_engines[session_id] = engine
        return self._card_engines[session_id]

    @staticmethod
    def _dict_to_card(d: dict) -> Card:
        """Reconstruct a Card from a persisted dict."""
        history = []
        for entry in d.get("history", []):
            history.append(CardPhaseEntry(
                phase=CardStatus(entry["phase"]),
                agent=entry["agent"],
                content=entry["content"],
                timestamp=entry["timestamp"],
            ))
        prev = d.get("previous_phase")
        return Card(
            id=d["id"],
            title=d["title"],
            description=d.get("description", ""),
            status=CardStatus(d.get("status", "backlog")),
            planner=d.get("planner", ""),
            implementer=d.get("implementer", ""),
            reviewer=d.get("reviewer", ""),
            coordinator=d.get("coordinator", ""),
            coordination_stage=d.get("coordination_stage", ""),
            previous_phase=CardStatus(prev) if prev else None,
            history=history,
            created_at=d.get("created_at", ""),
        )

    async def create_card(
        self,
        session_id: str,
        agent_names: list[str] | list[dict],
        title: str,
        description: str,
        planner: str = "",
        implementer: str = "",
        reviewer: str = "",
        coordinator: str = "",
    ) -> Card:
        engine = self.get_card_engine(session_id, agent_names)
        card = engine.create_card(
            title=title,
            description=description,
            planner=planner,
            implementer=implementer,
            reviewer=reviewer,
            coordinator=coordinator,
        )
        await self._store_call(self.store.save_card, session_id, card.to_dict())
        return card

    async def update_card(self, session_id: str, card_id: str, **fields: object) -> Card:
        engine = self._card_engines.get(session_id)
        if engine is None:
            raise KeyError(f"No card engine for session {session_id}")
        card = engine.update_card(card_id, **fields)
        await self._store_call(self.store.save_card, session_id, card.to_dict())
        return card

    async def mark_card_done(self, session_id: str, card_id: str) -> Card:
        engine = self._card_engines.get(session_id)
        if engine is None:
            raise KeyError(f"No card engine for session {session_id}")
        card = engine.mark_done(card_id)
        await self._store_call(self.store.save_card, session_id, card.to_dict())
        return card

    async def delete_card(self, session_id: str, card_id: str) -> None:
        engine = self._card_engines.get(session_id)
        if engine is None:
            raise KeyError(f"No card engine for session {session_id}")
        engine.delete_card(card_id)
        await self._store_call(self.store.delete_card, session_id, card_id)

    def get_cards(self, session_id: str, agent_names: list[str] | list[dict]) -> list[dict]:
        engine = self.get_card_engine(session_id, agent_names)
        return [c.to_dict() for c in engine.get_cards()]

    async def start_card(self, session_id: str, card_id: str, agent_names: list[str] | list[dict]) -> None:
        """Begin the card lifecycle: backlog -> planning/coordinating. Triggers a single-agent round."""
        engine = self.get_card_engine(session_id, agent_names)
        card, prompt = engine.start_card(card_id)
        await self.broadcast(session_id, {"type": "card_updated", "card": card.to_dict()})
        # Determine which agent runs the first phase
        agent_name = self._resolve_card_agent(card)
        if not agent_name:
            log.warning("card %s has no agent for phase %s, cannot start", card_id, card.status.value)
            return
        await self.run_card_phase(session_id, card_id, prompt, agent_name, agent_names)

    async def run_card_phase(
        self,
        session_id: str,
        card_id: str,
        prompt: str,
        agent_name: str,
        agent_names: list[str] | list[dict],
    ) -> None:
        """Run a SINGLE-AGENT round for a card phase."""
        self._active_card_tasks[session_id] = card_id
        engine = self.get_card_engine(session_id, agent_names)
        card = engine.get_card(card_id)

        await self.broadcast(session_id, {
            "type": "card_phase_started",
            "card": card.to_dict(),
            "agent": agent_name,
            "prompt": prompt,
        })

        # Run single-agent round via run_prompt with only the assigned agent
        self.run_prompt(session_id, prompt, [agent_name])

    async def delegate_card(self, session_id: str, card_id: str, agent_names: list[str] | list[dict]) -> None:
        """Inject a delegation prompt as a multi-agent round (all agents discuss roles).

        If the card has a coordinator, run a single-agent coordinator round instead.
        """
        engine = self.get_card_engine(session_id, agent_names)
        card = engine.get_card(card_id)
        if card.coordinator:
            # Coordinator-only delegation: coordinator assigns all roles
            prompt = engine.build_delegation_prompt(card_id)
            self._delegation_cards[session_id] = card_id
            self._delegation_responses[session_id] = {}
            self.run_prompt(session_id, prompt, [card.coordinator])
            return
        prompt = engine.build_delegation_prompt(card_id)
        # Track this as a delegation round so responses get parsed on RoundEnded
        self._delegation_cards[session_id] = card_id
        self._delegation_responses[session_id] = {}
        # Delegation is a multi-agent round: all agents participate
        self.run_prompt(session_id, prompt, agent_names)

    def _cancel_idle_cleanup(self, session_id: str) -> None:
        task = self._idle_cleanup_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    def _schedule_idle_cleanup(self, session_id: str) -> None:
        if self.warmup_ttl <= 0:
            return
        if session_id in self._idle_cleanup_tasks:
            return

        async def _cleanup_after_idle() -> None:
            try:
                await asyncio.sleep(self.warmup_ttl)
                if self.is_running(session_id):
                    return
                if self._subscribers.get(session_id):
                    return
                self.cleanup_session(session_id)
            finally:
                self._idle_cleanup_tasks.pop(session_id, None)

        self._idle_cleanup_tasks[session_id] = asyncio.create_task(
            _cleanup_after_idle(),
            name=f"idle-cleanup-{session_id}",
        )

    async def _get_session_config(self, session_id: str) -> dict:
        """Get merged settings for a session (defaults -> global -> session -> CLI)."""
        if not self.settings_store:
            return {}
        session_data = await self._store_call(self.store.get_session, session_id)
        session_config = session_data.get("config", {}) if session_data else {}
        cli_overrides: dict = {}
        if self.timeout != 1800.0:
            cli_overrides["timeouts.idle"] = self.timeout
        if self.parse_timeout != 120.0:
            cli_overrides["timeouts.parse"] = self.parse_timeout
        if self.send_timeout != 120.0:
            cli_overrides["timeouts.send"] = self.send_timeout
        if self.hard_timeout:
            cli_overrides["timeouts.hard"] = self.hard_timeout
        return await self._store_call(
            self.settings_store.get_effective,
            session_config=session_config,
            cli_overrides=cli_overrides or None,
        )

    def _apply_config_to_agents(self, agents: list, config: dict) -> None:
        """Apply model and timeout settings from config to agents."""
        for agent in agents:
            agent_type = agent.agent_type or agent.name
            if not agent.model:
                model = config.get(f"agents.{agent_type}.model")
                if model:
                    agent.model = model
            # System prompt override
            if not agent.system_prompt_override:
                prompt_override = config.get(f"agents.{agent_type}.system_prompt")
                if prompt_override:
                    agent.system_prompt_override = prompt_override
            parse_t = config.get("timeouts.parse")
            if isinstance(parse_t, (int, float)):
                agent.parse_timeout = float(parse_t)
            hard_t = config.get("timeouts.hard")
            if isinstance(hard_t, (int, float)) and hard_t > 0:
                agent.hard_timeout = float(hard_t)

    def _apply_config_to_session(self, session_id: str, config: dict) -> None:
        """Apply non-agent settings from config to this session."""
        send_t = config.get("timeouts.send")
        if isinstance(send_t, (int, float)) and send_t > 0:
            self._session_send_timeouts[session_id] = float(send_t)
        else:
            self._session_send_timeouts.pop(session_id, None)

    async def _execute(self, session_id: str, prompt: str, agent_names: list[str] | list[dict], start_round: int = 0) -> None:
        # Wait for warmup to complete if it's still running
        if session_id in self._warmup_tasks:
            try:
                await self._warmup_tasks[session_id]
            except asyncio.CancelledError:
                pass

        # Use pre-warmed agents or create fresh ones
        agents = await self.get_warmed_agents(session_id, agent_names)

        # Apply settings from config
        config = await self._get_session_config(session_id)
        if config:
            self._apply_config_to_session(session_id, config)
            self._apply_config_to_agents(agents, config)
            idle_timeout = config.get("timeouts.idle", self.timeout)
        else:
            idle_timeout = self.timeout

        # Memory: start recorder if session has a working_dir
        from ..memory.recorder import SessionRecorder
        recorder: SessionRecorder | None = None
        session_data = await self._store_call(self.store.get_session, session_id)
        working_dir = session_data.get("working_dir", "") if session_data else ""
        if working_dir:
            try:
                recorder = SessionRecorder(Path(working_dir), session_id)
                if prompt:
                    recorder.record_user_message(prompt)
            except Exception:
                log.debug("memory recorder init failed for %s", working_dir, exc_info=True)
                recorder = None

        # Ensure all agents have their session IDs from storage
        agent_session_ids = await self._store_call(self.store.get_agent_session_ids, session_id)
        scripts_dir = str(Path(__file__).resolve().parent.parent.parent / "scripts")
        card_api_url = os.environ.get("MULTIAGENTS_URL", "http://localhost:8421")
        for agent in agents:
            if agent.session_id is None:
                cli_sid = agent_session_ids.get(agent.name)
                if cli_sid:
                    agent.session_id = cli_sid
            # Set project directory so agents CWD and prompts reflect it
            if working_dir:
                agent.project_dir = working_dir
            # Inject session context so agents can use the card CLI
            agent.extra_env = {
                "MULTIAGENTS_SESSION": session_id,
                "MULTIAGENTS_URL": card_api_url,
                "PATH": scripts_dir + os.pathsep + os.environ.get("PATH", ""),
            }

        # Memory: compute once before room creation (avoids N*R repeated lookups)
        memory_context = ""
        if working_dir:
            try:
                from ..memory.manager import MemoryManager
                extraction_model = config.get("memory.model", "haiku") if config else "haiku"
                mgr = MemoryManager(Path(working_dir), extraction_model=extraction_model)
                memory_context = mgr.build_memory_context(prompt or "")
            except Exception:
                log.debug("memory context failed", exc_info=True)

        def _build_extra_context(agent_name: str) -> dict[str, str]:
            sections: dict[str, str] = {}
            if memory_context:
                sections["memory"] = memory_context
            # Card context (still per-round — agents modify cards mid-discussion)
            engine = self._card_engines.get(session_id)
            if engine:
                cards = engine.get_cards()
                if cards:
                    section = format_cards_section(
                        [c.to_dict() for c in cards], agent_name,
                    )
                    if section:
                        sections["cards"] = section
            return sections

        # Build persona context for ChatRoom prompt generation
        participants = None
        roles: dict[str, str] = {}
        if agent_names and isinstance(agent_names[0], dict):
            participants = [{"name": a["name"], "type": a["type"]} for a in agent_names]
            roles = {a["name"]: a.get("role", "") for a in agent_names}

        room = ChatRoom(
            agents, timeout=idle_timeout, context_provider=_build_extra_context,
            working_dir=working_dir, participants=participants, roles=roles,
        )

        existing_messages = await self._store_call(self.store.get_messages, session_id)
        room.history = [{"role": m["role"], "content": m["content"]} for m in existing_messages]

        self._rooms[session_id] = room
        round_number = start_round
        await self._store_call(self.store.set_running, session_id, True)

        try:
            async for event in room.run(start_round=start_round):
                if isinstance(event, RoundStarted):
                    round_number = event.round_number
                    await self._store_call(self.store.set_current_round, session_id, round_number)
                    await self._store_call(self.store.reset_agent_progress, session_id, event.agents, round_number)
                    self._round_metrics[session_id] = RoundMetrics(
                        round_number=round_number,
                        started_at=time.monotonic(),
                        stream_chunks={name: 0 for name in event.agents},
                    )
                    if recorder:
                        recorder.record_round_started(event.round_number, event.agents)
                elif isinstance(event, AgentCompleted):
                    resp = event.response
                    await self._store_call(
                        self.store.save_message,
                        session_id,
                        resp.agent,
                        resp.response,
                        round_number=round_number,
                        passed=event.passed,
                    )
                    if resp.session_id:
                        await self._store_call(self.store.save_agent_session_id, session_id, resp.agent, resp.session_id)
                    status = "done" if resp.success else "failed"
                    await self._store_call(self.store.set_agent_status, session_id, resp.agent, status, round_number)
                    metrics = self._round_metrics.get(session_id)
                    if metrics:
                        metrics.latencies_ms[resp.agent] = resp.latency_ms
                    if recorder:
                        recorder.record_agent_completed(
                            resp.agent, resp.response, event.passed,
                            resp.latency_ms, round_number,
                        )
                    # Collect delegation responses
                    delegation_card_id = self._delegation_cards.get(session_id)
                    if delegation_card_id:
                        self._delegation_responses.setdefault(session_id, {})[resp.agent] = resp.response
                    # Card phase auto-advancement
                    active_card_id = self._active_card_tasks.get(session_id)
                    if active_card_id:
                        engine = self._card_engines.get(session_id)
                        if engine:
                            try:
                                card, next_prompt = engine.on_agent_completed(
                                    active_card_id, resp.agent, resp.response,
                                )
                                await self._store_call(self.store.save_card, session_id, card.to_dict())
                                await self.broadcast(session_id, {
                                    "type": "card_phase_completed",
                                    "card": card.to_dict(),
                                    "agent": resp.agent,
                                    "next_prompt": next_prompt,
                                })
                                if next_prompt:
                                    # Determine next agent based on current card status
                                    next_agent = self._resolve_card_agent(card)
                                    if next_agent:
                                        # Schedule next phase after a small delay
                                        # to let the broadcast complete first
                                        self._cancel_next_card_phase(session_id)
                                        token = self._card_phase_tokens.get(session_id, 0) + 1
                                        self._card_phase_tokens[session_id] = token
                                        expected_status = card.status
                                        task = asyncio.create_task(
                                            self._schedule_next_card_phase(
                                                session_id, active_card_id,
                                                next_prompt, next_agent, agent_names,
                                                token=token, expected_status=expected_status,
                                            ),
                                            name=f"card-phase-{session_id}",
                                        )
                                        self._card_phase_tasks[session_id] = task
                            except Exception:
                                log.exception(
                                    "card phase advance failed session=%s card=%s",
                                    session_id, active_card_id,
                                )
                elif isinstance(event, AgentStreamChunk):
                    await self._store_call(
                        self.store.append_agent_stream, session_id, event.agent_name, round_number, event.text,
                    )
                    metrics = self._round_metrics.get(session_id)
                    if metrics:
                        metrics.stream_chunks[event.agent_name] = metrics.stream_chunks.get(event.agent_name, 0) + 1
                elif isinstance(event, RoundEnded):
                    metrics = self._round_metrics.pop(session_id, None)
                    if metrics:
                        duration_ms = (time.monotonic() - metrics.started_at) * 1000
                        self._log_metric(
                            "round_summary",
                            session_id=session_id,
                            round=metrics.round_number,
                            duration_ms=round(duration_ms, 2),
                            stream_chunks=metrics.stream_chunks,
                            agent_latency_ms=metrics.latencies_ms,
                            send_failures=metrics.send_failures,
                        )
                    if recorder:
                        recorder.record_round_ended(round_number, event.all_passed)
                    # Parse delegation responses after the round ends
                    delegation_card_id = self._delegation_cards.pop(session_id, None)
                    if delegation_card_id:
                        responses = self._delegation_responses.pop(session_id, {})
                        engine = self._card_engines.get(session_id)
                        if engine and responses:
                            try:
                                card = engine.parse_delegation_response(
                                    delegation_card_id, responses,
                                )
                                if card:
                                    await self._store_call(self.store.save_card, session_id, card.to_dict())
                                    await self.broadcast(session_id, {
                                        "type": "card_updated",
                                        "card": card.to_dict(),
                                    })
                                    log.info(
                                        "delegation succeeded card=%s planner=%s implementer=%s reviewer=%s",
                                        card.id, card.planner, card.implementer, card.reviewer,
                                    )
                                else:
                                    log.warning(
                                        "delegation incomplete card=%s — not all roles assigned",
                                        delegation_card_id,
                                    )
                            except Exception:
                                log.exception(
                                    "delegation parsing failed session=%s card=%s",
                                    session_id, delegation_card_id,
                                )
                await self.broadcast(session_id, event_to_dict(event))
        except asyncio.CancelledError:
            log.info("session cancelled: %s", session_id)
            await self.broadcast(session_id, {"type": "discussion_ended", "reason": "cancelled"})
        except Exception:
            log.exception("session error: %s", session_id)
            await self.broadcast(session_id, {"type": "error", "message": "Internal error"})
        finally:
            await self._store_call(self.store.clear_in_flight, session_id)
            await self._store_call(self.store.clear_events, session_id)
            self._tasks.pop(session_id, None)
            self._rooms.pop(session_id, None)
            self._round_metrics.pop(session_id, None)
            self._send_failures.pop(session_id, None)
            self._active_card_tasks.pop(session_id, None)
            self._delegation_cards.pop(session_id, None)
            self._delegation_responses.pop(session_id, None)
            # Memory: close recorder and finalize episode in background
            if recorder:
                recorder.record_discussion_ended("session_end", round_number)
                recorder.close()
                if working_dir:
                    from ..memory.manager import MemoryManager
                    _wd = working_dir
                    _sid = session_id
                    asyncio.create_task(
                        asyncio.to_thread(MemoryManager(Path(_wd)).finalize_session, _sid)
                    )
            # Clean up warmed agents when discussion ends
            self.cleanup_session(session_id, cancel_card_phase_tasks=False)
            self._start_pending_run(session_id)

    @staticmethod
    def _resolve_card_agent(card: Card) -> str | None:
        """Determine which agent should run the current card phase."""
        if card.status == CardStatus.COORDINATING:
            return card.coordinator or None
        if card.status == CardStatus.PLANNING:
            return card.planner or None
        if card.status == CardStatus.IMPLEMENTING:
            return card.implementer or None
        if card.status == CardStatus.REVIEWING:
            return card.reviewer or None
        return None

    async def _schedule_next_card_phase(
        self,
        session_id: str,
        card_id: str,
        prompt: str,
        agent_name: str,
        agent_names: list[str] | list[dict],
        token: int,
        expected_status: CardStatus,
    ) -> None:
        """Wait briefly then kick off the next card phase."""
        try:
            await asyncio.sleep(0.1)
            if self._card_phase_tokens.get(session_id) != token:
                return
            if self._active_card_tasks.get(session_id) != card_id:
                return
            engine = self._card_engines.get(session_id)
            if not engine:
                return
            try:
                card = engine.get_card(card_id)
            except KeyError:
                return
            if card.status != expected_status:
                return
            current = self._card_phase_tasks.get(session_id)
            if current is asyncio.current_task():
                self._card_phase_tasks.pop(session_id, None)
            await self.run_card_phase(session_id, card_id, prompt, agent_name, agent_names)
        except Exception:
            log.exception(
                "failed to schedule next card phase session=%s card=%s",
                session_id, card_id,
            )
        finally:
            current = self._card_phase_tasks.get(session_id)
            if current is asyncio.current_task():
                self._card_phase_tasks.pop(session_id, None)
