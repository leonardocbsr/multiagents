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
  const agentMessages = useMemo(() => {
    const map: Record<string, typeof state.messages> = {};
    for (const agentInfo of state.agents) {
      map[agentInfo.name] = state.messages.filter((m) => m.role === agentInfo.name || m.role === `dm:${agentInfo.name}`);
    }
    return map;
  }, [state.messages, state.agents]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {state.agents.map((agentInfo) => (
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
