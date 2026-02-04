from src.chat.router import (
    format_prompt,
    detect_pass,
    extract_shareable,
    extract_mentions,
    extract_agreements,
    extract_handoffs,
    extract_statuses,
)
from src.agents.prompts import build_agent_system_prompt


# === Prompt structure tests ===


def test_format_prompt_round1_all_in_current_round():
    """Round 1: everything goes into Current Round (no history section)."""
    history = [
        {"role": "user", "content": "Build an API"},
    ]
    result = format_prompt(history, "claude", current_round=1)
    assert "## Current Round" in result
    assert "[User]: Build an API" in result
    assert "## Conversation History" not in result
    assert "## Your Turn (Round 1)" in result


def test_format_prompt_round2_splits_history():
    """Round 2: round-1 responses are in Current Round, user message in history."""
    history = [
        {"role": "user", "content": "Build an API"},
        {"role": "claude", "content": "I suggest FastAPI", "round": 1},
        {"role": "codex", "content": "Express is better", "round": 1},
        {"role": "kimi", "content": "[PASS]", "round": 1},
    ]
    result = format_prompt(history, "kimi", current_round=2)
    assert "## Conversation History" not in result  # user msg pulled into current context
    assert "## Current Round" in result
    assert "[User]: Build an API" in result
    assert "[Claude]: I suggest FastAPI" in result
    assert "[Codex]: Express is better" in result
    assert "## Your Turn (Round 2)" in result


def test_format_prompt_round3_has_history():
    """Round 3: rounds before prev_round go to history."""
    history = [
        {"role": "user", "content": "Build an API"},
        {"role": "claude", "content": "I suggest FastAPI", "round": 1},
        {"role": "codex", "content": "+1 Claude", "round": 1},
        {"role": "kimi", "content": "[PASS]", "round": 1},
        {"role": "claude", "content": "@Kimi thoughts?", "round": 2},
        {"role": "codex", "content": "[STATUS:DONE]", "round": 2},
        {"role": "kimi", "content": "I like FastAPI too", "round": 2},
    ]
    result = format_prompt(history, "kimi", current_round=3)

    # History should contain user msg + round 1
    assert "## Conversation History" in result
    hist_section = result.split("## Current Round")[0]
    assert "[User]: Build an API" in hist_section
    assert "[Claude]: I suggest FastAPI" in hist_section

    # Current Round should contain round 2
    current_section = result.split("## Current Round")[1].split("## Your Turn")[0]
    assert "[Claude]: @Kimi thoughts?" in current_section
    assert "[Codex]: [STATUS:DONE]" in current_section

    assert "## Your Turn (Round 3)" in result


def test_format_prompt_user_injection_in_current_round():
    """User messages between rounds are included in current context."""
    history = [
        {"role": "user", "content": "Build an API"},
        {"role": "claude", "content": "FastAPI plan", "round": 1},
        {"role": "codex", "content": "+1", "round": 1},
        {"role": "user", "content": "What about TypeScript?"},
        {"role": "claude", "content": "Could use Express", "round": 2},
        {"role": "codex", "content": "I prefer Hono", "round": 2},
    ]
    result = format_prompt(history, "kimi", current_round=3)

    # History: user msg + round 1
    hist_section = result.split("## Current Round")[0]
    assert "[User]: Build an API" in hist_section
    assert "[Claude]: FastAPI plan" in hist_section

    # Current Round: injected user msg + round 2
    current_section = result.split("## Current Round")[1].split("## Your Turn")[0]
    assert "[User]: What about TypeScript?" in current_section
    assert "[Claude]: Could use Express" in current_section
    assert "[Codex]: I prefer Hono" in current_section


def test_format_prompt_includes_agent_identity():
    history = [{"role": "user", "content": "Hello"}]
    result = format_prompt(history, "claude", current_round=1)
    assert "You are Claude" in result


def test_format_prompt_includes_share_reminder():
    """The round prompt reminds agents to use Share tags."""
    history = [{"role": "user", "content": "Hello"}]
    result = format_prompt(history, "claude", current_round=1)
    assert "<Share>" in result


def test_format_prompt_includes_pass_instruction():
    history = [{"role": "user", "content": "Hello"}]
    result = format_prompt(history, "claude", current_round=1)
    assert "[PASS]" in result


