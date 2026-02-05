import { useEffect, useRef } from "react";
import type { AgentInfo } from "../types";
import { parseCoordinationPatterns } from "../types";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";
import StyledMarkdown from "./StyledMarkdown";
import CoordinationBadges from "./CoordinationBadges";

interface Props {
  agent: string;
  stream: string;
  agents?: AgentInfo[];
}

export default function StreamingBubble({ agent, stream, agents }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const agentInfo = agents?.find(a => a.name === agent);
  const agentType = agentInfo?.type ?? agent;
  const color = AGENT_COLORS[agentType] ?? "text-zinc-400";

  // Parse coordination patterns from the stream
  const patterns = stream ? parseCoordinationPatterns(stream, { allowedAgents: agents?.map(a => a.name) }) : null;

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  });

  return (
    <div className="flex gap-2.5">
      <div className={`w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center shrink-0 ${color}`}>
        <AgentIcon agent={agentType} size={14} />
      </div>
      <div className="flex-1 pt-0.5 min-w-0" ref={scrollRef}>
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-xs font-medium capitalize ${color}`}>{agent}</span>
          <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-pulse" />
        </div>
        {stream ? (
          <>
            <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-zinc-400 text-xs leading-relaxed break-words">{stream}</StyledMarkdown>
            {patterns && <CoordinationBadges patterns={patterns} />}
          </>
        ) : (
          <div className="flex items-center gap-2 text-xs text-zinc-600">
            <span className="w-1.5 h-1.5 rounded-full bg-zinc-600 animate-pulse" />Thinking...
          </div>
        )}
      </div>
    </div>
  );
}
