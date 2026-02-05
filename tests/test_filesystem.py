from starlette.testclient import TestClient
from src.server.app import create_app
from src.server.sessions import SessionStore


def _client(tmp_path):
    store = SessionStore(tmp_path / "test.db")
    app = create_app(session_store=store)
    return TestClient(app)


def test_list_home(tmp_path):
    c = _client(tmp_path)
    r = c.get("/api/filesystem/list")
    assert r.status_code == 200
    data = r.json()
    assert "path" in data
    assert "directories" in data
    assert isinstance(data["directories"], list)


def test_list_specific_dir(tmp_path):
    (tmp_path / "aaa").mkdir()
    (tmp_path / "bbb").mkdir()
    (tmp_path / "file.txt").write_text("x")
    c = _client(tmp_path)
    r = c.get("/api/filesystem/list", params={"path": str(tmp_path)})
    assert r.status_code == 200
    data = r.json()
    assert "aaa" in data["directories"]
    assert "bbb" in data["directories"]
    assert "file.txt" not in data["directories"]


def test_list_hidden_excluded(tmp_path):
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible").mkdir()
    c = _client(tmp_path)
    r = c.get("/api/filesystem/list", params={"path": str(tmp_path)})
    data = r.json()
    assert ".hidden" not in data["directories"]
    assert "visible" in data["directories"]


def test_list_parent(tmp_path):
    child = tmp_path / "sub"
    child.mkdir()
    c = _client(tmp_path)
    r = c.get("/api/filesystem/list", params={"path": str(child)})
    data = r.json()
    assert data["parent"] == str(tmp_path)


def test_list_invalid_path(tmp_path):
    c = _client(tmp_path)
    r = c.get("/api/filesystem/list", params={"path": str(tmp_path / "nope")})
    assert r.status_code == 400


def test_list_sorted(tmp_path):
    for name in ["Zebra", "alpha", "Beta"]:
        (tmp_path / name).mkdir()
    c = _client(tmp_path)
    r = c.get("/api/filesystem/list", params={"path": str(tmp_path)})
    dirs = r.json()["directories"]
    assert dirs == ["alpha", "Beta", "Zebra"]
