from __future__ import annotations

from pathlib import Path

_MARKER = ".multiagents"


def find_project_root(start: Path | None = None) -> Path | None:
    current = (Path(start) if start else Path.cwd()).resolve()
    while True:
        if (current / _MARKER).is_dir():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
