import { useMemo } from "react";
import type { AppState } from "../types";
import AgentPanel from "./AgentPanel";

interface Props {
  state: AppState;
  expandedAgents: Set<string>;
  onToggleAgent: (agent: string) => void;
  onSendDM?: (agent: string, text: string) => void;
}

export default function AgentPanels({ state, expandedAgents, onToggleAgent, onSendDM }: Props) {
  const getMessageTimestamp = (createdAt: string): number => {
    const ts = Date.parse(createdAt);
    return Number.isFinite(ts) ? ts : 0;
  };

  const orderedAgents = useMemo(() => {
    const latestByAgent = new Map<string, number>();
    for (const msg of state.messages) {
      const role = msg.role.startsWith("dm:") ? msg.role.slice(3) : msg.role;
      if (!state.agents.some((a) => a.name === role)) continue;
      const ts = getMessageTimestamp(msg.created_at);
      const prev = latestByAgent.get(role) ?? 0;
      if (ts > prev) latestByAgent.set(role, ts);
    }
    return [...state.agents].sort((a, b) => {
      const diff = (latestByAgent.get(b.name) ?? 0) - (latestByAgent.get(a.name) ?? 0);
      if (diff !== 0) return diff;
      return a.name.localeCompare(b.name);
    });
  }, [state.agents, state.messages]);

  const agentMessages = useMemo(() => {
    const map: Record<string, typeof state.messages> = {};
    for (const agentInfo of state.agents) {
      map[agentInfo.name] = state.messages.filter((m) => m.role === agentInfo.name || m.role === `dm:${agentInfo.name}`);
    }
    return map;
  }, [state.messages, state.agents]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {orderedAgents.map((agentInfo) => (
        <AgentPanel
          key={agentInfo.name}
          agent={agentInfo.name}
          agentType={agentInfo.type}
          messages={agentMessages[agentInfo.name] ?? []}
          prompts={state.agentPrompts[agentInfo.name] ?? {}}
          stream={
            state.agentStatuses[agentInfo.name] === "streaming"
              ? state.agentStreams[agentInfo.name]
              : undefined
          }
          status={state.agentStatuses[agentInfo.name] ?? "idle"}
          expanded={expandedAgents.has(agentInfo.name)}
          onToggle={() => onToggleAgent(agentInfo.name)}
          onSendDM={onSendDM ? (text) => onSendDM(agentInfo.name, text) : undefined}
        />
      ))}
    </div>
  );
}
