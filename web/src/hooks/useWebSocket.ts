import { useCallback, useEffect, useReducer, useRef } from "react";
import type { AgentInfo, AppState, ClientMessage, Message, ServerMessage } from "../types";
import { normalizeAgents } from "../types";

const INITIAL_STATE: AppState = {
  connected: false,
  reconnecting: false,
  reconnectAttempt: 0,
  reconnectInMs: null,
  reconnectExhausted: false,
  sessionId: null,
  title: "",
  agents: [],
  messages: [],
  agentStreams: {},
  agentStreamCounts: {},
  agentStatuses: {},
  pendingAgentStderr: {},
  isRunning: false,
  isPaused: false,
  currentRound: 0,
  cards: [],
  deliveryAcks: {},
  agentPrompts: {},
  pendingPermissions: [],
};

const BASE_RECONNECT_DELAY_MS = 500;
const MAX_RECONNECT_DELAY_MS = 30_000;
const MAX_RECONNECT_ATTEMPTS = 10;
const RECONNECT_JITTER_RATIO = 0.2;

function getWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

type Action =
  | { type: "reset" }
  | { type: "server_message"; msg: ServerMessage }
  | { type: "set_running"; running: boolean }
  | { type: "disconnected" }
  | { type: "reconnect_scheduled"; attempt: number; delayMs: number }
  | { type: "reconnect_cleared" }
  | { type: "reconnect_exhausted" }
  | { type: "reconnect_tick"; remainingMs: number }
  | { type: "remove_permission"; requestId: string; agent?: string };

