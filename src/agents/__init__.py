from dataclasses import dataclass

from .base import BaseAgent
from .claude import ClaudeAgent
from .codex import CodexAgent
from .kimi import KimiAgent

AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "claude": ClaudeAgent,
    "codex": CodexAgent,
    "kimi": KimiAgent,
}


@dataclass
class AgentPersona:
    name: str
    type: str
    role: str = ""
    model: str | None = None


def create_agents(
    names_or_personas: list[str] | list[AgentPersona] | list[dict],
    parse_timeout: float | None = None,
    hard_timeout: float | None = None,
) -> list[BaseAgent]:
    personas: list[AgentPersona] = []
    for item in names_or_personas:
        if isinstance(item, str):
            personas.append(AgentPersona(name=item, type=item))
        elif isinstance(item, dict):
            personas.append(AgentPersona(
                name=item.get("name", item.get("type", "")),
                type=item.get("type", ""),
                role=item.get("role", ""),
                model=item.get("model"),
            ))
        elif isinstance(item, AgentPersona):
            personas.append(item)
        else:
            raise ValueError(f"Invalid agent spec: {item!r}")

    unknown = [p.type for p in personas if p.type not in AGENT_CLASSES]
    if unknown:
        raise ValueError(f"Unknown agent type(s): {', '.join(unknown)}")

    agents = []
    for persona in personas:
        agent = AGENT_CLASSES[persona.type]()
        agent.name = persona.name
        agent.agent_type = persona.type
        if persona.model:
            agent.model = persona.model
        if parse_timeout is not None:
            agent.parse_timeout = parse_timeout
        if hard_timeout is not None:
            agent.hard_timeout = hard_timeout
        agents.append(agent)
    return agents
