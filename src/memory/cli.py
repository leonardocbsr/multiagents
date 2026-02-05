from __future__ import annotations

from pathlib import Path

from .store import MemoryStore


def init_project(directory: Path | None = None) -> Path:
    target = Path(directory) if directory else Path.cwd()
    (target / ".multiagents").mkdir(parents=True, exist_ok=True)
    MemoryStore(target)  # creates/validates schema
    return target