function reducer(state: AppState, action: Action): AppState {
  if (action.type === "reset") return { ...INITIAL_STATE };
  if (action.type === "set_running") return { ...state, isRunning: action.running };
  if (action.type === "disconnected") {
    return { ...state, connected: false };
  }
  if (action.type === "reconnect_scheduled") {
    return {
      ...state,
      connected: false,
      reconnecting: true,
      reconnectAttempt: action.attempt,
      reconnectInMs: action.delayMs,
    };
  }
  if (action.type === "reconnect_cleared") {
    return { ...state, reconnecting: false, reconnectAttempt: 0, reconnectInMs: null, reconnectExhausted: false };
  }
  if (action.type === "reconnect_exhausted") {
    return { ...state, reconnecting: false, reconnectExhausted: true, reconnectInMs: null };
  }
  if (action.type === "reconnect_tick") {
    return { ...state, reconnectInMs: action.remainingMs };
  }
  if (action.type === "remove_permission") {
    return {
      ...state,
      pendingPermissions: state.pendingPermissions.filter((p) => {
        if (action.agent) {
          return !(p.request_id === action.requestId && p.agent === action.agent);
        }
        return p.request_id !== action.requestId;
      }),
    };
  }

  const msg = action.msg;

  switch (msg.type) {
    case "connected":
      return { ...state, connected: true, agents: normalizeAgents(msg.agents), reconnecting: false, reconnectAttempt: 0, reconnectInMs: null };

    case "session_created":
      return {
        ...state,
        sessionId: msg.session_id,
        agents: normalizeAgents(msg.agents),
        messages: [],
        agentStreams: {},
        agentStreamCounts: {},
        agentStatuses: {},
        pendingAgentStderr: {},
        cards: [],
        deliveryAcks: {},
        agentPrompts: {},
        pendingPermissions: [],
        reconnecting: false,
        reconnectAttempt: 0,
        reconnectInMs: null,
      };

    case "session_joined":
      if (msg.is_running && msg.in_flight) {
        return {
          ...state,
          sessionId: msg.session_id,
          title: msg.title,
          agents: normalizeAgents(msg.agents),
          messages: msg.messages,
          isRunning: msg.is_running,
          currentRound: msg.in_flight.round,
          agentStreams: msg.in_flight.agent_streams,
          agentStreamCounts: {},
          agentStatuses: msg.in_flight.agent_statuses,
          pendingAgentStderr: {},
          pendingPermissions: [],
          cards: msg.cards ?? [],
          deliveryAcks: {},
          agentPrompts: {},
          reconnecting: false,
          reconnectAttempt: 0,
          reconnectInMs: null,
        };
      }
      return {
        ...state,
        sessionId: msg.session_id,
        title: msg.title,
        agents: normalizeAgents(msg.agents),
        messages: msg.messages,
        isRunning: msg.is_running,
        currentRound: 0,
        agentStreams: {},
        agentStreamCounts: {},
        agentStatuses: {},
        pendingAgentStderr: {},
        pendingPermissions: [],
        cards: msg.cards ?? [],
        deliveryAcks: {},
        agentPrompts: {},
        reconnecting: false,
        reconnectAttempt: 0,
        reconnectInMs: null,
      };

    case "title_changed":
      return { ...state, title: msg.title };

    case "user_message": {
      const userMsg: Message = {
        id: crypto.randomUUID(), role: "user", content: msg.text,
        round_number: null, passed: false, created_at: msg.created_at ?? new Date().toISOString(),
      };
      return { ...state, messages: [...state.messages, userMsg] };
    }

    case "round_started": {
      const statuses: Record<string, "streaming"> = {};
      for (const a of msg.agents) statuses[a] = "streaming";
      return {
        ...state, isRunning: true, isPaused: false, currentRound: msg.round,
        agentStreams: Object.fromEntries(msg.agents.map(a => [a, ""])),
        agentStreamCounts: Object.fromEntries(msg.agents.map(a => [a, 0])),
        agentStatuses: statuses,
        pendingAgentStderr: {},
      };
    }

    case "agent_stream":
      return {
        ...state,
        agentStreams: { ...state.agentStreams, [msg.agent]: (state.agentStreams[msg.agent] ?? "") + msg.chunk },
        agentStreamCounts: { ...state.agentStreamCounts, [msg.agent]: (state.agentStreamCounts[msg.agent] ?? 0) + 1 },
        ...(state.agentStatuses[msg.agent] !== "streaming" ? { agentStatuses: { ...state.agentStatuses, [msg.agent]: "streaming" } } : {}),
      };

    case "agent_stderr": {
      const round = state.currentRound || 0;
      const key = `${msg.agent}:${round}`;
      return {
        ...state,
        pendingAgentStderr: { ...state.pendingAgentStderr, [key]: msg.text },
      };
    }

    case "agent_notice": {
      const noticeMsg: Message = {
        id: crypto.randomUUID(), role: "system", content: `[${msg.agent}] ${msg.message}`,
        round_number: state.currentRound || null, passed: false, created_at: msg.created_at ?? new Date().toISOString(),
      };
      return { ...state, messages: [...state.messages, noticeMsg] };
    }

    case "agent_completed": {
      // Prefer the accumulated stream content (includes tool badges and thinking
      // blocks) over the server's clean text from _parse_output.
      const streamed = state.agentStreams[msg.agent] ?? "";
      const content = streamed.trim() || msg.text;
      const stderrKey = `${msg.agent}:${state.currentRound || 0}`;
      const stderr = state.pendingAgentStderr[stderrKey];
      const nextPending = { ...state.pendingAgentStderr };
      if (stderr) delete nextPending[stderrKey];
      const agentMsg: Message = {
        id: crypto.randomUUID(), role: msg.agent, content,
        round_number: state.currentRound, passed: msg.passed, created_at: msg.created_at ?? new Date().toISOString(),
        latency_ms: msg.latency_ms,
        stream_chunks: state.agentStreamCounts[msg.agent] ?? 0,
        stderr,
      };
      return {
        ...state, messages: [...state.messages, agentMsg],
        agentStatuses: { ...state.agentStatuses, [msg.agent]: msg.success ? "done" : "failed" },
        agentStreams: { ...state.agentStreams, [msg.agent]: "" },
        agentStreamCounts: { ...state.agentStreamCounts, [msg.agent]: 0 },
        pendingAgentStderr: nextPending,
      };
    }

    case "round_ended":
      return state;

    case "paused":
      return { ...state, isPaused: true };

    case "discussion_ended":
      return { ...state, isRunning: false, isPaused: false, currentRound: 0, agentStreams: {}, agentStreamCounts: {}, agentStatuses: {}, pendingPermissions: [] };

    case "error":
      return state;

    case "card_created":
      return { ...state, cards: [...state.cards, msg.card] };

    case "card_updated":
      return { ...state, cards: state.cards.map(c => c.id === msg.card.id ? msg.card : c) };

    case "card_deleted":
      return { ...state, cards: state.cards.filter(c => c.id !== msg.card_id) };

    case "card_phase_started":
      return { ...state, cards: state.cards.map(c => c.id === msg.card_id ? { ...c, status: msg.phase } : c) };

    case "card_phase_completed":
      return { ...state, cards: state.cards.map(c => c.id === msg.card_id ? { ...c, status: msg.next_phase ?? c.status } : c) };

    case "agent_interrupted": {
      const streamed = state.agentStreams[msg.agent] ?? "";
      const content = streamed.trim() || msg.partial_text;
      const interruptedMsg: Message = {
        id: crypto.randomUUID(),
        role: msg.agent,
        content,
        round_number: msg.round,
        passed: false,
        created_at: msg.created_at ?? new Date().toISOString(),
        interrupted: true,
      };
      return {
        ...state,
        messages: [...state.messages, interruptedMsg],
        agentStreams: { ...state.agentStreams, [msg.agent]: "" },
        agentStreamCounts: { ...state.agentStreamCounts, [msg.agent]: 0 },
        agentStatuses: { ...state.agentStatuses, [msg.agent]: "streaming" },
      };
    }

    case "dm_sent": {
      const dmMsg: Message = {
        id: crypto.randomUUID(),
        role: `dm:${msg.agent}`,
        content: msg.text,
        round_number: msg.round,
        passed: false,
        created_at: msg.created_at ?? new Date().toISOString(),
      };
      return { ...state, messages: [...state.messages, dmMsg] };
    }

    case "agent_prompt": {
      const prev = state.agentPrompts[msg.agent] ?? {};
      return {
        ...state,
        agentPrompts: {
          ...state.agentPrompts,
          [msg.agent]: {
            ...prev,
            [msg.round]: msg.sections,
          },
        },
      };
    }

    case "delivery_acked": {
      if (typeof msg.round !== "number") return state;
      const key = `${msg.sender}:${msg.round}`;
      const existing = state.deliveryAcks[key] ?? [];
      if (existing.includes(msg.recipient)) return state;
      return {
        ...state,
        deliveryAcks: {
          ...state.deliveryAcks,
          [key]: [...existing, msg.recipient],
        },
      };
    }

    case "permission_request":
      if (state.pendingPermissions.some((p) => p.request_id === msg.request_id && p.agent === msg.agent)) {
        return state;
      }
      return {
        ...state,
        pendingPermissions: [...state.pendingPermissions, {
          request_id: msg.request_id,
          agent: msg.agent,
          tool_name: msg.tool_name,
          tool_input: msg.tool_input,
          description: msg.description,
          round: msg.round,
          created_at: msg.created_at ?? new Date().toISOString(),
        }],
      };

    case "agent_added": {
      const newAgent: AgentInfo = { name: msg.name, type: msg.agent_type, role: msg.role, model: msg.model ?? null };
      return {
        ...state,
        agents: [...state.agents, newAgent],
        agentStatuses: { ...state.agentStatuses, [msg.name]: state.isRunning ? "streaming" : "idle" },
        agentStreams: { ...state.agentStreams, [msg.name]: "" },
        agentStreamCounts: { ...state.agentStreamCounts, [msg.name]: 0 },
      };
    }

    case "agent_removed": {
      const { [msg.name]: _stream, ...restStreams } = state.agentStreams;
      const { [msg.name]: _status, ...restStatuses } = state.agentStatuses;
      const { [msg.name]: _count, ...restCounts } = state.agentStreamCounts;
      const nextAcks: Record<string, string[]> = {};
      for (const [k, readers] of Object.entries(state.deliveryAcks)) {
        const filtered = readers.filter((name) => name !== msg.name);
        if (filtered.length > 0) nextAcks[k] = filtered;
      }
      return {
        ...state,
        agents: state.agents.filter(a => a.name !== msg.name),
        agentStreams: restStreams,
        agentStatuses: restStatuses,
        agentStreamCounts: restCounts,
        deliveryAcks: nextAcks,
      };
    }

    default:
      return state;
  }
}

