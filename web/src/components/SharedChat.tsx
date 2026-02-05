import { useCallback, useEffect, useRef, useState, useMemo } from "react";
import { ArrowDown } from "lucide-react";
import { User } from "lucide-react";
import { AgentIcon, AGENT_AVATAR_CLASSES, AGENT_COLORS } from "./AgentIcons";
import StyledMarkdown from "./StyledMarkdown";
import type { AppState, AgentInfo, Message } from "../types";
import { Button, Card, CardContent, CardFooter, CardHeader } from "./ui";
import AgentMessageCard from "./AgentMessageCard";
import AgentStatusBar from "./AgentStatusBar";

const SHARE_TAG_PATTERN = /<Share>(.*?)<\/Share>/is;
const THINKING_BLOCK_RE = /<(?:thinking|antThinking)>[\s\S]*?<\/(?:thinking|antThinking)>/gi;
const STATUS_TAG_RE_GLOBAL = /(?:\[(EXPLORE|DECISION|BLOCKED|DONE|TODO|QUESTION)\]|\[STATUS:\s*([^\]\n]+)\])/gi;
const STATUS_COLORS: Record<string, string> = {
  EXPLORE: "badge-info",
  DECISION: "badge-success",
  BLOCKED: "badge-danger",
  DONE: "badge-success",
  TODO: "badge-warn",
  QUESTION: "badge-violet",
  READY: "badge-cyan",
  "IN PROGRESS": "badge-info",
};
const DEFAULT_STATUS_COLOR = "badge-info";
const HANDOFF_RE_GLOBAL = /\[HANDOFF:(\w+)\]/gi;

function extractHandoffs(text: string): string[] {
  HANDOFF_RE_GLOBAL.lastIndex = 0;
  const found: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = HANDOFF_RE_GLOBAL.exec(text)) !== null) {
    const agent = match[1];
    if (!found.some(h => h.toLowerCase() === agent.toLowerCase())) {
      found.push(agent);
    }
  }
  return found;
}

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

function normalizeStatus(status: string): string {
  return status.trim().replace(/\s+/g, " ").toUpperCase();
}

function extractStatuses(text: string): string[] {
  STATUS_TAG_RE_GLOBAL.lastIndex = 0;
  const found: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = STATUS_TAG_RE_GLOBAL.exec(text)) !== null) {
    found.push(normalizeStatus(match[1] ?? match[2] ?? ""));
  }
  return found;
}

function stripStatusTags(text: string): string {
  STATUS_TAG_RE_GLOBAL.lastIndex = 0;
  HANDOFF_RE_GLOBAL.lastIndex = 0;
  return text
    .replace(STATUS_TAG_RE_GLOBAL, "")
    .replace(HANDOFF_RE_GLOBAL, "")
    .replace(/[ \t]+$/gm, "")
    .replace(/^\n+/, "")
    .trim();
}

interface SharedEntry {
  kind: "user" | "shared" | "passed" | "responded" | "passed-group";
  message?: Message;
  agent?: string;
  agents?: string[];
  groupKey?: string;
}

function entryKey(entry: SharedEntry): string | null {
  if (entry.kind === "passed-group") return entry.groupKey ?? null;
  return entry.message?.id ?? null;
}

function buildSharedEntries(messages: Message[]): SharedEntry[] {
  const entries: SharedEntry[] = [];

  for (const msg of messages) {
    if (msg.role === "user") {
      entries.push({ kind: "user", message: msg });
    } else if (msg.role === "system" || msg.role === "error" || msg.passed) {
      // Skip non-shareable entries in shared view.
    } else if (hasShareContent(msg.content)) {
      entries.push({ kind: "shared", message: msg, agent: msg.role });
    }
  }
  return entries;
}

