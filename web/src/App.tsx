import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import SessionPicker from "./components/SessionPicker";
import ChatRoom from "./components/ChatRoom";
import PromptInput from "./components/PromptInput";
import AgentStatusBar from "./components/AgentStatusBar";
import KanbanPanel from "./components/KanbanPanel";
import LayoutToggle, { type LayoutMode } from "./components/LayoutToggle";
import SplitLayout from "./components/SplitLayout";
import { fetchSessionStatus, type SessionStatus } from "./api";
import { useToast } from "./components/Toast";
import SettingsModal from "./components/SettingsModal";
import { Settings } from "lucide-react";

function getHashSessionId(): string | null {
  const hash = window.location.hash.slice(1);
  return hash || null;
}

export default function App() {
  const { toast } = useToast();
  const toastRef = useRef(toast);
  toastRef.current = toast;

  const handleSendFailure = useCallback((msgType: string) => {
    toastRef.current(`Failed to send ${msgType} — connection lost`, "error");
  }, []);
  const { state, sendMessage, createSession, joinSession, stopAgent, stopRound, resume, disconnect, createCard, updateCard, startCard, delegateCard, markCardDone, deleteCard, sendDM, addAgent, removeAgent } = useWebSocket(handleSendFailure);
  const [showPicker, setShowPicker] = useState(!getHashSessionId());
  const [showKanban, setShowKanban] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>(() => {
    try {
      const stored = localStorage.getItem("layout-mode");
      if (stored === "unified" || stored === "split") return stored;
    } catch {}
    return "split";
  });

  const handleLayoutChange = useCallback((mode: LayoutMode) => {
    setLayoutMode(mode);
    localStorage.setItem("layout-mode", mode);
  }, []);

  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [statusError, setStatusError] = useState(false);
  const hashJoinedRef = useRef(false);

  // Show toast when connection drops or reconnect exhausted
  const wasConnectedRef = useRef(false);
  useEffect(() => {
    if (state.connected) {
      wasConnectedRef.current = true;
    } else if (wasConnectedRef.current && state.reconnecting) {
      toast("Connection lost — reconnecting…", "error");
      wasConnectedRef.current = false;
    }
  }, [state.connected, state.reconnecting, toast]);

  useEffect(() => {
    if (state.reconnectExhausted) {
      toast("Could not reconnect to server. Please refresh the page.", "error");
    }
  }, [state.reconnectExhausted, toast]);

  // Auto-join session from URL hash on first connect
  useEffect(() => {
    if (!state.connected || hashJoinedRef.current) return;
    const hashSid = getHashSessionId();
    if (hashSid && !state.sessionId) {
      hashJoinedRef.current = true;
      joinSession(hashSid);
    }
  }, [state.connected, state.sessionId, joinSession]);

  // Sync URL hash with current session + copy URL toast
  const prevSessionRef = useRef<string | null>(null);
  useEffect(() => {
    if (state.sessionId) {
      setShowPicker(false);
      window.location.hash = state.sessionId;
      if (prevSessionRef.current !== state.sessionId) {
        prevSessionRef.current = state.sessionId;
        navigator.clipboard.writeText(window.location.href).then(
          () => toast("Session URL copied to clipboard", "info"),
          () => {} // clipboard not available, skip silently
        );
      }
    }
  }, [state.sessionId, toast]);

  const handleCreate = useCallback((workingDir?: string, agents?: import("./types").AgentInfo[], config?: Record<string, unknown>) => { createSession(workingDir, agents, config); }, [createSession]);
  const handleSelect = useCallback((sessionId: string) => { joinSession(sessionId); }, [joinSession]);
  const handleBack = useCallback(() => {
    disconnect();
    hashJoinedRef.current = false;
    prevSessionRef.current = null;
    history.replaceState(null, "", window.location.pathname);
    setShowPicker(true);
  }, [disconnect]);

  const reconnectStatus = state.reconnectExhausted
    ? "Connection lost. Please refresh the page."
    : state.reconnecting
    ? `Reconnecting in ${Math.ceil((state.reconnectInMs ?? 0) / 1000)}s (attempt ${state.reconnectAttempt}/10)`
    : null;

  useEffect(() => {
    if (!state.sessionId || showPicker) {
      setStatus(null);
      setStatusError(false);
      return;
    }
    let alive = true;
    const load = () => {
      fetchSessionStatus(state.sessionId!)
        .then((data) => {
          if (!alive) return;
          setStatus(data);
          setStatusError(false);
        })
        .catch(() => {
          if (!alive) return;
          setStatusError(true);
        });
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [state.sessionId, showPicker]);

  const statusSummary = useMemo(() => {
    if (!status) return statusError ? "Status unavailable" : null;
    if (status.is_paused) return "Paused";
    if (status.is_running) return `Running${status.current_round ? ` \u00b7 Round ${status.current_round}` : ""}`;
    return "Idle";
  }, [status, statusError]);

  const lastEventSummary = useMemo(() => {
    if (!status) return null;
    if (!status.last_event_time) return "No events yet";
    const ts = Date.parse(status.last_event_time);
    if (Number.isNaN(ts)) return "Last event unknown";
    const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
    if (diffSec < 60) return `Last event ${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `Last event ${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `Last event ${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    return `Last event ${diffDay}d ago`;
  }, [status]);

  if (showPicker || !state.sessionId) {
    return <SessionPicker onSelect={handleSelect} onCreate={handleCreate} connectionStatus={reconnectStatus} connectionError={state.reconnectExhausted} defaultAgents={state.agents} />;
  }

  return (
    <div className="flex flex-col h-[100dvh] bg-zinc-950 text-zinc-100 font-mono text-sm">
      {/* Header */}
      <div className="border-b border-zinc-800 shrink-0">
        <div className="h-11 flex items-center px-4">
          <button onClick={handleBack} className="text-zinc-500 hover:text-zinc-300 transition-colors mr-3 text-xs">&larr; Back</button>
          <h1 className="text-base font-semibold tracking-tight truncate flex-1 min-w-0">{state.title || "Multiagents"}</h1>
          <div className="flex items-center gap-3 text-xs text-zinc-500 shrink-0">
            <LayoutToggle mode={layoutMode} onChange={handleLayoutChange} />
            <button
              onClick={() => setShowSettings(v => !v)}
              className={`hover:text-zinc-300 transition-colors ${showSettings ? "text-zinc-300" : ""}`}
              title="Settings"
            >
              <Settings size={14} />
            </button>
            <button
              onClick={() => setShowKanban(v => !v)}
              className={`hover:text-zinc-300 transition-colors text-xs ${showKanban ? "text-zinc-300" : ""}`}
              title="Toggle task board"
            >
              Tasks
            </button>
            {state.isRunning && (
              <span className="flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${state.isPaused ? "bg-amber-400" : "bg-emerald-400 animate-pulse"}`} />
                <span className="hidden md:inline">{state.isPaused ? "Paused" : "Discussing"}</span>
              </span>
            )}
            {statusSummary && (
              <span className={`hidden md:inline ${statusError ? "text-amber-300" : "text-zinc-400"}`}>
                {statusSummary}
              </span>
            )}
            {lastEventSummary && <span className="hidden md:inline text-zinc-600">{lastEventSummary}</span>}
          </div>
        </div>
        {reconnectStatus && (
          <div className={`px-4 py-1.5 border-t text-xs ${state.reconnectExhausted ? "bg-red-500/10 border-red-500/20 text-red-300" : "bg-amber-500/10 border-amber-500/20 text-amber-300"}`}>
            {reconnectStatus}
          </div>
        )}
      </div>
      <AgentStatusBar state={state} onStopAgent={stopAgent} onRemoveAgent={removeAgent} onAddAgent={addAgent} />
      <div className="flex flex-1 overflow-hidden">
        {layoutMode === "unified" ? (
          <div className="flex-1 flex flex-col overflow-hidden">
            <ChatRoom state={state} />
          </div>
        ) : (
          <SplitLayout state={state} onSendDM={sendDM} />
        )}
        {showKanban && (
          <KanbanPanel
            cards={state.cards}
            agents={state.agents.map(a => a.name)}
            isRunning={state.isRunning}
            onCreateCard={(title, desc, planner, implementer, reviewer, coordinator) => createCard(title, desc, planner, implementer, reviewer, coordinator)}
            onUpdateCard={updateCard}
            onStartCard={startCard}
            onDelegateCard={delegateCard}
            onMarkDone={markCardDone}
            onDeleteCard={deleteCard}
          />
        )}
      </div>
      <PromptInput
        onSubmit={sendMessage}
        onStopRound={stopRound}
        onResume={resume}
        isRunning={state.isRunning}
        isPaused={state.isPaused}
        connected={state.connected}
        agents={state.agents}
      />
      <SettingsModal open={showSettings} onClose={() => setShowSettings(false)} />
    </div>
  );
}
