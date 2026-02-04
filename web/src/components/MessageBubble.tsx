import { useCallback, useMemo, useState } from "react";
import type { Message, AgentInfo } from "../types";
import { parseCoordinationPatterns } from "../types";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";
import StyledMarkdown from "./StyledMarkdown";
import CoordinationBadges from "./CoordinationBadges";

interface Props {
  message: Message;
  agents?: AgentInfo[];
}

export default function MessageBubble({ message, agents }: Props) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";
  const isSystem = message.role === "system" || message.role === "error";
  const isPassed = message.passed;
  const agentInfo = agents?.find(a => a.name === message.role);
  const agentType = agentInfo?.type ?? message.role;
  const color = AGENT_COLORS[agentType] ?? "text-zinc-400";
  const canCopy = !isUser && !isSystem && !isPassed && message.content.trim().length > 0;

  // Parse coordination patterns for agent messages
  const patterns = !isUser && !isSystem && !isPassed
    ? parseCoordinationPatterns(message.content, { allowedAgents: agents?.map(a => a.name) })
    : null;

  const meta = useMemo(() => {
    const parts: string[] = [];
    if (typeof message.latency_ms === "number") {
      parts.push(`${Math.round(message.latency_ms)}ms`);
    }
    if (typeof message.stream_chunks === "number") {
      parts.push(`${message.stream_chunks} chunks`);
    }
    return parts.join(" · ");
  }, [message.latency_ms, message.stream_chunks]);

  const handleCopy = useCallback(async () => {
    if (!canCopy) return;
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  }, [canCopy, message.content]);

  if (isUser) {
    return (
      <div className="flex gap-2.5">
        <div className="w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center text-xs font-medium shrink-0">You</div>
        <div className="flex-1 pt-1"><p className="text-sm text-zinc-200">{message.content}</p></div>
      </div>
    );
  }

  if (isSystem) {
    return (
      <div className="flex gap-2.5">
        <div className="w-7 h-7 rounded-full bg-amber-500/20 flex items-center justify-center text-xs font-medium text-amber-200 shrink-0">!</div>
        <div className="flex-1 pt-1">
          <p className="text-xs text-amber-200 whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-2.5 ${isPassed ? "opacity-40" : ""}`}>
      <div className={`w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center shrink-0 ${color}`}>
        <AgentIcon agent={agentType} size={14} />
      </div>
      <div className="flex-1 pt-0.5 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-xs font-medium capitalize ${color}`}>{message.role}</span>
          {isPassed && <span className="text-[10px] text-zinc-600">[PASS]</span>}
          {!isPassed && meta && <span className="text-[10px] text-zinc-600">{meta}</span>}
          {message.stderr && (
            <span
              className="text-[10px] text-amber-200/90 bg-amber-500/10 border border-amber-500/20 rounded px-1.5 py-0.5"
              title={message.stderr}
            >
              stderr
            </span>
          )}
          {canCopy && (
            <button
              onClick={handleCopy}
              className="ml-auto text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
              title="Copy response"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          )}
        </div>
        {isPassed ? (
          <p className="text-xs text-zinc-600 italic">No new input</p>
        ) : (
          <>
            <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-zinc-300 text-xs leading-relaxed break-words">
              {message.content}
            </StyledMarkdown>
            {patterns && <CoordinationBadges patterns={patterns} />}
          </>
        )}
      </div>
    </div>
  );
}
