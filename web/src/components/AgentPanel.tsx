import { useEffect, useRef, useState } from "react";
import { AgentIcon, AGENT_COLORS, AGENT_AVATAR_CLASSES } from "./AgentIcons";
import StyledMarkdown from "./StyledMarkdown";
import type { Message } from "../types";
import { Button, Input } from "./ui";

interface Props {
  agent: string;
  agentType?: string;
  messages: Message[];
  prompts: Record<number, Record<string, string>>;
  stream: string | undefined;
  status: "idle" | "streaming" | "done" | "failed";
  expanded: boolean;
  selected?: boolean;
  onToggle: () => void;
  onSendDM?: (text: string) => void;
  density?: "compact" | "comfortable";
}

const STATUS_DOTS: Record<string, string> = {
  idle: "bg-ui-soft",
  streaming: "dot-status-streaming animate-pulse",
  done: "dot-status-done",
  failed: "dot-status-failed",
};

const SECTION_LABELS: Record<string, string> = {
  system: "System Prompt",
  memory: "Memory",
  cards: "Cards",
  round_delta: "Round",
};

const SECTION_ORDER = ["system", "memory", "cards", "round_delta"];

function formatMessageTime(createdAt: string): string {
  const ts = Date.parse(createdAt);
  if (Number.isNaN(ts)) return "";
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function PromptSection({ label, content }: { label: string; content: string }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="border-b border-ui-soft last:border-b-0">
      <Button
        onClick={() => setOpen(!open)}
        variant="ghost"
        size="sm"
        className="w-full justify-start gap-1.5 px-2 py-1 text-[10px] font-medium text-ui-info uppercase bg-ui-hover"
      >
        <span className="text-[8px]">{open ? "\u25BC" : "\u25B6"}</span>
        {label}
      </Button>
      {open && (
        <div className="px-2 pb-1.5">
          <pre className="text-[11px] text-ui-subtle whitespace-pre-wrap font-mono leading-relaxed break-words">
            {content}
          </pre>
        </div>
      )}
    </div>
  );
}

