from __future__ import annotations

from ..chat.events import (
    AgentCompleted,
    AgentInterrupted,
    AgentNotice,
    AgentPromptAssembled,
    AgentStderr,
    AgentStreamChunk,
    ChatEvent,
    DiscussionEnded,
    RoundEnded,
    RoundPaused,
    RoundStarted,
    UserMessageReceived,
)


def event_to_dict(event: ChatEvent) -> dict:
    match event:
        case RoundStarted(round_number=rn, agents=agents):
            return {"type": "round_started", "round": rn, "agents": agents}
        case AgentStreamChunk(agent_name=agent, text=text):
            return {"type": "agent_stream", "agent": agent, "chunk": text}
        case AgentStderr(agent_name=agent, text=text):
            return {"type": "agent_stderr", "agent": agent, "text": text}
        case AgentNotice(agent_name=agent, message=msg):
            return {"type": "agent_notice", "agent": agent, "message": msg}
        case AgentCompleted(agent_name=agent, response=resp, passed=passed, stopped=stopped):
            return {"type": "agent_completed", "agent": agent, "text": resp.response, "passed": passed, "success": resp.success, "latency_ms": resp.latency_ms, "stopped": stopped}
        case RoundEnded(round_number=rn, all_passed=ap):
            return {"type": "round_ended", "round": rn, "all_passed": ap}
        case RoundPaused(round_number=rn):
            return {"type": "paused", "round": rn}
        case DiscussionEnded(reason=reason):
            return {"type": "discussion_ended", "reason": reason}
        case UserMessageReceived(text=text):
            return {"type": "user_message", "text": text}
        case AgentInterrupted(agent_name=agent, round_number=rn, partial_text=text):
            return {"type": "agent_interrupted", "agent": agent, "round": rn, "partial_text": text}
        case AgentPromptAssembled(agent_name=agent, round_number=rn, sections=sections):
            return {"type": "agent_prompt", "agent": agent, "round": rn, "sections": sections}
        case _:
            return {"type": "unknown"}
