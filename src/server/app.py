from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone

from fastapi.responses import FileResponse, JSONResponse, Response

from .runner import SessionRunner
from .sessions import SessionStore
from .settings import SettingsStore

log = logging.getLogger("multiagents")

# --- WebSocket message validation ---

_MAX_WS_MESSAGE_SIZE = 1 * 1024 * 1024  # 1 MB

_VALID_MSG_TYPES = frozenset({
    "create_session", "join_session", "message", "stop_agent", "stop_round",
    "resume", "cancel", "direct_message", "add_agent", "remove_agent",
    "ack", "metric", "card_create", "card_update", "card_start",
    "card_delegate", "card_done", "card_delete", "permission_response",
})

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "join_session": ["session_id"],
    "message": ["text"],
    "stop_agent": ["agent"],
    "direct_message": ["agent", "text"],
    "add_agent": ["name", "agent_type"],
    "ack": ["event_id"],
    "card_create": ["title"],
    "card_update": ["card_id"],
    "card_start": ["card_id"],
    "card_delegate": ["card_id"],
    "card_done": ["card_id"],
    "card_delete": ["card_id"],
    "permission_response": ["request_id"],
}

# Rate limiting: max messages per window
_RATE_LIMIT_WINDOW = 10.0  # seconds
_RATE_LIMIT_MAX = 100  # messages per window
_SUPPORTED_AGENT_TYPES = frozenset({"claude", "codex", "kimi"})


def _validate_ws_message(msg: dict) -> str | None:
    """Validate a WebSocket message shape. Returns error string or None."""
    if not isinstance(msg, dict):
        return "Message must be a JSON object"
    msg_type = msg.get("type")
    if not isinstance(msg_type, str):
        return "Missing or invalid 'type' field"
    if msg_type not in _VALID_MSG_TYPES:
        return f"Unknown message type: {msg_type}"
    required = _REQUIRED_FIELDS.get(msg_type, [])
    for field in required:
        if field not in msg or msg[field] is None:
            return f"Missing required field '{field}' for {msg_type}"
    return None

_DEFAULT_AGENTS = [
    {"name": "claude", "type": "claude", "role": "", "model": None},
    {"name": "codex", "type": "codex", "role": "", "model": None},
    {"name": "kimi", "type": "kimi", "role": "", "model": None},
]