function collapseConsecutivePasses(entries: SharedEntry[]): SharedEntry[] {
  const result: SharedEntry[] = [];
  let passRun: SharedEntry[] = [];

  const flushPasses = () => {
    if (passRun.length === 0) return;
    if (passRun.length === 1) {
      result.push(passRun[0]);
    } else {
      const agents = passRun.map((e) => e.agent!);
      const key = passRun.map((e) => e.message?.id ?? e.agent).join(",");
      result.push({ kind: "passed-group", agents, groupKey: key });
    }
    passRun = [];
  };

  for (const entry of entries) {
    if (entry.kind === "passed") {
      passRun.push(entry);
    } else {
      flushPasses();
      result.push(entry);
    }
  }
  flushPasses();
  return result;
}

function PassMarker({
  agents,
  stateAgents,
}: {
  agents: string[];
  stateAgents: AgentInfo[];
}) {
  return (
    <div className="flex items-center gap-3 py-1 opacity-45">
      <div className="flex-1 border-t border-dashed border-ui-dashed" />
      <div className="flex items-center gap-1.5">
        {agents.map((name, idx) => {
          const aType = resolveAgentInfo(name, stateAgents).type;
          const color = AGENT_COLORS[aType] ?? "text-ui-muted";
          return (
            <div
              key={`${name}-${idx}`}
              className="w-5 h-5 rounded-full border border-dashed border-ui-dashed flex items-center justify-center"
              title={name}
              aria-label={`${name} passed`}
              style={{ borderColor: `color-mix(in srgb, var(--agent-${aType}, #6B7280) 66%, transparent)` }}
            >
              <span className={`${color} opacity-70`}>
                <AgentIcon agent={aType} size={9} />
              </span>
            </div>
          );
        })}
      </div>
      <div className="flex-1 border-t border-dashed border-ui-dashed" />
    </div>
  );
}

interface Props {
  state: AppState;
  onExpandAgent?: (agent: string) => void;
  onStopAgent?: (agent: string) => void;
  onRemoveAgent?: (name: string) => void;
  onAddAgent?: (name: string, agentType: string, role: string) => void;
  density?: "compact" | "comfortable";
}

function resolveAgentInfo(agentName: string, agents: AgentInfo[]): { type: string; model?: string | null } {
  const info = agents.find(a => a.name === agentName);
  return { type: info?.type ?? agentName, model: info?.model ?? null };
}

