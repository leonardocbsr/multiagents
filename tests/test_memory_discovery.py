from pathlib import Path

from src.memory.discovery import find_project_root


def test_find_from_project_dir(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    assert find_project_root(tmp_path) == tmp_path


def test_find_from_subdirectory(tmp_path):
    (tmp_path / ".multiagents").mkdir()
    child = tmp_path / "src" / "deep"
    child.mkdir(parents=True)
    assert find_project_root(child) == tmp_path


def test_returns_none_when_missing(tmp_path):
    child = tmp_path / "no_project" / "sub"
    child.mkdir(parents=True)
    assert find_project_root(child) is None


def test_defaults_to_cwd(tmp_path, monkeypatch):
    (tmp_path / ".multiagents").mkdir()
    monkeypatch.chdir(tmp_path)
    assert find_project_root() == tmp_path


def test_file_not_dir_ignored(tmp_path):
    (tmp_path / ".multiagents").write_text("not a dir")
    assert find_project_root(tmp_path) is None
