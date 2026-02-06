import { useCallback, useMemo, useState } from "react";
import { User } from "lucide-react";
import type { Message, AgentInfo } from "../types";
import { parseCoordinationPatterns } from "../types";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";
import StyledMarkdown from "./StyledMarkdown";
import CoordinationBadges from "./CoordinationBadges";
import { Button } from "./ui";
import AgentMessageCard from "./AgentMessageCard";
import { copyTextToClipboard } from "../utils/clipboard";

interface Props {
  message: Message;
  agents?: AgentInfo[];
  density?: "compact" | "comfortable";
}

export default function MessageBubble({ message, agents, density = "comfortable" }: Props) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";
  const isSystem = message.role === "system" || message.role === "error";
  const isPassed = message.passed;
  const agentInfo = agents?.find(a => a.name === message.role);
  const agentType = agentInfo?.type ?? message.role;
  const modelLabel = agentInfo?.model ?? undefined;
  const color = AGENT_COLORS[agentType] ?? "text-ui-muted";
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
      const ok = await copyTextToClipboard(message.content);
      if (!ok) throw new Error("copy failed");
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  }, [canCopy, message.content]);

  if (isUser) {
    return (
      <div className="flex-1 min-w-0">
        <div className="chat-bubble-agent relative overflow-hidden">
          <span
            aria-hidden="true"
            className="absolute left-0 top-0 bottom-0 w-[2px]"
            style={{ background: "var(--accent-500)", opacity: 0.6 }}
          />
          <div className="flex items-center mb-1">
            <div className="flex items-center gap-1.5 min-w-0">
              <div className="chat-avatar border-ui-info-soft text-ui-info" aria-label="You">
                <User size={12} />
              </div>
              <span className="text-[13px] font-semibold text-ui-info">You</span>
            </div>
          </div>
          <div className="pt-0">
            <p className="text-sm text-ui-strong whitespace-pre-wrap break-words">{message.content}</p>
          </div>
        </div>
      </div>
    );
  }

  if (isSystem) {
    return (
      <div className={`flex ${density === "compact" ? "gap-2" : "gap-3"}`}>
        <div className="chat-avatar text-ui-warn">!</div>
        <div className="flex-1 min-w-0">
          <div className="chat-bubble-system">
            <p className="text-xs whitespace-pre-wrap break-words">{message.content}</p>
          </div>
        </div>
      </div>
    );
  }

  // Pass indicator — dashed circle + name
  if (isPassed) {
    return (
      <div className="flex items-center gap-2 py-0.5 opacity-45">
        <div className="w-5 h-5 rounded-full border border-dashed border-ui-dashed flex items-center justify-center">
          <span className={`${color} opacity-70`}><AgentIcon agent={agentType} size={9} /></span>
        </div>
        <span className={`text-[11px] font-mono capitalize ${color} opacity-70`}>{message.role}</span>
        <span className="text-[11px] font-mono text-ui-faint">passed</span>
      </div>
    );
  }

  return (
    <div className="flex-1 min-w-0">
      <AgentMessageCard
        agentName={message.role}
        agentType={agentType}
        modelLabel={modelLabel}
        meta={meta}
        headerRight={(
          <>
            {message.stderr && (
              <span
                className="text-[10px] text-ui-warn bg-ui-warn-soft border border-ui-warn-soft rounded px-1.5 py-0.5"
                title={message.stderr}
              >
                stderr
              </span>
            )}
            {canCopy && (
              <Button
                onClick={handleCopy}
                variant="ghost"
                size="sm"
                className="text-[10px] text-ui-subtle hover:text-ui"
                title="Copy response"
              >
                {copied ? "Copied" : "Copy"}
              </Button>
            )}
          </>
        )}
        footer={patterns ? <CoordinationBadges patterns={patterns} /> : undefined}
      >
        {message.content.length > 1600 ? (
          <details className="text-xs">
            <summary className="cursor-pointer text-ui-subtle hover:text-ui mb-1">Show long message</summary>
            <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui text-[13.5px] leading-[1.7] break-words">
              {message.content}
            </StyledMarkdown>
          </details>
        ) : (
          <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui text-[13.5px] leading-[1.7] break-words">
            {message.content}
          </StyledMarkdown>
        )}
      </AgentMessageCard>
    </div>
  );
}
