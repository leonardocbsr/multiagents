from __future__ import annotations

import re

_DISCORD_MAX_LEN = 2000

_THINKING_RE = re.compile(
    r"<(?:thinking|antThinking)>[\s\S]*?</(?:thinking|antThinking)>",
    re.IGNORECASE,
)
_SHARE_RE = re.compile(r"<Share>(.*?)</Share>", re.DOTALL | re.IGNORECASE)
_TOOL_RE = re.compile(r"<tool>(.*?)</tool>", re.DOTALL | re.IGNORECASE)


def _extract_share(text: str) -> str | None:
    """Extract Share content, stripping thinking blocks first."""
    if text.strip() == "[PASS]":
        return None
    cleaned = _THINKING_RE.sub("", text)
    matches = _SHARE_RE.findall(cleaned)
    if not matches:
        return None
    content = "\n\n".join(m.strip() for m in matches if m.strip())
    return content if content else None


def _extract_tools(text: str) -> list[str]:
    """Extract tool badge labels from text."""
    matches = _TOOL_RE.findall(text)
    tools = []
    for m in matches:
        label = m.strip().split()[0] if m.strip() else ""
        if label:
            tools.append(label)
    return tools


def _split_message(text: str, max_len: int = _DISCORD_MAX_LEN) -> list[str]:
    """Split text into chunks that fit Discord's message limit."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at a paragraph boundary
        cut = text.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = text.rfind("\n", 0, max_len)
        if cut == -1:
            cut = text.rfind(" ", 0, max_len)
        if cut == -1:
            cut = max_len
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()

    return chunks


def format_event(event: dict) -> list[str]:
    """Convert a server WebSocket event to Discord message(s).

    Returns a list of strings to post. Empty list means nothing to post.
    """
    event_type = event.get("type", "")

    if event_type == "agent_completed":
        return _format_agent_completed(event)
    elif event_type == "round_started":
        return _format_round_started(event)
    elif event_type == "round_ended":
        return _format_round_ended(event)
    elif event_type == "agent_interrupted":
        return _format_agent_interrupted(event)
    elif event_type == "discussion_ended":
        return _format_discussion_ended(event)
    elif event_type == "permission_request":
        return _format_permission_request(event)
    elif event_type == "error":
        return _format_error(event)
    else:
        return []


def _format_agent_completed(event: dict) -> list[str]:
    agent = event.get("agent", "unknown")
    text = event.get("text", "")
    passed = event.get("passed", False)
    success = event.get("success", True)
    agent_display = agent.capitalize()

    if passed:
        return []

    if not success:
        return [f"⚠ **{agent_display}** encountered an error."]

    tools = _extract_tools(text)
    share = _extract_share(text)

    if share is None:
        return [f"**{agent_display}:** *(private response withheld)*"]

    parts: list[str] = []
    if tools:
        badge_line = " ".join(f"`🔧 {t}`" for t in tools)
        parts.append(badge_line)
    parts.append(share)

    body = f"**{agent_display}:** " + "\n".join(parts)
    chunks = _split_message(body)

    # Add agent prefix to continuation chunks for readability
    for i in range(1, len(chunks)):
        prefix = f"**{agent_display}** *(cont'd):* "
        if len(prefix) + len(chunks[i]) <= _DISCORD_MAX_LEN:
            chunks[i] = prefix + chunks[i]

    return chunks


def _format_round_started(event: dict) -> list[str]:
    round_num = event.get("round", 1)
    if round_num <= 1:
        return []
    return [f"───── Round {round_num} ─────"]


def _format_round_ended(event: dict) -> list[str]:
    if event.get("all_passed"):
        return ["All agents passed. Send a message to continue."]
    return []


def _format_agent_interrupted(event: dict) -> list[str]:
    agent = event.get("agent", "unknown").capitalize()
    return [f"⚠ **{agent}** was interrupted."]


def _format_discussion_ended(event: dict) -> list[str]:
    reason = event.get("reason", "unknown")
    if reason == "all_passed":
        return ["Discussion complete — all agents have nothing to add."]
    elif reason == "cancelled":
        return ["Discussion cancelled."]
    elif reason == "error":
        return ["Discussion ended due to an error."]
    return [f"Discussion ended ({reason})."]


def _format_permission_request(event: dict) -> list[str]:
    agent = str(event.get("agent", "unknown")).capitalize()
    tool_name = str(event.get("tool_name", "unknown"))
    description = str(event.get("description", "")).strip()

    message = f"🔐 **Permission requested** by **{agent}** for `{tool_name}`."
    if description:
        message += f"\n{description}"
    return [message]


def _format_error(event: dict) -> list[str]:
    message = event.get("message", "Unknown error")
    return [f"Server error: {message}"]