def test_system_prompt_includes_full_directives():
    """Static directives live in the CLI system prompt (build_agent_system_prompt)."""
    result = build_agent_system_prompt(agent_name="TestAgent")
    assert "<Share>" in result
    assert "</Share>" in result
    assert "[PASS]" in result
    assert "@AgentName" in result
    assert "[HANDOFF:Agent]" in result
    assert "ROUND MODEL" in result
    assert "You are TestAgent," in result


# === Pass detection ===


def test_detect_pass_exact():
    assert detect_pass("[PASS]") is True
    assert detect_pass("  [PASS]  ") is True
    assert detect_pass("[PASS]\n") is True


def test_detect_pass_negative():
    assert detect_pass("I think we should use FastAPI") is False
    assert detect_pass("I'll pass on this one") is False


# === Shareable extraction ===


def test_extract_shareable_single_tag():
    text = "Let me think... <Share>The answer is 42</Share>"
    assert extract_shareable(text) == "The answer is 42"


def test_extract_shareable_multiple_tags():
    text = "<Share>Point 1</Share> thinking... <Share>Point 2</Share>"
    assert extract_shareable(text) == "Point 1\n\nPoint 2"


def test_extract_shareable_no_tags():
    text = "Just a regular response"
    assert extract_shareable(text) == "(private response withheld)"


def test_extract_shareable_pass_passthrough():
    assert extract_shareable("[PASS]") == "[PASS]"


def test_extract_shareable_case_insensitive():
    assert extract_shareable("<share>lowercase</share>") == "lowercase"
    assert extract_shareable("<SHARE>uppercase</SHARE>") == "uppercase"
    assert extract_shareable("<Share>Mixed</Share>") == "Mixed"


def test_extract_shareable_multiline():
    text = """<Share>
Line 1
Line 2
</Share>"""
    assert extract_shareable(text) == "Line 1\nLine 2"


def test_extract_shareable_empty():
    text = "<Share></Share> still returns empty"
    assert extract_shareable(text) == "(private response withheld)"


def test_extract_shareable_whitespace_only():
    text = "<Share>   </Share> nothing here"
    assert extract_shareable(text) == "(private response withheld)"


def test_extract_shareable_share_inside_thinking():
    """Share tag opened inside a thinking block should not swallow the response."""
    text = (
        "<thinking>Let me coordinate. <Share>tags for coordination.</thinking>"
        "Understood — full fixes.\n"
        "<Share> @Claude — please create cards.</Share>"
    )
    assert extract_shareable(text) == "@Claude — please create cards."


def test_extract_shareable_thinking_wraps_share():
    """Share tag fully inside thinking should be stripped; outer Share found."""
    text = (
        "<thinking>I think <Share>hidden</Share> about it.</thinking>"
        "<Share>Visible content</Share>"
    )
    assert extract_shareable(text) == "Visible content"


def test_extract_shareable_no_thinking_unchanged():
    """Normal Share extraction works when no thinking tags present."""
    text = "Private stuff. <Share>Shared content</Share>"
    assert extract_shareable(text) == "Shared content"


# === Coordination pattern tests ===


def test_extract_mentions():
    assert extract_mentions("@Claude what do you think?") == ["Claude"]
    assert extract_mentions("@kimi and @Codex please review") == ["kimi", "Codex"]
    assert extract_mentions("No mentions here") == []


def test_extract_agreements():
    assert extract_agreements("+1 Claude") == ["Claude"]
    assert extract_agreements("+1 codex and +1 Kimi") == ["codex", "Kimi"]
    assert extract_agreements("I agree") == []


def test_extract_handoffs():
    result = extract_handoffs("[HANDOFF:claude] Fix the bug")
    assert result == [("claude", "Fix the bug")]

    result = extract_handoffs("[HANDOFF:codex] Task 1. [HANDOFF:kimi] Task 2")
    assert len(result) == 2
    assert result[0][0] == "codex"
    assert result[1][0] == "kimi"


def test_extract_handoffs_context_truncation():
    long_text = "[HANDOFF:claude] " + "x" * 200
    result = extract_handoffs(long_text)
    assert len(result[0][1]) <= 100


