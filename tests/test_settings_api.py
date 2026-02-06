import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from src.server.app import create_app
from src.server.sessions import SessionStore
from src.server.settings import SettingsStore


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    session_store = SessionStore(db_path)
    settings_store = SettingsStore(db_path)
    return create_app(session_store=session_store, settings_store=settings_store)


@pytest.fixture
def client(app):
    return TestClient(app)


def test_get_settings_returns_defaults(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["timeouts.idle"] == 1800
    assert data["agents.enabled"] == ["claude", "codex", "kimi"]
    assert data["ui.layout.default"] == "split"
    assert data["ui.layout.allow_switch"] is True
    assert data["ui.layout.split_enabled"] is True
    assert data["ui.theme.mode"] == "dark"
    assert data["ui.theme.accent"] == "cyan"
    assert data["ui.theme.density"] == "cozy"


def test_put_settings_bulk_update(client):
    resp = client.put("/api/settings", json={
        "timeouts.idle": 900,
        "ui.layout.default": "chat",
        "ui.theme.mode": "light",
        "ui.theme.accent": "amber",
        "ui.theme.density": "compact",
    })
    assert resp.status_code == 200
    resp = client.get("/api/settings")
    assert resp.json()["timeouts.idle"] == 900
    assert resp.json()["ui.layout.default"] == "chat"
    assert resp.json()["ui.theme.mode"] == "light"
    assert resp.json()["ui.theme.accent"] == "amber"
    assert resp.json()["ui.theme.density"] == "compact"


def test_get_single_setting(client):
    resp = client.get("/api/settings/timeouts.idle")
    assert resp.status_code == 200
    assert resp.json()["value"] == 1800


def test_put_single_setting(client):
    resp = client.put("/api/settings/timeouts.idle", json={"value": 600})
    assert resp.status_code == 200
    resp = client.get("/api/settings/timeouts.idle")
    assert resp.json()["value"] == 600


def test_delete_setting_resets_to_default(client):
    client.put("/api/settings/timeouts.idle", json={"value": 600})
    resp = client.delete("/api/settings/timeouts.idle")
    assert resp.status_code == 200
    resp = client.get("/api/settings/timeouts.idle")
    assert resp.json()["value"] == 1800


def test_put_bulk_rejects_unknown_keys(client):
    resp = client.put("/api/settings", json={"bogus.key": 42})
    assert resp.status_code == 400
    assert "Unknown" in resp.json()["detail"]


def test_put_single_requires_value_key(client):
    resp = client.put("/api/settings/timeouts.idle", json={"wrong": 42})
    assert resp.status_code == 400


def test_create_session_with_config(client):
    resp = client.post("/api/sessions", json={
        "config": {"agents.claude.model": "opus", "timeouts.idle": 900}
    })
    assert resp.status_code == 200
    session = resp.json()
    assert session["config"]["agents.claude.model"] == "opus"
    assert session["config"]["timeouts.idle"] == 900


def test_get_session_returns_config(client):
    create_resp = client.post("/api/sessions", json={
        "config": {"agents.claude.model": "opus"}
    })
    session_id = create_resp.json()["id"]
    get_resp = client.get(f"/api/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["config"]["agents.claude.model"] == "opus"


def test_create_session_rejects_unknown_config_key(client):
    resp = client.post("/api/sessions", json={
        "config": {"bogus.key": 42}
    })
    assert resp.status_code == 400
    assert "Unknown settings keys" in resp.json()["detail"]


def test_ws_create_session_persists_config(client):
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        ws.send_json({
            "type": "create_session",
            "config": {"agents.claude.model": "opus", "timeouts.idle": 900},
        })
        created = ws.receive_json()
        assert created["type"] == "session_created"
        session_id = created["session_id"]
    resp = client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["config"]["agents.claude.model"] == "opus"
    assert resp.json()["config"]["timeouts.idle"] == 900


def test_ws_create_session_rejects_unknown_config_key(client):
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        ws.send_json({
            "type": "create_session",
            "config": {"bogus.key": 1},
        })
        err = ws.receive_json()
        assert err["type"] == "error"
        assert "Unknown settings keys" in err["message"]


def test_ws_create_session_rejects_non_array_agents(client):
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        ws.send_json({
            "type": "create_session",
            "agents": "claude",
        })
        err = ws.receive_json()
        assert err["type"] == "error"
        assert "'agents' must be an array" in err["message"]


def test_ws_create_session_rejects_duplicate_agent_names(client):
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        ws.send_json({
            "type": "create_session",
            "agents": [
                {"name": "codex", "type": "codex", "role": ""},
                {"name": "codex", "type": "claude", "role": ""},
            ],
        })
        err = ws.receive_json()
        assert err["type"] == "error"
        assert "duplicate name 'codex'" in err["message"]


def test_ws_create_session_rejects_unsupported_agent_type(client):
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        ws.send_json({
            "type": "create_session",
            "agents": [{"name": "writer", "type": "gpt", "role": ""}],
        })
        err = ws.receive_json()
        assert err["type"] == "error"
        assert "unsupported agent type 'gpt'" in err["message"]


def test_ws_running_message_not_double_broadcast(monkeypatch, tmp_path):
    class FakeRunner:
        last_instance = None

        def __init__(self, **kwargs):
            FakeRunner.last_instance = self
            self.broadcast_calls = []

        def subscribe(self, session_id, ws):
            return None

        def unsubscribe(self, session_id, ws):
            return None

        def start_warmup(self, session_id, agent_names):
            return None

        def is_running(self, session_id):
            return True

        def inject_message(self, session_id, text):
            return None

        async def broadcast(self, session_id, data):
            self.broadcast_calls.append(data)
            return 1

    monkeypatch.setattr("src.server.app.SessionRunner", FakeRunner)

    db_path = tmp_path / "test.db"
    session_store = SessionStore(db_path)
    settings_store = SettingsStore(db_path)
    app = create_app(session_store=session_store, settings_store=settings_store)
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        connected = ws.receive_json()
        assert connected["type"] == "connected"
        ws.send_json({"type": "create_session"})
        created = ws.receive_json()
        assert created["type"] == "session_created"
        ws.send_json({"type": "message", "text": "hello while running"})

    # While running, app should queue/inject only. User message broadcast will
    # come later from ChatRoom(UserMessageReceived), not immediately here.
    assert FakeRunner.last_instance is not None
    assert not any(
        call.get("type") == "user_message" and call.get("text") == "hello while running"
        for call in FakeRunner.last_instance.broadcast_calls
    )
