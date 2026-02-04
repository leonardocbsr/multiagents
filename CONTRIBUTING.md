# Contributing to Multiagents

## Development Setup

```bash
./setup.sh
./start.sh
```

Or manually:

```bash
pip install -e ".[dev]"
cd web && pnpm install
```

## Development Workflow

- Create a feature branch from `main`
- Make focused changes with clear commit messages
- Add or update tests for behavior changes
- Run checks locally before opening a PR

## Local Checks

```bash
pytest -v
cd web && pnpm build
```

## Pull Request Guidelines

- Explain what changed and why
- Link related issues when applicable
- Include screenshots or recordings for UI changes
- Call out breaking changes explicitly

## Code Style

- Python: keep code typed where practical and maintain clear function boundaries
- TypeScript/React: keep components focused and avoid unnecessary state duplication
- Prefer small, reviewable PRs over large mixed changes