function PromptContext({ sections }: { sections: Record<string, string> }) {
  const [expanded, setExpanded] = useState(false);
  const keys = SECTION_ORDER.filter(k => sections[k]);

  if (keys.length === 0) return null;

  return (
    <div className="my-1">
      <Button
        onClick={() => setExpanded(!expanded)}
        variant="ghost"
        size="sm"
        className="justify-start gap-1.5 text-[10px] text-ui-info"
      >
        <span>{expanded ? "\u25BC" : "\u25B6"}</span>
        <span>Context injected</span>
      </Button>
      {expanded && (
        <div className="mt-1 border border-ui-info-soft rounded bg-ui-info-soft overflow-hidden">
          {keys.map((key) => (
            <PromptSection key={key} label={SECTION_LABELS[key] ?? key} content={sections[key]} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function AgentPanel({ agent, agentType, messages, prompts, stream, status, expanded, selected = false, onToggle, onSendDM, density = "comfortable" }: Props) {
  const resolvedType = agentType ?? agent;
  const color = AGENT_COLORS[resolvedType] ?? "text-ui-muted";
  const scrollRef = useRef<HTMLDivElement>(null);
  const [dmText, setDmText] = useState("");
  const [renderLimit, setRenderLimit] = useState(180);

  useEffect(() => {
    setRenderLimit(180);
  }, [agent]);

  useEffect(() => {
    if (expanded && status === "streaming" && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [expanded, status, stream]);

  const handleDMSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = dmText.trim();
    if (!text || !onSendDM) return;
    onSendDM(text);
    setDmText("");
  };
  const hiddenMessages = Math.max(0, messages.length - renderLimit);
  const renderedMessages = hiddenMessages > 0 ? messages.slice(-renderLimit) : messages;

  const avatarClass = AGENT_AVATAR_CLASSES[resolvedType] ?? "";
  const accentColor = resolvedType === "claude"
    ? "var(--agent-claude)"
    : resolvedType === "codex"
      ? "var(--agent-codex)"
      : resolvedType === "kimi"
        ? "var(--agent-kimi)"
        : "var(--border-active)";

  return (
    <div className={`flex flex-col ${expanded ? "flex-1 min-h-0" : ""}`}>
      {/* Agent row — card-style matching prototype */}
      <button
        onClick={onToggle}
        className="w-full text-left cursor-pointer transition-all shrink-0 rounded-[10px] relative overflow-hidden"
        style={{
          padding: '12px 16px',
          margin: '4px 8px',
          width: 'calc(100% - 16px)',
          background: selected || expanded ? "var(--bg-card)" : "transparent",
          border: expanded ? "1px solid var(--border-medium)" : "1px solid transparent",
        }}
        onMouseEnter={(e) => {
          if (!expanded && !selected) {
            e.currentTarget.style.background = "var(--bg-card)";
            e.currentTarget.style.borderColor = "var(--border-medium)";
          }
        }}
        onMouseLeave={(e) => {
          if (!expanded && !selected) {
            e.currentTarget.style.background = "transparent";
            e.currentTarget.style.borderColor = "transparent";
          }
        }}
      >
        {selected && (
          <span
            aria-hidden="true"
            className="absolute left-1 top-0 bottom-0 w-[3px] rounded-r"
            style={{ background: accentColor }}
          />
        )}
        <div className="flex items-center gap-2.5">
          <div
            className={`w-9 h-9 rounded-full flex items-center justify-center border shrink-0 ${avatarClass}`}
            style={{ borderWidth: '1.5px' }}
          >
            <span className={color}>
              <AgentIcon agent={resolvedType} size={15} />
            </span>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-[13px] font-semibold text-ui-strong capitalize">{agent}</span>
              <div className={`w-1.5 h-1.5 rounded-full ${STATUS_DOTS[status] ?? "bg-ui-soft"}`} />
            </div>
            <span className="text-[11px] font-mono text-ui-subtle capitalize">{resolvedType} · {status}</span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="flex flex-col flex-1 min-h-0">
          <div className="mx-4 my-1" style={{ height: 1, background: 'var(--border-subtle)' }} />
          <div ref={scrollRef} className={`flex-1 overflow-y-auto px-4 ${density === "compact" ? "py-1.5 space-y-2" : "py-2 space-y-3"}`}>
            {hiddenMessages > 0 && (
              <Button
                onClick={() => setRenderLimit((n) => n + 180)}
                variant="secondary"
                size="sm"
                className="w-full text-[10px] bg-ui-surface border-ui-strong text-ui-subtle hover:text-ui hover:bg-ui-elevated"
              >
                Show older ({hiddenMessages} hidden)
              </Button>
            )}
            {(() => {
              const items: React.ReactNode[] = [];
              let lastRound: number | null = null;
              let passRunCount = 0;

              const flushPassRun = () => {
                if (passRunCount > 1) {
                  items.push(
                    <div key={`pass-group-${items.length}`} className="flex items-center gap-2 py-0.5 opacity-50">
                      <div className="flex-1 border-t border-ui-soft" />
                      <span className="text-[10px] text-ui-faint">passed {passRunCount}x</span>
                      <div className="flex-1 border-t border-ui-soft" />
                    </div>
                  );
                }
                passRunCount = 0;
              };

              for (const msg of renderedMessages) {
                if (msg.passed && !msg.role.startsWith("dm:") && !msg.interrupted) {
                  if (passRunCount === 0) {
                    const msgTime = formatMessageTime(msg.created_at);
                    // Push the first one as-is
                    items.push(
                      <div key={msg.id} className="text-xs">
                        <span className="text-ui-faint italic text-[10px]">
                          passed
                          {msgTime ? ` · ${msgTime}` : ""}
                        </span>
                      </div>
                    );
                  }
                  passRunCount++;
                  continue;
                }

                if (passRunCount > 1) {
                  // Replace the single "passed" we pushed with a grouped one
                  items.pop();
                  flushPassRun();
                } else {
                  passRunCount = 0;
                }

                const msgTime = formatMessageTime(msg.created_at);
                const round = msg.round_number;
                if (round !== null && round !== lastRound && prompts[round]) {
                  items.push(
                    <PromptContext key={`prompt-${round}`} sections={prompts[round]} />
                  );
                  lastRound = round;
                } else if (round !== lastRound) {
                  lastRound = round;
                }
                items.push(
                  <div key={msg.id} className="text-xs">
                    {msg.role.startsWith("dm:") ? (
                      <div className="flex items-center gap-1.5 text-[10px] text-ui-violet py-1">
                        <span className="font-medium">You &rarr; {agent}:</span>
                        <span className="text-ui-violet">{msg.content}</span>
                        {msgTime && <span className="text-ui-violet ml-auto">{msgTime}</span>}
                      </div>
                    ) : msg.interrupted ? (
                      <div className="opacity-40">
                        {msgTime && (
                          <div className="text-[10px] text-ui-faint mb-1 flex items-center gap-2">
                            {msgTime && <span className="text-ui-faint">{msgTime}</span>}
                          </div>
                        )}
                        {msg.content.length > 1200 ? (
                          <details className="text-xs">
                            <summary className="cursor-pointer text-ui-subtle hover:text-ui mb-1">Show long message</summary>
                            <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui-muted text-xs leading-relaxed break-words">
                              {msg.content}
                            </StyledMarkdown>
                          </details>
                        ) : (
                          <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui-muted text-xs leading-relaxed break-words">
                            {msg.content}
                          </StyledMarkdown>
                        )}
                        <div className="flex items-center gap-2 py-1 text-[10px] text-ui-warn">
                          <div className="flex-1 border-t border-ui-warn-soft" />
                          <span>interrupted</span>
                          <div className="flex-1 border-t border-ui-warn-soft" />
                        </div>
                      </div>
                    ) : msg.passed ? (
                      <span className="text-ui-faint italic text-[10px]">
                        passed
                        {msgTime ? ` · ${msgTime}` : ""}
                      </span>
                    ) : (
                      <div>
                        {msgTime && (
                          <div className="text-[10px] text-ui-faint mb-1 flex items-center gap-2">
                            {msgTime && <span className="text-ui-faint">{msgTime}</span>}
                          </div>
                        )}
                        <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui-muted text-xs leading-relaxed break-words">
                          {msg.content}
                        </StyledMarkdown>
                      </div>
                    )}
                  </div>
                );
              }
              // Flush any trailing pass run
              if (passRunCount > 1) {
                items.pop();
                flushPassRun();
              }
              return items;
            })()}
            {stream && (
              <div className="text-xs">
                <div className="flex items-center gap-1 mb-1">
                  <span className="w-1.5 h-1.5 rounded-full dot-status-streaming animate-pulse" />
                  <span className="text-[10px] text-ui-faint">Streaming</span>
                </div>
                {stream.length > 1200 ? (
                  <details className="text-xs">
                    <summary className="cursor-pointer text-ui-subtle hover:text-ui mb-1">Show long stream</summary>
                    <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui-muted text-xs leading-relaxed break-words">
                      {stream}
                    </StyledMarkdown>
                  </details>
                ) : (
                  <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui-muted text-xs leading-relaxed break-words">
                    {stream}
                  </StyledMarkdown>
                )}
              </div>
            )}
          </div>
          <form onSubmit={handleDMSubmit} className="px-4 py-2 border-t border-ui-soft shrink-0">
            <Input
              type="text"
              value={dmText}
              onChange={(e) => setDmText(e.target.value)}
              placeholder={`DM ${agent}...`}
              disabled={!onSendDM}
              className={`w-full text-xs bg-ui-surface border-ui placeholder:text-ui-faint ${
                onSendDM
                  ? "text-ui focus:border-ui-strong focus:outline-none"
                  : "text-ui-faint cursor-not-allowed"
              }`}
            />
          </form>
        </div>
      )}
    </div>
  );
}
