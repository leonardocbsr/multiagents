# Repository Guidelines

## Project Structure & Module Organization
- `src/`: Python backend (FastAPI server, chat orchestration, agents, cards, memory).
- `tests/`: `pytest` suite for backend behavior and protocol flows.
- `web/`: React + TypeScript frontend (Vite + Tailwind).
- `docs/`: quickstart and UI reference images.
- `scripts/`: utility scripts (for example `scripts/multiagents-cards`).
- Root scripts: `setup.sh` installs dependencies; `start.sh` runs backend + frontend together.

## Build, Test, and Development Commands
- `./setup.sh`: create/activate `.venv`, install Python deps, install frontend deps.
- `./start.sh`: run full stack (`api` on `8421`, `web` on `5174`).
- `python -m src.main --port 8421 --agents claude,codex,kimi`: run backend only.
- `pytest -v`: run backend tests.
- `cd web && pnpm dev`: run frontend dev server.
- `cd web && pnpm build`: type-check and build frontend for production.

## Coding Style & Naming Conventions
- Python: 4-space indentation, type hints where practical, small focused functions.
- TypeScript/React: 2-space indentation, functional components, avoid duplicated state.
- Naming: Python modules/files use `snake_case`; React components use `PascalCase` (for example `ChatRoom.tsx`); tests use `test_*.py`.
- Keep changes narrow and readable; prefer clear boundaries between orchestration (`src/chat/`, `src/server/`) and integrations (`src/agents/`).

## Testing Guidelines
- Framework: `pytest` with `pytest-asyncio` (`asyncio_mode = auto`).
- Add or update tests for every behavior change, especially event flow, routing, and settings APIs.
- Use targeted runs while developing (example: `pytest tests/test_room.py -k pass`).
- No fixed coverage percentage is enforced; review quality is based on meaningful scenario coverage.

## Commit & Pull Request Guidelines
- Follow Conventional Commit style seen in history (example: `feat: add round pause event`).
- Keep commits focused; avoid mixing refactors and feature changes.
- PRs should include: what changed, why, linked issues (if any), and UI screenshots/recordings for frontend updates.
- Call out breaking changes explicitly and list local checks run (`pytest -v`, `cd web && pnpm build`).

## Security & Configuration Tips
- Default binding is loopback; only use `--host 0.0.0.0` intentionally.
- Agent CLIs (`claude`, `codex`, `kimi`) are optional but required to run those agents.
- Do not commit local secrets or machine-specific configuration.
