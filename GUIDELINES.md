# Multi-Agent Collaboration Guidelines

## 1. Rule #1: Trust & Explicit Approval
**NEVER modify, create, or delete files without explicit User approval.**
- Even with full filesystem access, access ≠ permission.
- **Protocol:** Propose changes → Wait for User "OK" → Execute.
- This applies to code, configuration, and infrastructure (e.g., `_get_cwd` behavior).

## 2. Workspace Architecture & Session Isolation
- **Mandatory Isolation:** Each agent runs in its own isolated temp directory (`/tmp/multiagents-<agent>-<uuid>/`).
- **Why:** This prevents CLI session data from colliding, which causes context bloat and agent crashes.
- **Don't Assume Bugs:** If a design choice looks like a bug (like "isolation"), ASK the User first. We "chapamos" once by assuming isolation was an error.

## 3. Absolute Path Protocol
Since our `cwd` is isolated, we **must** use absolute paths for all project file operations.
- **Project Root:** `<project-root>` (the absolute path to the repository root)
- **Usage:** Always use the full path in tools: `read_file("<project-root>/src/main.py")`.

## 4. Coordination & Communication
- **[PASS] Aggressively:** If you have nothing to add, respond with exactly `[PASS]`. Silence is better than noise.
- **+1 AgentName:** Use this to show agreement and build on an idea without repeating it.
- **[HANDOFF:Agent]**: Use for clear task delegation, including specific file paths if applicable.
- **[STATUS:msg]**: Keep your intent visible (EXPLORE, DECISION, BLOCKED, DONE).

## 5. Write Collision Prevention
- **Claim Before Write:** Before touching any file, announce it in a `[STATUS]` message (e.g., `[STATUS: Editing src/api.py]`).
- **Single-Writer Rule:** Only one agent should lead the implementation of a specific task. Others act as reviewers.
- **Re-read Before Edit:** Always perform a fresh `read_file` before applying a `replace` to ensure you're working on the latest version of the code.

## 6. Task Complexity Norms
- **Simple Tasks:** Default to a single agent. Others should `[PASS]`.
- **Complex Tasks:** Use the full crew for architectural discussion, debugging, and peer review.