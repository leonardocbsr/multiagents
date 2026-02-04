export interface AgentInfo {
  name: string;
  type: string;  // "claude" | "codex" | "kimi"
  role: string;
}

export interface Settings {
  [key: string]: unknown;
  "agents.enabled": string[];
  "agents.claude.model": string | null;
  "agents.claude.system_prompt": string | null;
  "agents.codex.model": string | null;
  "agents.codex.system_prompt": string | null;
  "agents.kimi.model": string | null;
  "agents.kimi.system_prompt": string | null;
  "timeouts.idle": number;
  "timeouts.parse": number;
  "timeouts.send": number;
  "timeouts.hard": number;
  "memory.model": string;
  "server.warmup_ttl": number;
  "server.max_events": number;
}

export function normalizeAgents(agents: (string | AgentInfo)[]): AgentInfo[] {
  return agents.map(a =>
    typeof a === "string" ? { name: a, type: a, role: "" } : a
  );
}

export interface Message {
  id: string;
  role: string;
  content: string;
  stderr?: string;
  round_number: number | null;
  passed: boolean;
  created_at: string;
  streaming?: boolean;
  latency_ms?: number;
  stream_chunks?: number;
  interrupted?: boolean;
}

// === Kanban Card Types ===

export type CardStatus = "backlog" | "coordinating" | "planning" | "reviewing" | "implementing" | "done";

export interface CardPhaseEntry {
  phase: CardStatus;
  agent: string;
  content: string;
  timestamp: string;
}

export interface Card {
  id: string;
  title: string;
  description: string;
  status: CardStatus;
  planner: string;
  implementer: string;
  reviewer: string;
  coordinator: string;
  coordination_stage: string;
  previous_phase: CardStatus | null;
  history: CardPhaseEntry[];
  created_at: string;
}

export interface AppState {
  connected: boolean;
  reconnecting: boolean;
  reconnectAttempt: number;
  reconnectInMs: number | null;
  reconnectExhausted: boolean;
  sessionId: string | null;
  title: string;
  agents: AgentInfo[];
  messages: Message[];
  agentStreams: Record<string, string>;
  agentStreamCounts: Record<string, number>;
  agentStatuses: Record<string, "idle" | "streaming" | "done" | "failed">;
  pendingAgentStderr: Record<string, string>;
  isRunning: boolean;
  isPaused: boolean;
  currentRound: number;
  cards: Card[];
  agentPrompts: Record<string, Record<number, Record<string, string>>>;
}

export interface InFlightState {
  round: number;
  agent_streams: Record<string, string>;
  agent_statuses: Record<string, "idle" | "streaming" | "done" | "failed">;
}

type ServerEnvelope = { event_id?: number };

export type ServerMessage = ServerEnvelope & (
  | { type: "connected"; agents: (string | AgentInfo)[] }
  | { type: "session_created"; session_id: string; agents: (string | AgentInfo)[] }
  | { type: "session_joined"; session_id: string; title: string; agents: (string | AgentInfo)[]; messages: Message[]; is_running: boolean; in_flight?: InFlightState | null; cards?: Card[] }
  | { type: "agent_added"; name: string; agent_type: string; role: string }
  | { type: "agent_removed"; name: string }
  | { type: "title_changed"; title: string }
  | { type: "user_message"; text: string }
  | { type: "round_started"; round: number; agents: string[] }
  | { type: "agent_stream"; agent: string; chunk: string }
  | { type: "agent_stderr"; agent: string; text: string }
  | { type: "agent_completed"; agent: string; text: string; passed: boolean; success: boolean; latency_ms: number; stopped?: boolean }
  | { type: "agent_notice"; agent: string; message: string }
  | { type: "round_ended"; round: number; all_passed: boolean }
  | { type: "paused"; round: number }
  | { type: "discussion_ended"; reason: string }
  | { type: "error"; message: string }
  | { type: "card_created"; card: Card }
  | { type: "card_updated"; card: Card }
  | { type: "card_deleted"; card_id: string }
  | { type: "card_phase_started"; card_id: string; phase: CardStatus; agent: string }
  | { type: "card_phase_completed"; card_id: string; phase: CardStatus; agent: string; approved?: boolean; next_phase?: CardStatus }
  | { type: "agent_interrupted"; agent: string; round: number; partial_text: string }
  | { type: "dm_sent"; agent: string; text: string; round: number }
  | { type: "agent_prompt"; agent: string; round: number; sections: Record<string, string> }
);