def create_app(
    default_agents: list[str] | list[dict] | None = None,
    timeout: float = 1800.0,
    parse_timeout: float = 1200.0,
    send_timeout: float = 120.0,
    hard_timeout: float | None = None,
    warmup_ttl: float = 300.0,
    ack_ttl: float = 300.0,
    session_store: SessionStore | None = None,
    settings_store: SettingsStore | None = None,
) -> FastAPI:
    store = session_store or SessionStore()
    settings = settings_store or SettingsStore(store.db_path)
    agents_list = list(default_agents or _DEFAULT_AGENTS)
    # Normalize to persona dicts if strings
    if agents_list and isinstance(agents_list[0], str):
        agents_list = [{"name": a, "type": a, "role": "", "model": None} for a in agents_list]
    runner = SessionRunner(
        store=store,
        timeout=timeout,
        parse_timeout=parse_timeout,
        send_timeout=send_timeout,
        hard_timeout=hard_timeout,
        warmup_ttl=warmup_ttl,
        ack_ttl=ack_ttl,
        settings_store=settings,
    )

    async def _store_call(fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    def _agents_with_models(spec: list[str] | list[dict]) -> list[dict]:
        """Normalize agent specs and attach configured model when not explicitly set."""
        normalized: list[dict] = []
        for item in spec:
            if isinstance(item, str):
                agent_type = item
                model = settings.get(f"agents.{agent_type}.model")
                normalized.append({"name": item, "type": agent_type, "role": "", "model": model})
                continue
            agent_type = item.get("type", "")
            model = item.get("model")
            if not model and agent_type:
                model = settings.get(f"agents.{agent_type}.model")
            normalized.append({
                "name": item.get("name", agent_type),
                "type": agent_type,
                "role": item.get("role", ""),
                "model": model,
            })
        return normalized

    def _validate_session_config(config: dict | None) -> str | None:
        if config is None:
            return None
        if not isinstance(config, dict):
            return "config must be an object"
        from .settings import DEFAULTS
        invalid = [k for k in config if k not in DEFAULTS]
        if invalid:
            return f"Unknown settings keys: {invalid}"
        return None

    def _validate_create_session_agents(agents: object) -> str | None:
        if not isinstance(agents, list):
            return "'agents' must be an array"
        if not agents:
            return "'agents' must include at least one agent"
        seen_names: set[str] = set()
        for i, item in enumerate(agents):
            if isinstance(item, str):
                agent_type = item.strip()
                if not agent_type:
                    return f"Invalid agents[{i}]: agent name/type cannot be empty"
                name = agent_type
            elif isinstance(item, dict):
                raw_type = item.get("type")
                if not isinstance(raw_type, str) or not raw_type.strip():
                    return f"Invalid agents[{i}]: 'type' must be a non-empty string"
                agent_type = raw_type.strip()
                raw_name = item.get("name", agent_type)
                if not isinstance(raw_name, str) or not raw_name.strip():
                    return f"Invalid agents[{i}]: 'name' must be a non-empty string"
                name = raw_name.strip()
                role = item.get("role", "")
                if not isinstance(role, str):
                    return f"Invalid agents[{i}]: 'role' must be a string"
                model = item.get("model")
                if model is not None and not isinstance(model, str):
                    return f"Invalid agents[{i}]: 'model' must be a string or null"
            else:
                return f"Invalid agents[{i}]: expected string or object"

            if agent_type not in _SUPPORTED_AGENT_TYPES:
                return (
                    f"Invalid agents[{i}]: unsupported agent type '{agent_type}'. "
                    f"Supported types: {sorted(_SUPPORTED_AGENT_TYPES)}"
                )
            name_key = name.lower()
            if name_key in seen_names:
                return f"Invalid agents: duplicate name '{name}'"
            seen_names.add(name_key)
        return None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Finalize any unprocessed transcripts from previous runs."""
        from pathlib import Path
        from ..memory.manager import MemoryManager

        sessions = await _store_call(store.list_sessions)
        for sess in sessions:
            full = await _store_call(store.get_session, sess["id"])
            if not full:
                continue
            wd = full.get("working_dir", "")
            if not wd:
                continue
            try:
                mgr = MemoryManager(Path(wd))
                pending = mgr.get_pending_transcripts()
                if pending:
                    log.info("recovering %d pending transcripts for %s", len(pending), wd)
                    for p in pending:
                        await asyncio.to_thread(mgr.finalize_session, p.stem)
            except Exception:
                log.debug("memory recovery failed for %s", wd, exc_info=True)
        yield

    app = FastAPI(title="Multiagents", lifespan=lifespan)

    @app.get("/health")
    async def health_check():
        """Health check endpoint that also reports agent warmup status."""
        sessions = await _store_call(store.list_sessions)
        health = {
            "status": "healthy",
            "sessions": len(sessions),
            "warmup_tasks": len(runner._warmup_tasks),
            "agent_pools": {sid: list(pool.keys()) for sid, pool in runner._agent_pools.items()},
        }
        return health

    @app.get("/api/sessions")
    def list_sessions():
        return store.list_sessions()

    @app.post("/api/sessions")
    def create_session(body: dict | None = None):
        working_dir = (body or {}).get("working_dir", "")
        if working_dir:
            working_dir = str(Path(working_dir).expanduser().resolve())
        session_config = (body or {}).get("config")
        error = _validate_session_config(session_config)
        if error:
            return JSONResponse(status_code=400, content={"detail": error})
        return store.create_session(
            agent_names=_agents_with_models(agents_list),
            working_dir=working_dir,
            config=session_config,
        )

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str):
        session = await _store_call(store.get_session, session_id)
        if session is None:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        await runner.delete_session(session_id)
        return {"ok": True}

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str):
        session = store.get_session(session_id)
        if session is None:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return session

    @app.get("/api/sessions/{session_id}/messages")
    def get_messages(session_id: str):
        return store.get_messages(session_id)

    @app.get("/api/sessions/{session_id}/export")
    def export_session(session_id: str):
        session = store.get_session(session_id)
        if session is None:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        messages = store.get_messages(session_id)
        cards = runner.get_cards(session_id, session["agent_names"])
        payload = json.dumps(
            {
                "session": session,
                "messages": messages,
                "cards": cards,
                "exported_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
            default=str,
        )
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="session-{session_id}.json"'},
        )

    @app.get("/api/sessions/{session_id}/status")
    def get_status(session_id: str):
        status = store.get_status(session_id)
        if status is None:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return status

    @app.get("/api/filesystem/list")
    def list_directory(path: str = "~"):
        from pathlib import Path as P
        target = P(os.path.expanduser(path)).resolve()
        if not target.is_dir():
            return JSONResponse(status_code=400, content={"detail": "Not a directory"})
        dirs = []
        try:
            with os.scandir(str(target)) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False) and not entry.name.startswith("."):
                            dirs.append(entry.name)
                    except PermissionError:
                        continue
        except PermissionError:
            return JSONResponse(status_code=403, content={"detail": "Permission denied"})
        dirs.sort(key=str.lower)
        return {
            "path": str(target),
            "parent": str(target.parent) if target.parent != target else None,
            "directories": dirs,
        }

    # --- Settings REST API ---

    @app.get("/api/settings")
    def get_settings():
        return settings.get_all()

    @app.put("/api/settings")
    def update_settings(body: dict):
        from .settings import DEFAULTS
        invalid = [k for k in body if k not in DEFAULTS]
        if invalid:
            return JSONResponse(status_code=400, content={"detail": f"Unknown settings keys: {invalid}"})
        settings.set_many(body)
        return settings.get_all()

    @app.get("/api/settings/{key:path}")
    def get_setting(key: str):
        return {"key": key, "value": settings.get(key)}

    @app.put("/api/settings/{key:path}")
    def update_setting(key: str, body: dict):
        from .settings import DEFAULTS
        if key not in DEFAULTS:
            return JSONResponse(status_code=400, content={"detail": f"Unknown settings key: {key}"})
        if "value" not in body:
            return JSONResponse(status_code=400, content={"detail": "Missing 'value' in request body"})
        settings.set(key, body["value"])
        return {"key": key, "value": body["value"]}

    @app.delete("/api/settings/{key:path}")
    def delete_setting(key: str):
        settings.delete(key)
        return {"ok": True}
    # --- Card REST API (used by agents via CLI script) ---

    @app.get("/api/sessions/{session_id}/cards")
    def list_cards(session_id: str, status: str | None = None, assignee: str | None = None, role: str | None = None):
        session = store.get_session(session_id)
        if session is None:
            return JSONResponse(status_code=404, content={"detail": "Session not found"})
        cards = runner.get_cards(session_id, session["agent_names"])
        if status:
            cards = [c for c in cards if c["status"] == status]
        if assignee:
            name = assignee.lower()
            if role:
                role_key = role.lower()
                cards = [c for c in cards if c.get(role_key, "").lower() == name]
            else:
                cards = [c for c in cards if name in (c.get("planner", "").lower(), c.get("implementer", "").lower(), c.get("reviewer", "").lower(), c.get("coordinator", "").lower())]
        return cards

    @app.get("/api/sessions/{session_id}/cards/{card_id}")
    def get_card(session_id: str, card_id: str):
        session = store.get_session(session_id)
        if session is None:
            return JSONResponse(status_code=404, content={"detail": "Session not found"})
        engine = runner.get_card_engine(session_id, session["agent_names"])
        try:
            return engine.get_card(card_id).to_dict()
        except KeyError:
            return JSONResponse(status_code=404, content={"detail": "Card not found"})

    @app.post("/api/sessions/{session_id}/cards")
    async def create_card_rest(session_id: str, body: dict):
        session = await _store_call(store.get_session, session_id)
        if session is None:
            return JSONResponse(status_code=404, content={"detail": "Session not found"})
        card = await runner.create_card(
            session_id, session["agent_names"],
            title=body.get("title", ""),
            description=body.get("description", ""),
            planner=body.get("planner", ""),
            implementer=body.get("implementer", ""),
            reviewer=body.get("reviewer", ""),
            coordinator=body.get("coordinator", ""),
        )
        await runner.broadcast(session_id, {"type": "card_created", "card": card.to_dict()})
        return card.to_dict()

    @app.patch("/api/sessions/{session_id}/cards/{card_id}")
    async def update_card_rest(session_id: str, card_id: str, body: dict):
        session = await _store_call(store.get_session, session_id)
        if session is None:
            return JSONResponse(status_code=404, content={"detail": "Session not found"})
        fields = {k: v for k, v in body.items() if v is not None}
        try:
            card = await runner.update_card(session_id, card_id, **fields)
            await runner.broadcast(session_id, {"type": "card_updated", "card": card.to_dict()})
            return card.to_dict()
        except KeyError as exc:
            return JSONResponse(status_code=404, content={"detail": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.delete("/api/sessions/{session_id}/cards/{card_id}")
    async def delete_card_rest(session_id: str, card_id: str):
        session = await _store_call(store.get_session, session_id)
        if session is None:
            return JSONResponse(status_code=404, content={"detail": "Session not found"})
        try:
            await runner.delete_card(session_id, card_id)
            await runner.broadcast(session_id, {"type": "card_deleted", "card_id": card_id})
            return {"ok": True}
        except KeyError as exc:
            return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        log.info("ws connected")
        session_id: str | None = None
        await ws.send_json({"type": "connected", "agents": _agents_with_models(agents_list)})

        # Rate limiting state
        _rate_timestamps: list[float] = []

        try:
            while True:
                # Receive raw text first for size checking
                raw = await ws.receive_text()
                if len(raw) > _MAX_WS_MESSAGE_SIZE:
                    await ws.send_json({"type": "error", "message": f"Message too large (max {_MAX_WS_MESSAGE_SIZE} bytes)"})
                    continue

                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    await ws.send_json({"type": "error", "message": "Invalid JSON"})
                    continue

                # Schema validation
                validation_error = _validate_ws_message(msg)
                if validation_error:
                    await ws.send_json({"type": "error", "message": validation_error})
                    continue

                # Rate limiting
                now = time.monotonic()
                _rate_timestamps = [t for t in _rate_timestamps if now - t < _RATE_LIMIT_WINDOW]
                _rate_timestamps.append(now)
                if len(_rate_timestamps) > _RATE_LIMIT_MAX:
                    await ws.send_json({"type": "error", "message": "Rate limit exceeded, slow down"})
                    continue

                msg_type = msg.get("type")

                if msg_type == "create_session":
                    working_dir = msg.get("working_dir", "")
                    if working_dir:
                        working_dir = str(Path(working_dir).expanduser().resolve())
                    agents_spec = msg.get("agents", agents_list)
                    if "agents" in msg:
                        error = _validate_create_session_agents(agents_spec)
                        if error:
                            await ws.send_json({"type": "error", "message": error})
                            continue
                    agents_spec = _agents_with_models(agents_spec)
                    session_config = msg.get("config")
                    error = _validate_session_config(session_config)
                    if error:
                        await ws.send_json({"type": "error", "message": error})
                        continue
                    session = await _store_call(
                        store.create_session,
                        agent_names=agents_spec,
                        working_dir=working_dir,
                        config=session_config,
                    )
                    session_id = session["id"]
                    runner.subscribe(session_id, ws)
                    # Start warming agents in background for faster first response
                    runner.start_warmup(session_id, session["agent_names"])
                    # Auto-init .multiagents/ in working_dir if specified
                    if working_dir:
                        from ..memory.cli import init_project
                        try:
                            init_project(Path(working_dir))
                        except Exception:
                            log.debug("failed to init memory in %s", working_dir, exc_info=True)
                    await ws.send_json({"type": "session_created", "session_id": session_id, "agents": session["agent_names"]})

                elif msg_type == "join_session":
                    sid = msg.get("session_id")
                    if not sid:
                        await ws.send_json({"type": "error", "message": "Missing session_id"})
                        continue
                    session = await _store_call(store.get_session, sid)
                    if session is None:
                        await ws.send_json({"type": "error", "message": "Session not found"})
                    else:
                        session_id = sid
                        runner.subscribe(session_id, ws)
                        # Start warming agents if not already warmed
                        runner.start_warmup(session_id, session["agent_names"])
                        messages = await _store_call(store.get_messages, session_id)
                        state = await _store_call(store.get_session_state, session_id)
                        in_flight = None
                        is_running = runner.is_running(session_id)
                        if state and state.get("is_running"):
                            if not is_running:
                                start_round = max(state.get("current_round", 0) - 1, 0)
                                runner.run_prompt(
                                    session_id=session_id,
                                    prompt="",
                                    agent_names=session["agent_names"],
                                    start_round=start_round,
                                )
                                is_running = True
                            progress = await _store_call(store.get_agent_progress, session_id)
                            in_flight = {
                                "round": state.get("current_round", 0),
                                "agent_streams": {k: v.get("stream_text", "") for k, v in progress.items()},
                                "agent_statuses": {k: v.get("status", "idle") for k, v in progress.items()},
                            }
                        cards = runner.get_cards(session_id, session["agent_names"])
                        await ws.send_json({
                            "type": "session_joined", "session_id": session_id,
                            "title": session.get("title", ""), "agents": _agents_with_models(session["agent_names"]),
                            "messages": messages, "is_running": is_running, "in_flight": in_flight,
                            "cards": cards,
                        })
                        last_event_id = msg.get("last_event_id")
                        if isinstance(last_event_id, int) and last_event_id > 0:
                            await runner.replay_events(session_id, last_event_id, ws)

                elif msg_type == "message":
                    if not session_id:
                        await ws.send_json({"type": "error", "message": "No session"})
                        continue
                    text = msg.get("text", "").strip()
                    if not text:
                        continue
                    if runner.is_running(session_id):
                        runner.inject_message(session_id, text)
                        await _store_call(store.save_message, session_id, "user", text)
                    else:
                        saved = await _store_call(store.save_message, session_id, "user", text)
                        await runner.broadcast(session_id, {"type": "user_message", "text": text, "created_at": saved["created_at"]})
                        messages = await _store_call(store.get_messages, session_id)
                        if len(messages) == 1:
                            title = text[:50] + ("..." if len(text) > 50 else "")
                            await _store_call(store.update_title, session_id, title)
                            await runner.broadcast(session_id, {"type": "title_changed", "title": title})
                        session = await _store_call(store.get_session, session_id)
                        runner.run_prompt(session_id=session_id, prompt=text, agent_names=session["agent_names"])

                elif msg_type == "stop_agent":
                    if session_id:
                        agent_name = msg.get("agent", "")
                        if agent_name:
                            runner.stop_agent(session_id, agent_name)

                elif msg_type == "stop_round":
                    if session_id:
                        runner.stop_round(session_id)

                elif msg_type == "resume":
                    if session_id:
                        runner.resume(session_id)

                elif msg_type == "direct_message":
                    if not session_id:
                        await ws.send_json({"type": "error", "message": "No session"})
                        continue
                    agent_name = msg.get("agent", "").strip()
                    text = msg.get("text", "").strip()
                    if not agent_name or not text:
                        continue
                    session = await _store_call(store.get_session, session_id)
                    existing_names = [a["name"] for a in (session or {}).get("agent_names", [])]
                    if agent_name not in existing_names:
                        await ws.send_json({"type": "error", "message": f"Unknown agent: {agent_name}"})
                        continue
                    # Save DM as a special message type for replay
                    saved = await _store_call(store.save_message, session_id, f"dm:{agent_name}", text)
                    # Broadcast so all connected clients see it
                    state_data = await _store_call(store.get_session_state, session_id)
                    current_round = state_data.get("current_round", 0) if state_data else 0
                    await runner.broadcast(session_id, {
                        "type": "dm_sent", "agent": agent_name,
                        "text": text, "round": current_round, "created_at": saved["created_at"],
                    })
                    if runner.is_running(session_id):
                        # Active round — queue a DM for the target agent
                        await runner.restart_agent(session_id, agent_name, text)
                    else:
                        # No active round — start a single-agent round with the DM
                        dm_prompt = f"[Direct message to {agent_name}]: {text}"
                        await _store_call(store.save_message, session_id, "user", dm_prompt)
                        runner.run_prompt(session_id, dm_prompt, [agent_name], start_round=current_round)

                elif msg_type == "add_agent":
                    if not session_id:
                        await ws.send_json({"type": "error", "message": "No session"})
                        continue
                    name = msg.get("name", "").strip()
                    agent_type = msg.get("agent_type", "").strip()
                    role = msg.get("role", "")
                    if not name or not agent_type:
                        await ws.send_json({"type": "error", "message": "Missing name or agent_type"})
                        continue
                    if agent_type not in ("claude", "codex", "kimi"):
                        await ws.send_json({"type": "error", "message": f"Unknown agent type: {agent_type}"})
                        continue
                    session = await _store_call(store.get_session, session_id)
                    existing_names = [a["name"] for a in session["agent_names"]]
                    if name in existing_names:
                        await ws.send_json({"type": "error", "message": f"Agent name '{name}' already exists"})
                        continue
                    persona = _agents_with_models([{"name": name, "type": agent_type, "role": role}])[0]
                    updated_agents = session["agent_names"] + [persona]
                    await _store_call(store.update_agents, session_id, updated_agents)
                    await _store_call(store.add_agent_state, session_id, name)
                    await runner.add_agent(session_id, persona)
                    await runner.broadcast(session_id, {
                        "type": "agent_added",
                        "name": name,
                        "agent_type": agent_type,
                        "role": role,
                        "model": persona.get("model"),
                    })

                elif msg_type == "remove_agent":
                    if not session_id:
                        await ws.send_json({"type": "error", "message": "No session"})
                        continue
                    name = msg.get("name", "").strip()
                    if not name:
                        continue
                    session = await _store_call(store.get_session, session_id)
                    updated_agents = [a for a in session["agent_names"] if a["name"] != name]
                    if len(updated_agents) == len(session["agent_names"]):
                        await ws.send_json({"type": "error", "message": f"Agent '{name}' not found"})
                        continue
                    await _store_call(store.update_agents, session_id, updated_agents)
                    await _store_call(store.remove_agent_state, session_id, name)
                    await runner.remove_agent(session_id, name)
                    await runner.broadcast(session_id, {"type": "agent_removed", "name": name})

                elif msg_type == "cancel":
                    if session_id:
                        await runner.cancel(session_id)

                elif msg_type == "ack":
                    if session_id:
                        event_id = msg.get("event_id")
                        if isinstance(event_id, int):
                            await runner.ack(session_id, ws, event_id)

                elif msg_type == "metric":
                    name = msg.get("name")
                    value = msg.get("value")
                    metric_sid = msg.get("session_id") or session_id
                    if isinstance(name, str) and isinstance(value, (int, float)):
                        runner.log_client_metric(name, metric_sid, float(value))

                elif msg_type == "permission_response":
                    if session_id:
                        request_id = msg.get("request_id", "")
                        approved = msg.get("approved", False)
                        agent_name = msg.get("agent")  # target specific agent if provided
                        runner.resolve_permission(session_id, request_id, approved, agent_name=agent_name)

                elif msg_type == "card_create":
                    if not session_id:
                        await ws.send_json({"type": "error", "message": "No session"})
                        continue
                    title = msg.get("title", "")
                    description = msg.get("description", "")
                    planner = msg.get("planner", "")
                    implementer = msg.get("implementer", "")
                    reviewer = msg.get("reviewer", "")
                    coordinator = msg.get("coordinator", "")
                    try:
                        card = await runner.create_card(
                            session_id, agents_list, title, description,
                            planner, implementer, reviewer, coordinator,
                        )
                        await runner.broadcast(session_id, {"type": "card_created", "card": card.to_dict()})
                    except Exception as exc:
                        await ws.send_json({"type": "error", "message": str(exc)})

                elif msg_type == "card_update":
                    if not session_id:
                        await ws.send_json({"type": "error", "message": "No session"})
                        continue
                    card_id = msg.get("card_id")
                    if not card_id:
                        await ws.send_json({"type": "error", "message": "Missing card_id"})
                        continue
                    fields = {k: v for k, v in msg.items() if k not in ("type", "card_id") and v is not None}
                    try:
                        card = await runner.update_card(session_id, card_id, **fields)
                        await runner.broadcast(session_id, {"type": "card_updated", "card": card.to_dict()})
                    except Exception as exc:
                        await ws.send_json({"type": "error", "message": str(exc)})

                elif msg_type == "card_start":
                    if not session_id:
                        await ws.send_json({"type": "error", "message": "No session"})
                        continue
                    card_id = msg.get("card_id")
                    if not card_id:
                        await ws.send_json({"type": "error", "message": "Missing card_id"})
                        continue
                    try:
                        session = await _store_call(store.get_session, session_id)
                        await runner.start_card(session_id, card_id, session["agent_names"])
                    except Exception as exc:
                        await ws.send_json({"type": "error", "message": str(exc)})

                elif msg_type == "card_delegate":
                    if not session_id:
                        await ws.send_json({"type": "error", "message": "No session"})
                        continue
                    card_id = msg.get("card_id")
                    if not card_id:
                        await ws.send_json({"type": "error", "message": "Missing card_id"})
                        continue
                    try:
                        session = await _store_call(store.get_session, session_id)
                        await runner.delegate_card(session_id, card_id, session["agent_names"])
                    except Exception as exc:
                        await ws.send_json({"type": "error", "message": str(exc)})

                elif msg_type == "card_done":
                    if not session_id:
                        await ws.send_json({"type": "error", "message": "No session"})
                        continue
                    card_id = msg.get("card_id")
                    if not card_id:
                        await ws.send_json({"type": "error", "message": "Missing card_id"})
                        continue
                    try:
                        card = await runner.mark_card_done(session_id, card_id)
                        await runner.broadcast(session_id, {"type": "card_updated", "card": card.to_dict()})
                    except Exception as exc:
                        await ws.send_json({"type": "error", "message": str(exc)})

                elif msg_type == "card_delete":
                    if not session_id:
                        await ws.send_json({"type": "error", "message": "No session"})
                        continue
                    card_id = msg.get("card_id")
                    if not card_id:
                        await ws.send_json({"type": "error", "message": "Missing card_id"})
                        continue
                    try:
                        await runner.delete_card(session_id, card_id)
                        await runner.broadcast(session_id, {"type": "card_deleted", "card_id": card_id})
                    except Exception as exc:
                        await ws.send_json({"type": "error", "message": str(exc)})

        except WebSocketDisconnect:
            log.info("ws disconnected")
            if session_id:
                runner.unsubscribe(session_id, ws)

    # Serve static files if STATIC_DIR is set (production mode)
    static_dir = os.environ.get("STATIC_DIR")
    if static_dir and os.path.isdir(static_dir):
        log.info("Serving static files from: %s", static_dir)

        @app.get("/")
        async def serve_index():
            return FileResponse(os.path.join(static_dir, "index.html"))

        @app.get("/{path:path}")
        async def serve_static(path: str):
            file_path = os.path.join(static_dir, path)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                return FileResponse(file_path)
            # Fallback to index.html for SPA routing
            return FileResponse(os.path.join(static_dir, "index.html"))

    return app