function formatTime(msg: Message): string {
  if (!msg.created_at) return "";
  try {
    const d = new Date(msg.created_at);
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}

function readByForMessage(state: AppState, msg: Message): string[] {
  if (typeof msg.round_number !== "number") return [];
  const key = `${msg.role}:${msg.round_number}`;
  return state.deliveryAcks[key] ?? [];
}

export default function SharedChat({
  state,
  onExpandAgent,
  onStopAgent,
  onRemoveAgent,
  onAddAgent,
  density = "comfortable",
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [isNearBottom, setIsNearBottom] = useState(true);
  const [renderLimit, setRenderLimit] = useState(250);
  const [newEntryKeys, setNewEntryKeys] = useState<Set<string>>(new Set());
  const prevEntryKeysRef = useRef<string[]>([]);

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
  const lastActivityText = useMemo(() => {
    if (Object.values(state.agentStatuses).some((s) => s === "streaming")) {
      return "Last activity now";
    }
    let latestTs = 0;
    for (const msg of state.messages) {
      const ts = Date.parse(msg.created_at);
      if (Number.isFinite(ts) && ts > latestTs) latestTs = ts;
    }
    if (!latestTs) return "No activity yet";
    const diffSec = Math.max(0, Math.floor((Date.now() - latestTs) / 1000));
    if (diffSec < 60) return `Last activity ${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `Last activity ${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `Last activity ${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    return `Last activity ${diffDay}d ago`;
  }, [state.messages, state.agentStatuses]);

  const collapsedEntries = useMemo(() => collapseConsecutivePasses(entries), [entries]);
  const hiddenEntries = Math.max(0, collapsedEntries.length - renderLimit);
  const renderedEntries = hiddenEntries > 0 ? collapsedEntries.slice(-renderLimit) : collapsedEntries;

  useEffect(() => {
    const keys = collapsedEntries.map(entryKey).filter((k): k is string => Boolean(k));
    const previous = new Set(prevEntryKeysRef.current);
    const added = keys.filter((k) => !previous.has(k));
    prevEntryKeysRef.current = keys;
    if (added.length === 0) return;
    setNewEntryKeys(new Set(added));
    const timer = window.setTimeout(() => setNewEntryKeys(new Set()), 400);
    return () => window.clearTimeout(timer);
  }, [collapsedEntries]);

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
    <div className="relative flex-1 overflow-auto bg-ui-surface" ref={containerRef}>
      {/* Filter bar */}
      <div className="sticky top-0 z-10 h-11 border-b border-ui-soft px-4 md:px-6" style={{ background: "var(--bg-surface)" }}>
        <div className="h-full flex items-center gap-2">
          <div className="min-w-0 flex-1">
            <AgentStatusBar
              state={state}
              onStopAgent={onStopAgent}
              onRemoveAgent={onRemoveAgent}
              onAddAgent={onAddAgent}
              className="h-full"
            />
          </div>
          <span className="text-[11px] font-mono text-ui-faint shrink-0 hidden md:inline">
            {entries.length} events · {lastActivityText}
          </span>
        </div>
      </div>

      <div className={`${density === "compact" ? "space-y-2" : "space-y-3"} px-3 md:px-5 py-3`}>
        {/* Show older — dashed button in message list */}
        {hiddenEntries > 0 && (
          <button
            onClick={() => setRenderLimit((n) => n + 250)}
            className="w-full py-2.5 rounded-[10px] text-[12px] font-mono text-ui-faint transition-colors cursor-pointer hover:text-ui-muted"
            style={{ border: '1px dashed var(--border-dashed)', background: 'transparent' }}
          >
            &uarr; Show {hiddenEntries} older events
          </button>
        )}

        {renderedEntries.map((entry, i) => {
          const key = entryKey(entry);
          const animateClass = key && newEntryKeys.has(key) ? "animate-slide-up" : "";
          const animateStyle = animateClass
            ? { animationDelay: `${Math.min(i * 0.04, 0.8)}s`, animationFillMode: "backwards" as const }
            : undefined;

          if (entry.kind === "user" && entry.message) {
            const time = formatTime(entry.message);
            return (
              <div
                key={entry.message.id}
                className={animateClass}
                style={animateStyle}
              >
                <div className="chat-bubble-agent relative overflow-hidden mx-2 md:mx-3">
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
                    <div className="ml-auto flex items-center gap-1.5 shrink-0">
                      {time && <span className="text-[10px] text-ui-subtle">{time}</span>}
                    </div>
                  </div>
                  <div className="pt-0">
                    <p className="text-sm text-ui-strong whitespace-pre-wrap break-words">{entry.message.content}</p>
                  </div>
                </div>
              </div>
            );
          }

          if (entry.kind === "passed-group" && entry.agents) {
            return (
              <div key={entry.groupKey}>
                <PassMarker agents={entry.agents} stateAgents={state.agents} />
              </div>
            );
          }

          if (entry.kind === "passed" && entry.message && entry.agent) {
            return (
              <div key={entry.message.id}>
                <PassMarker agents={[entry.agent]} stateAgents={state.agents} />
              </div>
            );
          }

          if (entry.kind === "shared" && entry.message && entry.agent) {
            const info = resolveAgentInfo(entry.agent, state.agents);
            const aType = info.type;
            const shareContent = extractShareOnly(entry.message.content);
            const statuses = extractStatuses(shareContent);
            const handoffs = extractHandoffs(shareContent);
            const markdownContent = stripStatusTags(shareContent);
            const time = formatTime(entry.message);
            const readBy = readByForMessage(state, entry.message);
            const color = AGENT_COLORS[aType] ?? "text-ui-muted";
            const avatarClass = AGENT_AVATAR_CLASSES[aType] ?? "";
            const modelText = info.model ?? "unknown";
            const railColor = aType === "claude"
              ? "var(--agent-claude)"
              : aType === "codex"
                ? "var(--agent-codex)"
                : aType === "kimi"
                  ? "var(--agent-kimi)"
                  : "var(--border-active)";
            return (
              <div
                key={entry.message.id}
                className={animateClass}
                style={animateStyle}
              >
                <Card className="mx-2 md:mx-3 share-card" style={{ ["--share-rail-color" as string]: railColor }}>
                  <CardHeader className="flex items-center gap-1.5 px-4 py-3">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <div className={`chat-avatar ${avatarClass} ${color}`}>
                        <AgentIcon agent={aType} size={14} />
                      </div>
                      <span className={`text-[13px] font-semibold capitalize ${color}`}>{entry.agent}</span>
                      <span className="text-[10px] text-ui-faint shrink-0" style={{ opacity: 0.7 }}>·</span>
                      <span className="text-[10px] text-ui-faint capitalize shrink-0" style={{ opacity: 0.7 }}>{aType}</span>
                      <span className="text-[10px] text-ui-faint shrink-0" style={{ opacity: 0.7 }}>·</span>
                      <span className="text-[10px] text-ui-faint shrink-0" style={{ opacity: 0.7 }}>{modelText}</span>
                    </div>
                    <div className="ml-auto flex items-center gap-1.5 shrink-0">
                      {time && <span className="text-[10px] text-ui-subtle">{time}</span>}
                      <span className="badge badge-shared text-[9px] py-0">shared</span>
                    </div>
                  </CardHeader>
                  <CardContent className="share-card-content px-4 py-3 text-share-body">
                    <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui-muted text-[12px] leading-[1.5] break-words">
                      {markdownContent}
                    </StyledMarkdown>
                  </CardContent>
                  {(statuses.length > 0 || handoffs.length > 0 || readBy.length > 0) && (
                    <CardFooter className="share-card-footer px-4 py-2 overflow-x-auto">
                      <div className="flex flex-nowrap gap-1.5 whitespace-nowrap pb-0.5">
                        {statuses.map((status, sIdx) => (
                          <span key={`${status}-${sIdx}`} className={`badge share-status-badge shrink-0 ${STATUS_COLORS[status] || DEFAULT_STATUS_COLOR}`}>
                            {status}
                          </span>
                        ))}
                        {handoffs.map((agent, hIdx) => (
                          <span key={`handoff-${hIdx}`} className="badge share-status-badge badge-violet shrink-0">
                            → {agent}
                          </span>
                        ))}
                        {readBy.length > 0 && (
                          <span className="inline-flex items-center gap-1.5 shrink-0">
                            <span className="text-[10px] text-ui-subtle">read by</span>
                            <span className="inline-flex items-center -space-x-1">
                              {readBy.map((reader) => {
                                const readerInfo = resolveAgentInfo(reader, state.agents);
                                const readerType = readerInfo.type;
                                const readerColor = AGENT_COLORS[readerType] ?? "text-ui-muted";
                                const readerAvatar = AGENT_AVATAR_CLASSES[readerType] ?? "";
                                return (
                                  <span
                                    key={`read-by-${entry.message!.id}-${reader}`}
                                    className={`chat-avatar ${readerAvatar} ${readerColor} border-ui-soft w-4 h-4`}
                                    title={reader}
                                  >
                                    <AgentIcon agent={readerType} size={9} />
                                  </span>
                                );
                              })}
                            </span>
                          </span>
                        )}
                      </div>
                    </CardFooter>
                  )}
                </Card>
              </div>
            );
          }

          if (entry.kind === "responded" && entry.message && entry.agent) {
            const info = resolveAgentInfo(entry.agent, state.agents);
            const aType = info.type;
            const time = formatTime(entry.message);
            return (
              <div
                key={entry.message.id}
                className={animateClass}
                style={animateStyle}
              >
                <AgentMessageCard
                  agentName={entry.agent}
                  agentType={aType}
                  modelLabel={info.model ?? undefined}
                  className="mx-2 md:mx-3"
                  onAgentClick={() => onExpandAgent?.(entry.agent!)}
                  headerRight={(
                    <>
                      {time && <span className="text-[10px] font-mono text-ui-subtle">{time}</span>}
                      <span className="badge badge-responded text-[9px] py-0">responded</span>
                    </>
                  )}
                >
                  {entry.message.content.length > 1600 ? (
                    <details className="text-xs">
                      <summary className="cursor-pointer text-ui-subtle hover:text-ui mb-1">Show long message</summary>
                      <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui text-[13.5px] leading-[1.7] break-words">
                        {entry.message.content}
                      </StyledMarkdown>
                    </details>
                  ) : (
                    <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui text-[13.5px] leading-[1.7] break-words">
                      {entry.message.content}
                    </StyledMarkdown>
                  )}
                </AgentMessageCard>
              </div>
            );
          }

          return null;
        })}

        {activeSharedStreams.map(({ agent, content }) => {
          const info = resolveAgentInfo(agent, state.agents);
          const aType = info.type;
          const statuses = extractStatuses(content);
          const handoffs = extractHandoffs(content);
          const markdownContent = stripStatusTags(content);
          const color = AGENT_COLORS[aType] ?? "text-ui-muted";
          const avatarClass = AGENT_AVATAR_CLASSES[aType] ?? "";
          const modelText = info.model ?? "unknown";
          const railColor = aType === "claude"
            ? "var(--agent-claude)"
            : aType === "codex"
              ? "var(--agent-codex)"
              : aType === "kimi"
                ? "var(--agent-kimi)"
                : "var(--border-active)";
          return (
            <div key={`stream-shared-${agent}`}>
              <Card className="mx-2 md:mx-3 share-card" style={{ ["--share-rail-color" as string]: railColor }}>
                <CardHeader className="flex items-center gap-1.5 px-4 py-3">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <div className={`chat-avatar ${avatarClass} ${color}`}>
                      <AgentIcon agent={aType} size={14} />
                    </div>
                    <span className={`text-[13px] font-semibold capitalize ${color}`}>{agent}</span>
                    <span className="text-[10px] text-ui-faint shrink-0" style={{ opacity: 0.7 }}>·</span>
                    <span className="text-[10px] text-ui-faint capitalize shrink-0" style={{ opacity: 0.7 }}>{aType}</span>
                    <span className="text-[10px] text-ui-faint shrink-0" style={{ opacity: 0.7 }}>·</span>
                    <span className="text-[10px] text-ui-faint shrink-0" style={{ opacity: 0.7 }}>{modelText}</span>
                  </div>
                  <div className="ml-auto flex items-center gap-1.5 shrink-0">
                    <span className="w-1.5 h-1.5 rounded-full dot-status-streaming animate-pulse" />
                  </div>
                </CardHeader>
                <CardContent className="share-card-content px-4 py-3 text-share-body">
                  <StyledMarkdown className="prose prose-invert prose-sm max-w-none text-ui-muted text-[12px] leading-[1.5] break-words">
                    {markdownContent}
                  </StyledMarkdown>
                </CardContent>
                {(statuses.length > 0 || handoffs.length > 0) && (
                  <CardFooter className="share-card-footer px-4 py-2 overflow-x-auto">
                    <div className="flex flex-nowrap gap-1.5 whitespace-nowrap pb-0.5">
                      {statuses.map((status, sIdx) => (
                        <span key={`${status}-${sIdx}`} className={`badge share-status-badge shrink-0 ${STATUS_COLORS[status] || DEFAULT_STATUS_COLOR}`}>
                          {status}
                        </span>
                      ))}
                      {handoffs.map((agent, hIdx) => (
                        <span key={`handoff-${hIdx}`} className="badge share-status-badge badge-violet shrink-0">
                          → {agent}
                        </span>
                      ))}
                    </div>
                  </CardFooter>
                )}
              </Card>
            </div>
          );
        })}

        <div ref={bottomRef} />
      </div>
      {!isNearBottom && (
        <Button
          onClick={scrollToBottom}
          variant="secondary"
          size="sm"
          className="sticky bottom-3 left-1/2 -translate-x-1/2 w-8 h-8 !p-0 rounded-full bg-ui-elevated border-ui-strong text-ui-muted hover:bg-ui-soft hover:text-ui"
          title="Jump to bottom"
          icon={<ArrowDown size={14} />}
        >
          <span className="sr-only">Jump to bottom</span>
        </Button>
      )}
    </div>
  );
}
