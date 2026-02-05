from __future__ import annotations

import re

_ROLE_DISPLAY = {
    "user": "User",
    "claude": "Claude",
    "codex": "Codex",
    "kimi": "Kimi",
    "system": "System",
}

# Regex to extract content from <Share>...</Share> tags
_SHARE_TAG_RE = re.compile(r"<Share>(.*?)</Share>", re.DOTALL | re.IGNORECASE)
_THINKING_BLOCK_RE = re.compile(
    r"<(?:thinking|antThinking)>[\s\S]*?</(?:thinking|antThinking)>",
    re.IGNORECASE,
)
_PRIVATE_PLACEHOLDER = "(private response withheld)"
PLACEHOLDER = _PRIVATE_PLACEHOLDER

# Coordination pattern regexes — mirrored in web/src/types.ts.
# Canonical test cases: tests/fixtures/coordination_patterns.json
_MENTION_RE = re.compile(r"(?<!/)@(\w+)")
_AGREEMENT_RE = re.compile(r"\+1\s+(\w+)", re.IGNORECASE)
_HANDOFF_RE = re.compile(r"\[HANDOFF:(\w+)\]", re.IGNORECASE)
_STATUS_RE = re.compile(
    r"\[(?:(?:STATUS:\s*)?(EXPLORE|DECISION|BLOCKED|DONE|TODO|QUESTION))\]"
    r"|\[STATUS:\s*([^\]\n]+)\]",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _split_history(
    history: list[dict], current_round: int,
) -> tuple[list[dict], list[dict]]:
    """Split history into (older_history, current_context).

    Current context = messages from the previous agent round (current_round - 1)
    plus any user messages that immediately precede them (the trigger).
    For round 1 (prev_round=0) everything is current context.
    """
    prev_round = current_round - 1

    if prev_round <= 0:
        return [], list(history)

    # Find the first message from the previous agent round
    context_start = len(history)
    for i, msg in enumerate(history):
        if msg.get("round") == prev_round:
            context_start = i
            break

    # Walk backward to include user messages that triggered this round
    # (user messages have no "round" field)
    while context_start > 0 and "round" not in history[context_start - 1]:
        context_start -= 1

    return history[:context_start], history[context_start:]


def _format_messages(msgs: list[dict]) -> list[str]:
    """Format history messages into display lines.

    Content in history is already processed (shareable extracted by ChatRoom),
    so no further extraction is needed here.
    """
    lines: list[str] = []
    for msg in msgs:
        role = msg["role"]
        role_label = _ROLE_DISPLAY.get(role, role.capitalize())
        lines.append(f"[{role_label}]: {msg['content']}")
    return lines


def _build_mention_notice(current_msgs: list[dict], agent_name: str) -> str:
    """Build a notice if this agent was @mentioned or handed off to in current round."""
    mentioners: list[str] = []
    handoff_from: list[tuple[str, str]] = []

    for msg in current_msgs:
        if msg["role"] == agent_name:
            continue
        content = msg["content"]

        for m in _MENTION_RE.findall(content):
            if m.lower() == agent_name.lower():
                role_label = _ROLE_DISPLAY.get(msg["role"], msg["role"].capitalize())
                mentioners.append(role_label)

        for match in _HANDOFF_RE.finditer(content):
            if match.group(1).lower() == agent_name.lower():
                role_label = _ROLE_DISPLAY.get(msg["role"], msg["role"].capitalize())
                after = content[match.end():].strip()
                context = after.split(".")[0][:100].strip()
                handoff_from.append((role_label, context))

    if not mentioners and not handoff_from:
        return ""

    parts: list[str] = []
    if mentioners:
        unique = list(dict.fromkeys(mentioners))
        parts.append(f"You were @mentioned by {', '.join(unique)}.")
    for sender, context in handoff_from:
        parts.append(f"{sender} handed off to you: {context}.")

    return " ".join(parts) + "\n\n"


def format_cards_section(cards: list[dict], agent_name: str) -> str:
    """Format a task board section for inclusion in the agent prompt."""
    if not cards:
        return ""

    lines = [
        "## Task Board",
        "Manage cards via `multiagents-cards` CLI. "
        "Session and URL are pre-configured in your environment.",
    ]

    for c in cards:
        my_roles: list[str] = []
        for role in ("coordinator", "planner", "implementer", "reviewer"):
            assignee = c.get(role, "")
            if assignee and assignee.lower() == agent_name.lower():
                my_roles.append(role)
        entry = f"- [{c['id']}] \"{c['title']}\" ({c['status']})"
        if my_roles:
            entry += f" — your role: {', '.join(my_roles)}"
        lines.append(entry)

    return "\n".join(lines)


def _build_participants_line(
    participants: list[dict], exclude_name: str,
) -> str:
    """Build an 'Other participants' line from a list of persona dicts.

    Each dict has ``name`` and ``type`` keys.  The type is shown in
    parentheses only when the name differs from the type (case-insensitive).
    The ``exclude_name`` persona is omitted (that's the agent itself).
    """
    parts: list[str] = []
    exclude_lower = exclude_name.lower()
    for p in participants:
        if p["name"].lower() == exclude_lower:
            continue
        name = p["name"]
        ptype = p.get("type", "")
        if ptype and name.lower() != ptype.lower():
            parts.append(f"{name} ({ptype.capitalize()})")
        else:
            parts.append(name)
    return ", ".join(parts)


def format_session_context(
    agent_name: str,
    working_dir: str = "",
    participants: list[dict] | None = None,
    role: str = "",
) -> str:
    """Session-specific context: participants, role, working dir.

    Static directives (Share tags, coordination tools, async message model, [PASS])
    live in the CLI system prompt via ``build_agent_system_prompt()``.
    This function only provides the dynamic per-session information.
    """
    if participants is not None:
        label = agent_name
        others = _build_participants_line(participants, agent_name)
    else:
        label = _ROLE_DISPLAY.get(agent_name, agent_name.capitalize())
        others = ", ".join(
            v for k, v in _ROLE_DISPLAY.items()
            if k != agent_name and k != "system"
        )

    role_line = f"Your role: {role}\n" if role else ""

    return (
        f"You are {label} in a group chat with a human user and other AI agents.\n"
        + role_line
        + f"Other participants: {others}."
    )



def format_round_prompt(
    history: list[dict],
    agent_name: str,
    current_round: int = 1,
    extra_context: dict[str, str] | None = None,
) -> str:
    """Per-round delta prompt for agents with active CLI sessions."""
    _, current_msgs = _split_history(history, current_round)

    sections: list[str] = []

    if extra_context:
        sections.extend(v for v in extra_context.values() if v)

    if current_msgs:
        current_lines = _format_messages(current_msgs)
        sections.append("## Current Round\n" + "\n".join(current_lines))

    mention_notice = _build_mention_notice(current_msgs, agent_name)
    your_turn = (
        f"## Your Turn (Round {current_round})\n"
        + mention_notice
        + "Respond directly — no preamble about what you're going to do, "
        "just do it. Wrap your response in <Share> tags. "
        "If you have nothing meaningful to add, respond with exactly [PASS]."
    )
    sections.append(your_turn)

    return "\n\n".join(sections)


def format_prompt(
    history: list[dict],
    agent_name: str,
    current_round: int = 1,
    has_session: bool = False,
    extra_context: dict[str, str] | None = None,
    working_dir: str = "",
    participants: list[dict] | None = None,
    role: str = "",
) -> str:
    """Full prompt for agents without an active CLI session.

    Static directives (Share tags, coordination tools, round model, [PASS])
    are delivered via the CLI system prompt (``build_agent_system_prompt``).
    This function provides session context + conversation data.
    """
    header = format_session_context(agent_name, working_dir, participants, role)

    history_msgs, current_msgs = _split_history(history, current_round)

    sections = [header]

    # Extra context sections (e.g. task board)
    if extra_context:
        sections.extend(v for v in extra_context.values() if v)

    if history_msgs and not has_session:
        history_lines = _format_messages(history_msgs)
        sections.append("## Conversation History\n" + "\n".join(history_lines))

    if current_msgs:
        current_lines = _format_messages(current_msgs)
        sections.append("## Current Round\n" + "\n".join(current_lines))

    mention_notice = _build_mention_notice(current_msgs, agent_name)
    your_turn = (
        f"## Your Turn (Round {current_round})\n"
        + mention_notice
        + "Respond directly — no preamble about what you're going to do, "
        "just do it. Wrap your response in <Share> tags. "
        "If you have nothing meaningful to add, respond with exactly [PASS]."
    )
    sections.append(your_turn)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Detection / extraction helpers
# ---------------------------------------------------------------------------


def detect_pass(text: str) -> bool:
    return text.strip() == "[PASS]"


def extract_shareable(text: str) -> str:
    """Extract content from <Share> tags. Returns placeholder if no tags found.

    Multiple <Share> blocks are concatenated with newlines.
    Thinking blocks are stripped first so a <Share> accidentally opened
    inside a thinking block doesn't swallow the whole response.
    """
    if text.strip() == "[PASS]":
        return "[PASS]"
    cleaned = _THINKING_BLOCK_RE.sub("", text)
    matches = _SHARE_TAG_RE.findall(cleaned)
    if not matches:
        return _PRIVATE_PLACEHOLDER
    shareable = "\n\n".join(m.strip() for m in matches if m.strip())
    return shareable if shareable else _PRIVATE_PLACEHOLDER


def extract_mentions(text: str) -> list[str]:
    """Extract @AgentName mentions from text."""
    return _MENTION_RE.findall(text)


def extract_agreements(text: str) -> list[str]:
    """Extract +1 AgentName agreements from text."""
    return _AGREEMENT_RE.findall(text)


def extract_handoffs(text: str) -> list[tuple[str, str]]:
    """Extract [HANDOFF:Agent] patterns and return [(agent, context), ...].

    Context is the text following the handoff tag in the same block.
    """
    handoffs = []
    for match in _HANDOFF_RE.finditer(text):
        agent = match.group(1)
        after = text[match.end():].strip()
        context = after.split('.')[0][:100].strip()
        handoffs.append((agent, context))
    return handoffs


def extract_statuses(text: str) -> list[str]:
    """Extract [STATUS] indicators from text."""
    statuses: list[str] = []
    for match in _STATUS_RE.finditer(text):
        status = match.group(1) or match.group(2)
        if not status:
            continue
        normalized = " ".join(status.strip().split())
        if normalized:
            statuses.append(normalized)
    return statuses
