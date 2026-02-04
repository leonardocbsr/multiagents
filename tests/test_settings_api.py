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


def test_put_settings_bulk_update(client):
    resp = client.put("/api/settings", json={"timeouts.idle": 900})
    assert resp.status_code == 200
    resp = client.get("/api/settings")
    assert resp.json()["timeouts.idle"] == 900


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