export function useWebSocket(onSendFailure?: (msgType: string) => void) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const countdownTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const reconnectAttempts = useRef(0);
  const reconnectDeadline = useRef(0);
  const sessionIdRef = useRef<string | null>(null);
  const lastEventIdRef = useRef(0);
  const lastAckedRef = useRef(0);
  const ackTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const manualDisconnect = useRef(false);
  const pendingReplay = useRef(false);
  const onSendFailureRef = useRef(onSendFailure);
  onSendFailureRef.current = onSendFailure;

  useEffect(() => {
    sessionIdRef.current = state.sessionId;
  }, [state.sessionId]);

  useEffect(() => {
    let alive = true;
    const scheduleReconnect = () => {
      if (!alive) return;
      if (reconnectAttempts.current >= MAX_RECONNECT_ATTEMPTS) {
        dispatch({ type: "reconnect_exhausted" });
        return;
      }
      const attempt = reconnectAttempts.current + 1;
      const delay = Math.min(MAX_RECONNECT_DELAY_MS, BASE_RECONNECT_DELAY_MS * 2 ** (attempt - 1));
      const jitter = delay * RECONNECT_JITTER_RATIO * Math.random();
      reconnectAttempts.current = attempt;
      const finalDelay = delay + jitter;
      dispatch({ type: "reconnect_scheduled", attempt, delayMs: finalDelay });
      reconnectDeadline.current = Date.now() + finalDelay;
      clearInterval(countdownTimer.current);
      countdownTimer.current = setInterval(() => {
        const remaining = Math.max(0, reconnectDeadline.current - Date.now());
        dispatch({ type: "reconnect_tick", remainingMs: remaining });
      }, 1000);
      reconnectTimer.current = setTimeout(() => {
        clearInterval(countdownTimer.current);
        connect();
      }, finalDelay);
    };

    function connect() {
      if (!alive) return;
      const existing = wsRef.current;
      if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
        return;
      }
      const ws = new WebSocket(getWsUrl());
      ws.onopen = () => {
        const attempts = reconnectAttempts.current;
        reconnectAttempts.current = 0;
        clearInterval(countdownTimer.current);
        dispatch({ type: "reconnect_cleared" });
        const sid = sessionIdRef.current;
        if (attempts > 0) {
          ws.send(JSON.stringify({ type: "metric", name: "reconnect_attempts", value: attempts, session_id: sid ?? undefined }));
        }
        if (sid) {
          const lastEventId = lastEventIdRef.current;
          if (lastEventId > 0) {
            pendingReplay.current = true;
          }
          ws.send(JSON.stringify({ type: "join_session", session_id: sid, last_event_id: lastEventId }));
        }
      };
      ws.onmessage = (event) => {
        if (!alive) return;
        let msg: ServerMessage = JSON.parse(event.data);
        if (msg.type === "session_joined" && pendingReplay.current) {
          msg = { ...msg, in_flight: null };
          pendingReplay.current = false;
        }
        dispatch({ type: "server_message", msg });
        if (msg.type === "session_created" || msg.type === "session_joined") {
          lastEventIdRef.current = 0;
          lastAckedRef.current = 0;
        }
        if (typeof msg.event_id === "number") {
          lastEventIdRef.current = Math.max(lastEventIdRef.current, msg.event_id);
          if (!ackTimer.current) {
            ackTimer.current = setTimeout(() => {
              ackTimer.current = undefined;
              if (!sessionIdRef.current) return;
              if (lastEventIdRef.current <= lastAckedRef.current) return;
              const ws = wsRef.current;
              if (!ws || ws.readyState !== WebSocket.OPEN) return;
              ws.send(JSON.stringify({ type: "ack", event_id: lastEventIdRef.current }));
              lastAckedRef.current = lastEventIdRef.current;
            }, 250);
          }
        }
      };
      ws.onerror = () => {
        if (!alive) return;
        ws.close();
      };
      ws.onclose = () => {
        if (!alive) return;
        if (manualDisconnect.current) {
          manualDisconnect.current = false;
          return;
        }
        dispatch({ type: "disconnected" });
        wsRef.current = null;
        clearTimeout(reconnectTimer.current);
        scheduleReconnect();
      };
      wsRef.current = ws;
    }
    connect();
    return () => {
      alive = false;
      reconnectAttempts.current = 0;
      clearTimeout(reconnectTimer.current);
      clearInterval(countdownTimer.current);
      clearTimeout(ackTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, []);

  const send = useCallback((msg: ClientMessage): boolean => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      onSendFailureRef.current?.(msg.type);
      return false;
    }
    ws.send(JSON.stringify(msg));
    return true;
  }, []);

  const sendMessage = useCallback((text: string): boolean => { return send({ type: "message", text }); }, [send]);
  const createSession = useCallback((workingDir?: string, agents?: AgentInfo[], config?: Record<string, unknown>) => { send({ type: "create_session", working_dir: workingDir, agents, config }); }, [send]);
  const joinSession = useCallback((sessionId: string) => {
    const lastEventId = lastEventIdRef.current;
    if (lastEventId > 0) {
      pendingReplay.current = true;
    }
    send({ type: "join_session", session_id: sessionId, last_event_id: lastEventId });
  }, [send]);
  const stopAgent = useCallback((agent: string) => send({ type: "stop_agent", agent }), [send]);
  const stopRound = useCallback(() => send({ type: "stop_round" }), [send]);
  const resume = useCallback(() => send({ type: "resume" }), [send]);
  const disconnect = useCallback(() => {
    clearTimeout(reconnectTimer.current);
    clearInterval(countdownTimer.current);
    reconnectAttempts.current = 0;
    manualDisconnect.current = true;
    lastEventIdRef.current = 0;
    lastAckedRef.current = 0;
    pendingReplay.current = false;
    clearTimeout(ackTimer.current);
    wsRef.current?.close();
    wsRef.current = null;
    dispatch({ type: "reset" });
  }, []);

  const createCard = useCallback((title: string, description: string, planner?: string, implementer?: string, reviewer?: string, coordinator?: string) => {
    send({ type: "card_create", title, description, planner, implementer, reviewer, coordinator });
  }, [send]);

  const updateCard = useCallback((card_id: string, fields: { title?: string; description?: string; planner?: string; implementer?: string; reviewer?: string; coordinator?: string }) => {
    send({ type: "card_update", card_id, ...fields });
  }, [send]);

  const startCard = useCallback((card_id: string) => {
    send({ type: "card_start", card_id });
  }, [send]);

  const delegateCard = useCallback((card_id: string) => {
    send({ type: "card_delegate", card_id });
  }, [send]);

  const markCardDone = useCallback((card_id: string) => {
    send({ type: "card_done", card_id });
  }, [send]);

  const deleteCard = useCallback((card_id: string) => {
    send({ type: "card_delete", card_id });
  }, [send]);

  const sendDM = useCallback((agent: string, text: string): boolean => {
    return send({ type: "direct_message", agent, text });
  }, [send]);

  const addAgent = useCallback((name: string, agentType: string, role: string) => {
    send({ type: "add_agent", name, agent_type: agentType, role });
  }, [send]);

  const removeAgent = useCallback((name: string) => {
    send({ type: "remove_agent", name });
  }, [send]);

  const respondToPermission = useCallback((requestId: string, approved: boolean, agent?: string) => {
    const sent = send({ type: "permission_response", request_id: requestId, approved, agent });
    if (sent) {
      dispatch({ type: "remove_permission", requestId, agent });
    }
  }, [send]);

  return { state, sendMessage, createSession, joinSession, stopAgent, stopRound, resume, disconnect, createCard, updateCard, startCard, delegateCard, markCardDone, deleteCard, sendDM, addAgent, removeAgent, respondToPermission };
}