export type ClientMessage =
  | { type: "create_session"; working_dir?: string; agents?: AgentInfo[]; config?: Record<string, unknown> }
  | { type: "join_session"; session_id: string; last_event_id?: number }
  | { type: "add_agent"; name: string; agent_type: string; role: string }
  | { type: "remove_agent"; name: string }
  | { type: "message"; text: string }
  | { type: "stop_agent"; agent: string }
  | { type: "stop_round" }
  | { type: "resume" }
  | { type: "cancel" }
  | { type: "ack"; event_id: number }
  | { type: "metric"; name: string; value: number; session_id?: string }
  | { type: "card_create"; title: string; description: string; planner?: string; implementer?: string; reviewer?: string; coordinator?: string }
  | { type: "card_update"; card_id: string; title?: string; description?: string; planner?: string; implementer?: string; reviewer?: string; coordinator?: string }
  | { type: "card_start"; card_id: string }
  | { type: "card_delegate"; card_id: string }
  | { type: "card_done"; card_id: string }
  | { type: "card_delete"; card_id: string }
  | { type: "direct_message"; agent: string; text: string };

// === Agent Coordination Patterns ===

export interface CoordinationPatterns {
  mentions: string[];      // @AgentName
  agreements: string[];    // +1 AgentName  
  handoffs: Handoff[];     // [HANDOFF:Agent]
  statuses: string[];      // [EXPLORE] or [STATUS: ...]
}

export interface Handoff {
  agent: string;
  context: string;
}

// Coordination pattern regexes — must match backend in src/chat/router.py.
// Canonical test cases: tests/fixtures/coordination_patterns.json
// Note: normalizeStatus() uppercases for display; Python preserves original case.
const MENTION_RE = /(?<!\/)@(\w+)/g;
const AGREEMENT_RE = /\+1\s+(\w+)/gi;
const HANDOFF_RE = /\[HANDOFF:(\w+)\]/gi;
const STATUS_RE = /(?:\[(EXPLORE|DECISION|BLOCKED|DONE|TODO|QUESTION)\]|\[STATUS:\s*([^\]\n]+)\])/gi;
const SHARE_TAG_RE = /<Share>(.*?)<\/Share>/gis;

function normalizeStatus(status: string): string {
  return status.trim().replace(/\s+/g, " ").toUpperCase();
}

function extractShareable(text: string): { hasShareTags: boolean; content: string } {
  SHARE_TAG_RE.lastIndex = 0;
  const matches = Array.from(text.matchAll(SHARE_TAG_RE));
  if (matches.length === 0) return { hasShareTags: false, content: "" };
  const content = matches
    .map(match => match[1].trim())
    .filter(Boolean)
    .join("\n\n");
  return { hasShareTags: true, content };
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const key = value.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(value);
  }
  return result;
}

function buildAgentLookup(allowedAgents?: string[]): Map<string, string> | null {
  if (!allowedAgents || allowedAgents.length === 0) return null;
  return new Map(allowedAgents.map(agent => [agent.toLowerCase(), agent]));
}

function normalizeAgentName(name: string, lookup: Map<string, string> | null): string | null {
  if (!lookup) return name;
  return lookup.get(name.toLowerCase()) ?? null;
}

interface CoordinationParseOptions {
  allowedAgents?: string[];
}

export function parseCoordinationPatterns(text: string, options: CoordinationParseOptions = {}): CoordinationPatterns {
  const { hasShareTags, content } = extractShareable(text);
  const source = hasShareTags ? content : text;
  if (!source.trim()) return { mentions: [], agreements: [], handoffs: [], statuses: [] };
  const agentLookup = buildAgentLookup(options.allowedAgents);

  const mentionsRaw = Array.from(source.matchAll(MENTION_RE)).map(m => m[1]);
  const mentions = uniqueStrings(
    mentionsRaw
      .map(name => normalizeAgentName(name, agentLookup))
      .filter((name): name is string => Boolean(name))
  );
  
  // Other patterns can be extracted from the full text
  const agreementsRaw = Array.from(source.matchAll(AGREEMENT_RE)).map(m => m[1]);
  const agreements = uniqueStrings(
    agreementsRaw
      .map(name => normalizeAgentName(name, agentLookup))
      .filter((name): name is string => Boolean(name))
  );
  const statuses = uniqueStrings(
    Array.from(source.matchAll(STATUS_RE))
      .map(m => normalizeStatus(m[1] ?? m[2] ?? ""))
      .filter(Boolean)
  );
  
  const handoffs: Handoff[] = [];
  let match;
  HANDOFF_RE.lastIndex = 0;
  while ((match = HANDOFF_RE.exec(source)) !== null) {
    const normalized = normalizeAgentName(match[1], agentLookup);
    if (!normalized) continue;
    const after = source.slice(match.index + match[0].length).trim();
    const context = after.split('.')[0].slice(0, 100).trim();
    if (!handoffs.some(entry => entry.agent.toLowerCase() === normalized.toLowerCase())) {
      handoffs.push({ agent: normalized, context });
    }
  }
  
  return { mentions, agreements, handoffs, statuses };
}
