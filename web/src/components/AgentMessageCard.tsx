import type { ReactNode } from "react";
import { AgentIcon, AGENT_AVATAR_CLASSES, AGENT_COLORS } from "./AgentIcons";

interface Props {
  agentName: string;
  agentType: string;
  modelLabel?: string;
  className?: string;
  onAgentClick?: () => void;
  meta?: string;
  headerRight?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}

export default function AgentMessageCard({
  agentName,
  agentType,
  modelLabel,
  className,
  onAgentClick,
  meta,
  headerRight,
  children,
  footer,
}: Props) {
  const color = AGENT_COLORS[agentType] ?? "text-ui-muted";
  const avatarClass = AGENT_AVATAR_CLASSES[agentType] ?? "";
  const model = modelLabel ?? "";
  const family = agentType;
  const modelText = model || "unknown";
  const railColor = agentType === "claude"
    ? "var(--agent-claude)"
    : agentType === "codex"
      ? "var(--agent-codex)"
      : agentType === "kimi"
        ? "var(--agent-kimi)"
        : "var(--border-active)";

  return (
    <div className={`chat-bubble-agent relative overflow-hidden ${className ?? ""}`}>
      <span
        aria-hidden="true"
        className="absolute left-0 top-0 bottom-0 w-[2px]"
        style={{ background: railColor, opacity: 0.65 }}
      />
      <div className="flex items-center mb-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <div className={`chat-avatar ${avatarClass} ${color}`}>
            <AgentIcon agent={agentType} size={14} />
          </div>
          {onAgentClick ? (
            <button onClick={onAgentClick} className={`text-[13px] font-semibold capitalize ${color} hover:underline cursor-pointer`}>
              {agentName}
            </button>
          ) : (
            <span className={`text-[13px] font-semibold capitalize ${color}`}>{agentName}</span>
          )}
          <span className="text-[10px] text-ui-faint shrink-0" style={{ opacity: 0.7 }}>
            ·
          </span>
          <span className="text-[10px] text-ui-faint capitalize shrink-0" style={{ opacity: 0.7 }}>
            {family}
          </span>
          <span className="text-[10px] text-ui-faint shrink-0" style={{ opacity: 0.7 }}>
            ·
          </span>
          <span className="text-[10px] text-ui-faint shrink-0" style={{ opacity: 0.7 }}>
            {modelText}
          </span>
          {meta && <span className="text-[10px] text-ui-faint shrink-0">{meta}</span>}
        </div>
        {headerRight && <div className="ml-auto flex items-center gap-1.5 shrink-0">{headerRight}</div>}
      </div>
      <div className="pt-0">
        {children}
      </div>
      {footer}
    </div>
  );
}
