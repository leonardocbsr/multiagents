import { useEffect, useRef } from "react";
import type { AgentInfo } from "../types";
import { parseCoordinationPatterns } from "../types";
import StyledMarkdown from "./StyledMarkdown";
import CoordinationBadges from "./CoordinationBadges";
import AgentMessageCard from "./AgentMessageCard";

interface Props {
  agent: string;
  stream: string;
  agents?: AgentInfo[];
}

export default function StreamingBubble({ agent, stream, agents }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const agentInfo = agents?.find(a => a.name === agent);
  const agentType = agentInfo?.type ?? agent;
  const modelLabel = agentInfo?.model ?? undefined;

  // Parse coordination patterns from the stream
  const patterns = stream ? parseCoordinationPatterns(stream, { allowedAgents: agents?.map(a => a.name) }) : null;

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  });

  return (
    <div className="flex-1 min-w-0" ref={scrollRef}>
      <AgentMessageCard
        agentName={agent}
        agentType={agentType}
        modelLabel={modelLabel}
        headerRight={<span className="w-1.5 h-1.5 rounded-full dot-status-streaming animate-pulse" />}
        footer={patterns ? <CoordinationBadges patterns={patterns} /> : undefined}
      >
        {stream ? (
          <>
            {stream.length > 1600 ? (
              <details className="text-xs">
                <summary className="cursor-pointer text-ui-subtle hover:text-ui mb-1">Show long stream</summary>
                <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui text-[13.5px] leading-[1.7] break-words">{stream}</StyledMarkdown>
              </details>
            ) : (
              <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui text-[13.5px] leading-[1.7] break-words">{stream}</StyledMarkdown>
            )}
          </>
        ) : (
          <div className="flex items-center gap-2 text-xs text-ui-faint">
            <span className="w-1.5 h-1.5 rounded-full bg-ui-soft animate-pulse" />Thinking...
          </div>
        )}
      </AgentMessageCard>
    </div>
  );
}
