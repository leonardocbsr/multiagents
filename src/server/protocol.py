from __future__ import annotations

from datetime import datetime, timezone

from ..chat.events import (
    AgentCompleted,
    AgentDeliveryAcked,
    AgentInterrupted,
    AgentNotice,
    AgentPermissionRequested,
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

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def event_to_dict(event: ChatEvent) -> dict:
    match event:
        case RoundStarted(round_number=rn, agents=agents):
            return {"type": "round_started", "round": rn, "agents": agents}
        case AgentStreamChunk(agent_name=agent, round_number=rn, text=text):
            return {"type": "agent_stream", "agent": agent, "round": rn, "chunk": text}
        case AgentStderr(agent_name=agent, round_number=rn, text=text):
            return {"type": "agent_stderr", "agent": agent, "round": rn, "text": text}
        case AgentNotice(agent_name=agent, message=msg):
            return {"type": "agent_notice", "agent": agent, "message": msg, "created_at": _ts()}
        case AgentCompleted(agent_name=agent, round_number=rn, response=resp, passed=passed, stopped=stopped):
            return {
                "type": "agent_completed",
                "agent": agent,
                "round": rn,
                "text": resp.response,
                "passed": passed,
                "success": resp.success,
                "latency_ms": resp.latency_ms,
                "stopped": stopped,
                "created_at": _ts(),
            }
        case RoundEnded(round_number=rn, all_passed=ap):
            return {"type": "round_ended", "round": rn, "all_passed": ap}
        case RoundPaused(round_number=rn):
            return {"type": "paused", "round": rn}
        case DiscussionEnded(reason=reason):
            return {"type": "discussion_ended", "reason": reason}
        case UserMessageReceived(text=text):
            return {"type": "user_message", "text": text, "created_at": _ts()}
        case AgentInterrupted(agent_name=agent, round_number=rn, partial_text=text):
            return {"type": "agent_interrupted", "agent": agent, "round": rn, "partial_text": text, "created_at": _ts()}
        case AgentPromptAssembled(agent_name=agent, round_number=rn, sections=sections):
            return {"type": "agent_prompt", "agent": agent, "round": rn, "sections": sections}
        case AgentDeliveryAcked(delivery_id=delivery_id, recipient=recipient, sender=sender, round_number=rn):
            return {
                "type": "delivery_acked",
                "delivery_id": delivery_id,
                "recipient": recipient,
                "sender": sender,
                "round": rn,
                "created_at": _ts(),
            }
        case AgentPermissionRequested(agent_name=agent, round_number=rn, request_id=rid, tool_name=tool, tool_input=tinput, description=desc):
            return {
                "type": "permission_request", "agent": agent, "round": rn,
                "request_id": rid, "tool_name": tool, "tool_input": tinput,
                "description": desc, "created_at": _ts(),
            }
        case _:
            return {"type": "unknown"}
