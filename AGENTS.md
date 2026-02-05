# Repository Guidelines

## Project Structure & Module Organization
- `src/`: Python backend (FastAPI app, orchestration, agent adapters, cards, memory).
- `tests/`: `pytest` suites covering routing, protocol flows, settings, memory, and agent behavior.
- `web/`: React + TypeScript frontend (Vite + Tailwind CSS v4).
- `docs/`: quickstart docs and UI references.
- `scripts/`: utility entrypoints such as `scripts/multiagents-cards`.

Keep boundaries clear: orchestration belongs in `src/chat/` and `src/server/`; integration-specific logic should stay in dedicated modules.

## Build, Test, and Development Commands
- `./setup.sh`: creates/activates `.venv`, installs Python and frontend dependencies.
- `./start.sh --backend python`: runs Python backend (`8421`) and frontend (`5174`) together.
- `python3 -m src.main --port 8421 --agents claude,codex,kimi`: backend only.
- `pytest -v`: run backend tests.
- `pytest tests/test_room.py -k pass`: targeted test run while iterating.
- `cd web && pnpm dev`: frontend dev server.
- `cd web && pnpm build`: UI token lint + TypeScript build + Vite production bundle.

## Coding Style & Naming Conventions
- Python: 4-space indentation, type hints where practical, small focused functions.
- TypeScript/React: 2-space indentation, functional components, avoid duplicated state.
- Naming: Python modules/files in `snake_case`; React components in `PascalCase`; tests as `test_*.py`.
- Prefer explicit interfaces and narrow changes over broad refactors.

## Testing Guidelines
- Framework: `pytest` with `pytest-asyncio` (`asyncio_mode = auto`) for Python.
- Add or update tests for every behavior change, especially event flow, routing, and settings APIs.
- During development, run focused tests first; before opening PRs, run full `pytest -v`.
- For frontend changes, ensure `cd web && pnpm build` passes.

## Commit & Pull Request Guidelines
- Use Conventional Commits (for example: `feat: add round pause event`, `fix: handle websocket reconnect race`).
- Keep commits focused; do not mix unrelated refactors with feature work.
- PRs should include what changed, why, linked issues, and screenshots/recordings for UI changes.
- List local verification steps run (for example: `pytest -v`, `cd web && pnpm build`).

## Security & Configuration Tips
- Default binding is loopback; only use `--host 0.0.0.0` intentionally.
- Agent CLIs (`claude`, `codex`, `kimi`) are optional but required for those providers.
- Never commit secrets or machine-specific credentials/configuration.