def test_extract_statuses():
    assert extract_statuses("[EXPLORE] Checking options") == ["EXPLORE"]
    assert extract_statuses("[decision] We go with A") == ["decision"]
    assert extract_statuses("[BLOCKED] Need input") == ["BLOCKED"]
    assert extract_statuses("[DONE] Task complete") == ["DONE"]
    assert extract_statuses("[TODO] Next step") == ["TODO"]
    assert extract_statuses("[QUESTION] What about X?") == ["QUESTION"]
    assert extract_statuses("[STATUS: READY] Standing by") == ["READY"]
    assert extract_statuses("[STATUS: in progress] Still working") == ["in progress"]


def test_extract_multiple_statuses():
    text = "[EXPLORE] Checked options. [DECISION] Going with Plan A"
    assert extract_statuses(text) == ["EXPLORE", "DECISION"]


# === Mention notice tests ===


def test_format_prompt_has_session_skips_history():
    """When has_session=True, older history is omitted (agent already has it)."""
    history = [
        {"role": "user", "content": "Build an API"},
        {"role": "claude", "content": "I suggest FastAPI", "round": 1},
        {"role": "codex", "content": "+1 Claude", "round": 1},
        {"role": "kimi", "content": "[PASS]", "round": 1},
        {"role": "claude", "content": "@Kimi thoughts?", "round": 2},
        {"role": "codex", "content": "[STATUS:DONE]", "round": 2},
        {"role": "kimi", "content": "I like FastAPI too", "round": 2},
    ]
    result = format_prompt(history, "kimi", current_round=3, has_session=True)

    # History section should be absent
    assert "## Conversation History" not in result

    # Current Round (round 2 responses) should still be present
    assert "## Current Round" in result
    assert "[Claude]: @Kimi thoughts?" in result
    assert "[Codex]: [STATUS:DONE]" in result
    assert "## Your Turn (Round 3)" in result


def test_format_prompt_has_session_false_includes_history():
    """When has_session=False (default), older history is included."""
    history = [
        {"role": "user", "content": "Build an API"},
        {"role": "claude", "content": "I suggest FastAPI", "round": 1},
        {"role": "codex", "content": "+1 Claude", "round": 1},
        {"role": "claude", "content": "Let's proceed", "round": 2},
        {"role": "codex", "content": "Agreed", "round": 2},
    ]
    result = format_prompt(history, "kimi", current_round=3, has_session=False)
    assert "## Conversation History" in result
    assert "[User]: Build an API" in result


def test_format_prompt_mention_notice():
    """Agent should get an informational notice when @mentioned by another agent."""
    history = [
        {"role": "user", "content": "Build an API"},
        {"role": "claude", "content": "@Codex what framework do you suggest?", "round": 1},
    ]
    result = format_prompt(history, "codex", current_round=2)
    assert "You were @mentioned by Claude" in result
    # Notice should be informational, not force a response
    assert "Do NOT respond with [PASS]" not in result


def test_format_prompt_mention_notice_case_insensitive():
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "kimi", "content": "@claude thoughts?", "round": 1},
    ]
    result = format_prompt(history, "claude", current_round=2)
    assert "You were @mentioned by Kimi" in result


def test_format_prompt_no_mention_notice_when_not_mentioned():
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "claude", "content": "@Kimi what do you think?", "round": 1},
    ]
    result = format_prompt(history, "codex", current_round=2)
    assert "You were @mentioned" not in result


def test_format_prompt_handoff_notice():
    history = [
        {"role": "user", "content": "Build an API"},
        {"role": "claude", "content": "[HANDOFF:codex] Implement the endpoints", "round": 1},
    ]
    result = format_prompt(history, "codex", current_round=2)
    assert "Claude handed off to you" in result
    assert "Implement the endpoints" in result


def test_format_prompt_no_self_mention():
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "claude", "content": "I agree with @Claude's earlier point", "round": 1},
    ]
    result = format_prompt(history, "claude", current_round=2)
    assert "You were @mentioned" not in result


def test_format_prompt_mention_only_from_current_round():
    """Mentions from older rounds should NOT trigger a notice."""
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "claude", "content": "@Kimi thoughts?", "round": 1},
        {"role": "kimi", "content": "I think it's good", "round": 1},
        {"role": "claude", "content": "Agreed, let's proceed", "round": 2},
        {"role": "codex", "content": "+1 Claude", "round": 2},
    ]
    # Round 3: only round 2 is current context. No @Kimi mention in round 2.
    result = format_prompt(history, "kimi", current_round=3)
    assert "You were @mentioned" not in result
