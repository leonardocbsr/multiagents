import { useMemo, useState } from "react";
import { Send } from "lucide-react";
import type { AppState } from "../types";
import StyledMarkdown from "./StyledMarkdown";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";
import { Button, Input } from "./ui";

interface Props {
  state: AppState;
  selectedAgent: string | null;
  onSelectAgent: (agent: string) => void;
  onSendDM?: (agent: string, text: string) => boolean;
}

const SHARE_RE = /<Share>([\s\S]*?)<\/Share>/gi;

function unwrapShareContent(content: string): string {
  const matches = Array.from(content.matchAll(SHARE_RE));
  if (matches.length === 0) return content;
  return matches.map((m) => m[1].trim()).filter(Boolean).join("\n\n");
}

export default function SessionContextPanel({ state, selectedAgent, onSelectAgent, onSendDM }: Props) {
  const [dmText, setDmText] = useState("");
  const orderedAgents = useMemo(() => {
    const latestByAgent = new Map<string, number>();
    for (const msg of state.messages) {
      const role = msg.role.startsWith("dm:") ? msg.role.slice(3) : msg.role;
      if (!state.agents.some((a) => a.name === role)) continue;
      const ts = Date.parse(msg.created_at);
      const parsed = Number.isFinite(ts) ? ts : 0;
      const prev = latestByAgent.get(role) ?? 0;
      if (parsed > prev) latestByAgent.set(role, parsed);
    }
    return [...state.agents].sort((a, b) => {
      const diff = (latestByAgent.get(b.name) ?? 0) - (latestByAgent.get(a.name) ?? 0);
      if (diff !== 0) return diff;
      return a.name.localeCompare(b.name);
    });
  }, [state.agents, state.messages]);

  const messages = useMemo(() => {
    if (!selectedAgent) return [];
    return state.messages.filter((m) => (m.role === selectedAgent || m.role === `dm:${selectedAgent}`) && !m.passed);
  }, [state.messages, selectedAgent]);

  const selectedInfo = useMemo(
    () => state.agents.find((a) => a.name === selectedAgent) ?? null,
    [state.agents, selectedAgent]
  );
  const selectedType = selectedInfo?.type ?? "claude";
  const selectedModel = selectedInfo?.model ?? selectedType;
  const selectedColorClass = AGENT_COLORS[selectedType] ?? "text-ui-muted";
  const selectedStream = selectedAgent ? state.agentStreams[selectedAgent] ?? "" : "";
  const canSendDM = !!selectedAgent && !!onSendDM && dmText.trim().length > 0;

  const handleSendDM = () => {
    const agent = selectedAgent;
    const text = dmText.trim();
    if (!agent || !onSendDM || !text) return;
    const ok = onSendDM(agent, text);
    if (ok !== false) setDmText("");
  };

  return (
    <div className="h-full min-h-0 flex">
      <div className="w-56 shrink-0 border-r border-ui-soft flex flex-col min-h-0">
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {orderedAgents.map((agentInfo) => {
            const isSelected = selectedAgent === agentInfo.name;
            const colorClass = AGENT_COLORS[agentInfo.type] ?? "text-ui-muted";
            const status = state.agentStatuses[agentInfo.name] ?? "idle";
            return (
              <button
                key={agentInfo.name}
                onClick={() => onSelectAgent(agentInfo.name)}
                className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-md text-left border transition-colors cursor-pointer ${
                  isSelected
                    ? "bg-ui-elevated border-ui-strong"
                    : "bg-ui-surface border-ui-soft hover:bg-ui-elevated"
                }`}
                title={`Open ${agentInfo.name} context`}
              >
                <span className={colorClass}>
                  <AgentIcon agent={agentInfo.type} size={12} />
                </span>
                <span className={`text-[12px] font-medium ${isSelected ? "text-ui" : "text-ui-muted"} truncate`}>
                  {agentInfo.name}
                </span>
                <span className={`ml-auto w-2 h-2 rounded-full ${
                  status === "streaming"
                    ? "dot-status-streaming status-breathe-streaming"
                    : status === "failed"
                      ? "dot-status-failed"
                      : status === "done"
                        ? "dot-status-done status-breathe-done"
                        : "dot-status-idle status-breathe-idle"
                }`} />
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex-1 min-w-0 flex flex-col min-h-0">
        <div className="flex-1 overflow-auto px-4 py-3 space-y-2">
        {!selectedAgent && <div className="text-[12px] text-ui-muted">No agent selected.</div>}
        {selectedAgent && messages.length === 0 && !selectedStream && (
          <div className="text-[12px] text-ui-muted">No messages for this agent yet.</div>
        )}

        {messages.map((msg) => {
          const ts = (() => {
            const parsed = Date.parse(msg.created_at);
            if (!Number.isFinite(parsed)) return "";
            return new Date(parsed).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
          })();
          const isShared = /<Share>[\s\S]*?<\/Share>/i.test(msg.content);
          const normalizedContent = unwrapShareContent(msg.content);
          const compactPreview = normalizedContent.replace(/\s+/g, " ").trim();
          const isExpandable = normalizedContent.includes("\n") || compactPreview.length > 140;
          const badge = msg.role.startsWith("dm:")
            ? { label: "dm", klass: "badge-violet" }
            : isShared
              ? { label: "shared", klass: "badge-shared" }
            : msg.interrupted
              ? { label: "interrupted", klass: "badge-warn" }
              : { label: "responded", klass: "badge-responded" };

          return (
            <div key={msg.id} className="py-2 border-b border-ui-soft last:border-b-0">
              <div className="flex items-center gap-2">
                <span className={selectedColorClass}>
                  <AgentIcon agent={selectedType} size={11} />
                </span>
                <span className={`text-[11px] font-semibold capitalize ${selectedColorClass}`}>{selectedAgent}</span>
                <span className="text-[10px] text-ui-faint">{selectedModel}</span>
                <div className="ml-auto flex items-center gap-1.5">
                  {ts && <span className="text-[10px] text-ui-faint">{ts}</span>}
                  <span className={`badge ${badge.klass} text-[9px] py-0 shrink-0`}>{badge.label}</span>
                </div>
              </div>
              {!normalizedContent ? (
                <div className="pl-[19px] mt-1">
                  <span className="text-[11px] text-ui-faint italic">No content</span>
                </div>
              ) : isExpandable ? (
                <details className="pl-[19px] mt-1 group">
                  <summary className="text-[11px] text-ui-subtle cursor-pointer hover:text-ui list-none">
                    <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui-muted text-[12px] leading-[1.5] break-words max-h-[2.8em] overflow-hidden">
                      {normalizedContent}
                    </StyledMarkdown>
                    <span className="mt-1 inline-flex items-center gap-1.5 text-[10px] font-medium text-ui-info hover:underline">
                      <span className="inline-block transition-transform group-open:rotate-90">&#8250;</span>
                      <span className="group-open:hidden">Show full message</span>
                      <span className="hidden group-open:inline">Hide full message</span>
                    </span>
                  </summary>
                  <div className="mt-1.5">
                    <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui-muted text-[12px] leading-[1.5] break-words">
                      {normalizedContent}
                    </StyledMarkdown>
                  </div>
                </details>
              ) : (
                <div className="pl-[19px] mt-1">
                  <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui-muted text-[12px] leading-[1.5] break-words">
                    {normalizedContent}
                  </StyledMarkdown>
                </div>
              )}
            </div>
          );
        })}

        {selectedStream && (
          <div className="py-2 border-b border-ui-info-soft">
            <div className="flex items-center gap-2">
              <span className="shrink-0 text-ui-info">
                <AgentIcon agent={selectedType} size={11} />
              </span>
              <span className={`text-[11px] font-semibold capitalize ${selectedColorClass}`}>{selectedAgent}</span>
              <span className="text-[10px] text-ui-faint">{selectedModel}</span>
              <div className="ml-auto flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full dot-status-streaming status-breathe-streaming" />
                <span className="text-[10px] text-ui-info">streaming</span>
              </div>
            </div>
            <StyledMarkdown className="pl-[19px] mt-1 prose prose-invert prose-sm max-w-none text-ui-muted text-[12px] leading-[1.5] break-words">
              {selectedStream}
            </StyledMarkdown>
          </div>
        )}
        </div>
        <div className="h-12 border-t border-ui-soft px-3 flex items-center gap-2 shrink-0">
          <Input
            type="text"
            value={dmText}
            onChange={(e) => setDmText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleSendDM();
              }
            }}
            placeholder={selectedAgent ? `DM ${selectedAgent}...` : "Select an agent to send DM"}
            className="flex-1 text-xs"
            disabled={!selectedAgent || !onSendDM}
          />
          <Button
            onClick={handleSendDM}
            disabled={!canSendDM}
            className="w-8 h-8 !p-0"
            title="Send DM"
            aria-label="Send DM"
            icon={<Send size={13} />}
          >
            <span className="sr-only">Send DM</span>
          </Button>
        </div>
      </div>
    </div>
  );
}
