import { useCallback, useEffect, useRef, useState, useMemo } from "react";
import { ArrowDown } from "lucide-react";
import { AgentIcon, AGENT_COLORS, AGENT_BG_COLORS } from "./AgentIcons";
import StyledMarkdown from "./StyledMarkdown";
import type { AppState, AgentInfo, Message } from "../types";

const SHARE_TAG_PATTERN = /<Share>(.*?)<\/Share>/is;
const THINKING_BLOCK_RE = /<(?:thinking|antThinking)>[\s\S]*?<\/(?:thinking|antThinking)>/gi;

/** Strip thinking blocks so a <Share> accidentally opened inside one doesn't swallow everything. */
function stripThinking(content: string): string {
  return content.replace(THINKING_BLOCK_RE, "");
}

function hasShareContent(content: string): boolean {
  return SHARE_TAG_PATTERN.test(stripThinking(content));
}

function extractShareOnly(content: string): string {
  const cleaned = stripThinking(content);
  const matches = Array.from(cleaned.matchAll(new RegExp(SHARE_TAG_PATTERN.source, "gis")));
  if (matches.length === 0) return "";
  return matches.map((m) => m[1].trim()).filter(Boolean).join("\n\n");
}

interface SharedEntry {
  kind: "user" | "shared" | "passed" | "responded" | "round";
  message?: Message;
  agent?: string;
  round?: number;
}

function buildSharedEntries(messages: Message[]): SharedEntry[] {
  const entries: SharedEntry[] = [];
  let lastRound = 0;

  for (const msg of messages) {
    if (msg.round_number && msg.round_number > lastRound) {
      lastRound = msg.round_number;
      entries.push({ kind: "round", round: msg.round_number });
    }

    if (msg.role === "user") {
      entries.push({ kind: "user", message: msg });
    } else if (msg.role === "system" || msg.role === "error") {
      // Skip system/error in shared view
    } else if (msg.passed) {
      entries.push({ kind: "passed", message: msg, agent: msg.role });
    } else if (hasShareContent(msg.content)) {
      entries.push({ kind: "shared", message: msg, agent: msg.role });
    } else {
      entries.push({ kind: "responded", message: msg, agent: msg.role });
    }
  }
  return entries;
}

interface Props {
  state: AppState;
  onExpandAgent?: (agent: string) => void;
}

function resolveAgentType(agentName: string, agents: AgentInfo[]): string {
  const info = agents.find(a => a.name === agentName);
  return info?.type ?? agentName;
}

