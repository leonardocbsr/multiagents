import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";
import StyledMarkdown from "./StyledMarkdown";
import type { Message } from "../types";

interface Props {
  agent: string;
  agentType?: string;
  messages: Message[];
  prompts: Record<number, Record<string, string>>;
  stream: string | undefined;
  status: "idle" | "streaming" | "done" | "failed";
  expanded: boolean;
  onToggle: () => void;
  onSendDM?: (text: string) => void;
}

const STATUS_DOTS: Record<string, string> = {
  idle: "bg-zinc-600",
  streaming: "bg-emerald-400 animate-pulse",
  done: "bg-zinc-500",
  failed: "bg-red-400",
};

const SECTION_LABELS: Record<string, string> = {
  system: "System Prompt",
  memory: "Memory",
  cards: "Cards",
  round_delta: "Round",
};

const SECTION_ORDER = ["system", "memory", "cards", "round_delta"];

function PromptSection({ label, content }: { label: string; content: string }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="border-b border-cyan-500/10 last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-1.5 px-2 py-1 text-[10px] font-medium text-cyan-400/70 uppercase hover:bg-cyan-500/10 transition-colors"
      >
        <span className="text-[8px]">{open ? "\u25BC" : "\u25B6"}</span>
        {label}
      </button>
      {open && (
        <div className="px-2 pb-1.5">
          <pre className="text-[10px] text-zinc-500 whitespace-pre-wrap font-mono leading-relaxed break-words">
            {content}
          </pre>
        </div>
      )}
    </div>
  );
}

function PromptContext({ round, sections }: { round: number; sections: Record<string, string> }) {
  const [expanded, setExpanded] = useState(false);
  const keys = SECTION_ORDER.filter(k => sections[k]);

  if (keys.length === 0) return null;

  return (
    <div className="my-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[10px] text-cyan-400/60 hover:text-cyan-400/80 transition-colors"
      >
        <span>{expanded ? "\u25BC" : "\u25B6"}</span>
        <span>Context injected</span>
        <span className="text-zinc-600">&middot; Round {round}</span>
      </button>
      {expanded && (
        <div className="mt-1 border border-cyan-500/20 rounded bg-cyan-500/5 overflow-hidden">
          {keys.map((key) => (
            <PromptSection key={key} label={SECTION_LABELS[key] ?? key} content={sections[key]} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function AgentPanel({ agent, agentType, messages, prompts, stream, status, expanded, onToggle, onSendDM }: Props) {
  const resolvedType = agentType ?? agent;
  const color = AGENT_COLORS[resolvedType] ?? "text-zinc-400";
  const scrollRef = useRef<HTMLDivElement>(null);
  const [dmText, setDmText] = useState("");

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

  return (
    <div className={`flex flex-col border-b border-zinc-800 ${expanded ? "flex-1 min-h-0" : ""}`}>
      <button
        onClick={onToggle}
        className="flex items-center gap-2 px-3 py-2 hover:bg-zinc-900/50 transition-colors shrink-0"
      >
        {expanded ? <ChevronDown size={12} className="text-zinc-500" /> : <ChevronRight size={12} className="text-zinc-500" />}
        <div className={`w-1.5 h-1.5 rounded-full ${STATUS_DOTS[status] ?? "bg-zinc-700"}`} />
        <span className={`${color}`}>
          <AgentIcon agent={resolvedType} size={12} />
        </span>
        <span className={`text-xs font-medium capitalize ${color}`}>{agent}</span>
        <span className="text-[10px] text-zinc-600 capitalize ml-auto">{status}</span>
      </button>

      {expanded && (
        <div className="flex flex-col flex-1 min-h-0">
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-2 space-y-3">
            {(() => {
              const items: React.ReactNode[] = [];
              let lastRound: number | null = null;

              for (const msg of messages) {
                const round = msg.round_number;
                if (round !== null && round !== lastRound && prompts[round]) {
                  items.push(
                    <PromptContext key={`prompt-${round}`} round={round} sections={prompts[round]} />
                  );
                  lastRound = round;
                } else if (round !== lastRound) {
                  lastRound = round;
                }
                items.push(
                  <div key={msg.id} className="text-xs">
                    {msg.role.startsWith("dm:") ? (
                      <div className="flex items-center gap-1.5 text-[10px] text-violet-400/70 py-1">
                        <span className="font-medium">You &rarr; {agent}:</span>
                        <span className="text-violet-300/60">{msg.content}</span>
                      </div>
                    ) : msg.interrupted ? (
                      <div className="opacity-40">
                        {msg.round_number && (
                          <div className="text-[10px] text-zinc-600 mb-1">Round {msg.round_number}</div>
                        )}
                        <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-zinc-400 text-xs leading-relaxed break-words">
                          {msg.content}
                        </StyledMarkdown>
                        <div className="flex items-center gap-2 py-1 text-[10px] text-amber-400/60">
                          <div className="flex-1 border-t border-amber-500/20" />
                          <span>interrupted</span>
                          <div className="flex-1 border-t border-amber-500/20" />
                        </div>
                      </div>
                    ) : msg.passed ? (
                      <span className="text-zinc-600 italic text-[10px]">Round {msg.round_number} — passed</span>
                    ) : (
                      <div>
                        {msg.round_number && (
                          <div className="text-[10px] text-zinc-600 mb-1">Round {msg.round_number}</div>
                        )}
                        <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-zinc-400 text-xs leading-relaxed break-words">
                          {msg.content}
                        </StyledMarkdown>
                      </div>
                    )}
                  </div>
                );
              }
              return items;
            })()}
            {stream && (
              <div className="text-xs">
                <div className="flex items-center gap-1 mb-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-[10px] text-zinc-600">Streaming</span>
                </div>
                <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-zinc-400 text-xs leading-relaxed break-words">
                  {stream}
                </StyledMarkdown>
              </div>
            )}
          </div>
          <form onSubmit={handleDMSubmit} className="px-3 py-2 border-t border-zinc-800/50 shrink-0">
            <input
              type="text"
              value={dmText}
              onChange={(e) => setDmText(e.target.value)}
              placeholder={`DM ${agent}...`}
              disabled={!onSendDM}
              className={`w-full bg-zinc-900/50 border border-zinc-800 rounded px-2 py-1.5 text-xs placeholder-zinc-700 ${
                onSendDM
                  ? "text-zinc-300 focus:border-zinc-600 focus:outline-none"
                  : "text-zinc-600 cursor-not-allowed"
              }`}
            />
          </form>
        </div>
      )}
    </div>
  );
}
