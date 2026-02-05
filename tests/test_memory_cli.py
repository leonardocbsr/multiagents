from pathlib import Path

from src.memory.cli import init_project


def test_init_creates_directory(tmp_path):
    init_project(tmp_path)
    assert (tmp_path / ".multiagents").is_dir()
    assert (tmp_path / ".multiagents" / "memory.db").exists()


def test_init_idempotent(tmp_path):
    init_project(tmp_path)
    from src.memory.store import MemoryStore

    store = MemoryStore(tmp_path)
    ep_id = store.save_episode(session_id="s1", summary="data")
    init_project(tmp_path)  # second call
    store2 = MemoryStore(tmp_path)
    assert store2.get_episode(ep_id) is not None


def test_public_imports():
    from src.memory import MemoryStore, MemoryManager, SessionRecorder, find_project_root

    assert all(
        x is not None
        for x in [MemoryStore, MemoryManager, SessionRecorder, find_project_root]
    )


def test_main_parser_init_subcommand():
    from src.main import build_parser

    parser = build_parser()
    args = parser.parse_args(["init"])
    assert args.command == "init"


def test_main_parser_backward_compat():
    """No subcommand still works (defaults to serve)."""
    from src.main import build_parser

    parser = build_parser()
    args = parser.parse_args(["--port", "9000"])
    assert args.command is None  # no subcommand = serve
    assert args.port == 9000