export default function SharedChat({ state, onExpandAgent }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [isNearBottom, setIsNearBottom] = useState(true);

  const checkScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    setIsNearBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener("scroll", checkScroll, { passive: true });
    return () => el.removeEventListener("scroll", checkScroll);
  }, [checkScroll]);

  useEffect(() => {
    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [state.messages, state.agentStreams, isNearBottom]);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const entries = useMemo(() => buildSharedEntries(state.messages), [state.messages]);

  const activeSharedStreams = useMemo(() => {
    const result: { agent: string; content: string }[] = [];
    for (const [agent, stream] of Object.entries(state.agentStreams)) {
      if (state.agentStatuses[agent] === "streaming" && stream && hasShareContent(stream)) {
        const shared = extractShareOnly(stream);
        if (shared) result.push({ agent, content: shared });
      }
    }
    return result;
  }, [state.agentStreams, state.agentStatuses]);

  return (
    <div className="relative flex-1 overflow-auto p-3 md:p-4" ref={containerRef}>
      <div className="max-w-3xl mx-auto space-y-3">
        {entries.map((entry) => {
          if (entry.kind === "round") {
            return (
              <div key={`round-${entry.round}`} className="flex items-center gap-3 py-1">
                <div className="flex-1 border-t border-zinc-800" />
                <span className="text-[10px] text-zinc-600 uppercase tracking-wider">Round {entry.round}</span>
                <div className="flex-1 border-t border-zinc-800" />
              </div>
            );
          }

          if (entry.kind === "user" && entry.message) {
            return (
              <div key={entry.message.id} className="flex gap-2.5">
                <div className="w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center text-xs font-medium shrink-0">You</div>
                <div className="flex-1 pt-1">
                  <p className="text-sm text-zinc-200">{entry.message.content}</p>
                </div>
              </div>
            );
          }

          if (entry.kind === "passed" && entry.message && entry.agent) {
            const aType = resolveAgentType(entry.agent, state.agents);
            const color = AGENT_COLORS[aType] ?? "text-zinc-400";
            const bgColor = AGENT_BG_COLORS[aType] ?? "bg-zinc-400";
            return (
              <div key={entry.message.id} className="flex items-center gap-2 py-0.5 opacity-50">
                <div className={`w-1.5 h-1.5 rounded-full ${bgColor}`} />
                <span className={`text-[11px] capitalize ${color}`}>{entry.agent}</span>
                <span className="text-[10px] text-zinc-600">passed</span>
              </div>
            );
          }

          if (entry.kind === "shared" && entry.message && entry.agent) {
            const aType = resolveAgentType(entry.agent, state.agents);
            const color = AGENT_COLORS[aType] ?? "text-zinc-400";
            const shareContent = `<Share>${extractShareOnly(entry.message.content)}</Share>`;
            return (
              <div key={entry.message.id} className="flex gap-2.5">
                <div className={`w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center shrink-0 ${color}`}>
                  <AgentIcon agent={aType} size={14} />
                </div>
                <div className="flex-1 pt-0.5 min-w-0">
                  <span className={`text-xs font-medium capitalize ${color}`}>{entry.agent}</span>
                  <StyledMarkdown
                    className="prose prose-invert prose-sm max-w-none text-zinc-300 text-xs leading-relaxed break-words"
                    shareHeader={null}
                  >
                    {shareContent}
                  </StyledMarkdown>
                </div>
              </div>
            );
          }

          if (entry.kind === "responded" && entry.message && entry.agent) {
            const aType = resolveAgentType(entry.agent, state.agents);
            const color = AGENT_COLORS[aType] ?? "text-zinc-400";
            const bgColor = AGENT_BG_COLORS[aType] ?? "bg-zinc-400";
            return (
              <button
                key={entry.message.id}
                onClick={() => onExpandAgent?.(entry.agent!)}
                className="flex items-center gap-2 py-0.5 hover:bg-zinc-900/50 rounded px-1 -mx-1 transition-colors group"
              >
                <div className={`w-1.5 h-1.5 rounded-full ${bgColor}`} />
                <span className={`text-[11px] capitalize ${color}`}>{entry.agent}</span>
                <span className="text-[10px] text-zinc-600">responded</span>
                <span className="text-[10px] text-zinc-700 opacity-0 group-hover:opacity-100 transition-opacity">— click to view</span>
              </button>
            );
          }

          return null;
        })}

        {activeSharedStreams.map(({ agent, content }) => {
          const aType = resolveAgentType(agent, state.agents);
          const color = AGENT_COLORS[aType] ?? "text-zinc-400";
          return (
            <div key={`stream-shared-${agent}`} className="flex gap-2.5">
              <div className={`w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center shrink-0 ${color}`}>
                <AgentIcon agent={aType} size={14} />
              </div>
              <div className="flex-1 pt-0.5 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-xs font-medium capitalize ${color}`}>{agent}</span>
                  <span className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-pulse" />
                </div>
                <StyledMarkdown
                  className="prose prose-invert prose-sm max-w-none text-zinc-300 text-xs leading-relaxed break-words"
                  shareHeader={null}
                >
                  {`<Share>${content}</Share>`}
                </StyledMarkdown>
              </div>
            </div>
          );
        })}

        <div ref={bottomRef} />
      </div>
      {!isNearBottom && (
        <button
          onClick={scrollToBottom}
          className="sticky bottom-3 left-1/2 -translate-x-1/2 w-8 h-8 flex items-center justify-center rounded-full bg-zinc-800 border border-zinc-700 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 transition-colors shadow-lg"
          title="Jump to bottom"
        >
          <ArrowDown size={14} />
        </button>
      )}
    </div>
  );
}
