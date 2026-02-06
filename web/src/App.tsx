import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import SessionPicker from "./components/SessionPicker";
import PromptInput from "./components/PromptInput";
import KanbanPanel from "./components/KanbanPanel";
import SplitLayout from "./components/SplitLayout";
import SessionContextPanel from "./components/SessionContextPanel";
import { fetchSessions, fetchSettings, type ServerSession } from "./api";
import { AgentIcon, AGENT_COLORS } from "./components/AgentIcons";
import { useToast } from "./components/Toast";
import SettingsModal from "./components/SettingsModal";
import PermissionBanner from "./components/PermissionBanner";
import { ChevronDown, Copy, FileText, ListTodo, Pin, Settings, X } from "lucide-react";
import { applyThemeAttributes, normalizeThemeConfig, type ThemeConfig } from "./theme/applyTheme";
import { Button } from "./components/ui";
import { copyTextToClipboard } from "./utils/clipboard";

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
  const { state, sendMessage, createSession, joinSession, stopAgent, stopRound, resume, disconnect, createCard, updateCard, startCard, delegateCard, markCardDone, deleteCard, sendDM, addAgent, removeAgent, respondToPermission } = useWebSocket(handleSendFailure);
  const [showPicker, setShowPicker] = useState(!getHashSessionId());
  const [showSettings, setShowSettings] = useState(false);
  const [activeUtility, setActiveUtility] = useState<"session" | "tasks" | null>(null);
  const [showSessionMenu, setShowSessionMenu] = useState(false);
  const [recentSessions, setRecentSessions] = useState<ServerSession[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [selectedContextAgent, setSelectedContextAgent] = useState<string | null>(null);
  const [pinnedUtilities, setPinnedUtilities] = useState<{ session: boolean; tasks: boolean }>({ session: false, tasks: false });
  const [pinnedWidths, setPinnedWidths] = useState<{ session: number; tasks: number }>({ session: 360, tasks: 430 });
  const [density, setDensity] = useState<"compact" | "comfortable">("comfortable");
  const [themeConfig, setThemeConfig] = useState<ThemeConfig>({
    mode: "dark",
    accent: "cyan",
    density: "cozy",
  });
  const loadThemeDefaults = useCallback(() => {
    fetchSettings()
      .then((data) => {
        const nextTheme = normalizeThemeConfig({
          mode: data["ui.theme.mode"] as ThemeConfig["mode"] | undefined,
          accent: data["ui.theme.accent"] as ThemeConfig["accent"] | undefined,
          density: data["ui.theme.density"] as ThemeConfig["density"] | undefined,
        });
        setThemeConfig(nextTheme);
        setDensity(nextTheme.density === "compact" ? "compact" : "comfortable");
      })
      .catch(() => {
        // Preserve existing fallback if settings can't be loaded.
      });
  }, []);

  const hashJoinedRef = useRef(false);
  const resizeDragRef = useRef<{ utility: "session" | "tasks"; startX: number; startWidth: number } | null>(null);

  // Show toast when connection drops or reconnect exhausted
  const wasConnectedRef = useRef(false);
  useEffect(() => {
    if (state.connected) {
      wasConnectedRef.current = true;
    } else if (wasConnectedRef.current && state.reconnecting) {
      toast("Connection lost — reconnecting…", "error", {
        durationMs: 5000,
        dedupeKey: "reconnecting",
        actionLabel: "Refresh now",
        onAction: () => window.location.reload(),
      });
      wasConnectedRef.current = false;
    }
  }, [state.connected, state.reconnecting, toast]);

  useEffect(() => {
    if (state.reconnectExhausted) {
      toast("Could not reconnect to server.", "error", {
        durationMs: 8000,
        dedupeKey: "reconnect-exhausted",
        actionLabel: "Refresh now",
        onAction: () => window.location.reload(),
      });
    }
  }, [state.reconnectExhausted, toast]);

  useEffect(() => {
    if (!showSettings) loadThemeDefaults();
  }, [showSettings, loadThemeDefaults]);

  useEffect(() => {
    applyThemeAttributes(themeConfig);
  }, [themeConfig]);

  useEffect(() => {
    if (themeConfig.mode !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => applyThemeAttributes(themeConfig);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [themeConfig]);

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
        void copyTextToClipboard(window.location.href).then((ok) => {
          if (ok) toast("Session URL copied to clipboard", "info");
        });
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

  const handleCopySessionId = useCallback(() => {
    if (!state.sessionId) return;
    void copyTextToClipboard(state.sessionId).then((ok) => {
      if (ok) toast("Session ID copied", "info");
      else toast("Failed to copy session ID", "error");
    });
  }, [state.sessionId, toast]);

  const loadRecentSessions = useCallback(() => {
    setLoadingSessions(true);
    fetchSessions()
      .then((sessions) => setRecentSessions(sessions.slice(0, 10)))
      .catch(() => toast("Failed to load sessions", "error"))
      .finally(() => setLoadingSessions(false));
  }, [toast]);

  useEffect(() => {
    if (showSessionMenu) loadRecentSessions();
  }, [showSessionMenu, loadRecentSessions]);

  const sessionMenuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!showSessionMenu) return;
    const onDown = (e: MouseEvent) => {
      if (sessionMenuRef.current && !sessionMenuRef.current.contains(e.target as Node)) {
        setShowSessionMenu(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [showSessionMenu]);

  useEffect(() => {
    const key = `workspace-pins:${state.sessionId ?? "global"}`;
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw) as { session?: boolean; tasks?: boolean };
        setPinnedUtilities({ session: !!parsed.session, tasks: !!parsed.tasks });
      } else {
        setPinnedUtilities({ session: false, tasks: false });
      }
    } catch {
      setPinnedUtilities({ session: false, tasks: false });
    }
  }, [state.sessionId]);

  useEffect(() => {
    const key = `workspace-pins:${state.sessionId ?? "global"}`;
    try {
      localStorage.setItem(key, JSON.stringify(pinnedUtilities));
    } catch {}
  }, [state.sessionId, pinnedUtilities]);

  useEffect(() => {
    const key = `workspace-pane-widths:${state.sessionId ?? "global"}`;
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw) as { session?: number; tasks?: number };
        setPinnedWidths({
          session: Math.max(280, Math.min(680, Number(parsed.session ?? 360))),
          tasks: Math.max(300, Math.min(760, Number(parsed.tasks ?? 430))),
        });
      } else {
        setPinnedWidths({ session: 360, tasks: 430 });
      }
    } catch {
      setPinnedWidths({ session: 360, tasks: 430 });
    }
  }, [state.sessionId]);

  useEffect(() => {
    const key = `workspace-pane-widths:${state.sessionId ?? "global"}`;
    try {
      localStorage.setItem(key, JSON.stringify(pinnedWidths));
    } catch {}
  }, [state.sessionId, pinnedWidths]);

  useEffect(() => {
    if (!selectedContextAgent && state.agents.length > 0) {
      setSelectedContextAgent(state.agents[0].name);
      return;
    }
    if (selectedContextAgent && !state.agents.some((a) => a.name === selectedContextAgent)) {
      setSelectedContextAgent(state.agents[0]?.name ?? null);
    }
  }, [selectedContextAgent, state.agents]);

  const sessionUtilityCount = useMemo(() => {
    if (!selectedContextAgent) return 0;
    return state.messages.filter((m) => m.role === selectedContextAgent || m.role === `dm:${selectedContextAgent}`).length;
  }, [state.messages, selectedContextAgent]);
  const pinnedUtilityList = useMemo(() => {
    const list: Array<"session" | "tasks"> = [];
    if (pinnedUtilities.session) list.push("session");
    if (pinnedUtilities.tasks) list.push("tasks");
    return list;
  }, [pinnedUtilities]);
  const workspaceGridTemplate = useMemo(() => {
    if (pinnedUtilityList.length === 0) return "minmax(0,1fr)";
    if (pinnedUtilityList.length === 1) {
      const only = pinnedUtilityList[0];
      return `minmax(0,1fr) ${pinnedWidths[only]}px`;
    }
    return `minmax(0,1fr) ${pinnedWidths.session}px ${pinnedWidths.tasks}px`;
  }, [pinnedUtilityList, pinnedWidths]);

  const startResizePane = useCallback((utility: "session" | "tasks", clientX: number) => {
    resizeDragRef.current = { utility, startX: clientX, startWidth: pinnedWidths[utility] };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [pinnedWidths]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const drag = resizeDragRef.current;
      if (!drag) return;
      const delta = e.clientX - drag.startX;
      const raw = drag.startWidth - delta;
      const min = drag.utility === "session" ? 280 : 300;
      const max = drag.utility === "session" ? 680 : 760;
      const next = Math.max(min, Math.min(max, raw));
      setPinnedWidths((prev) => ({ ...prev, [drag.utility]: next }));
    };
    const onUp = () => {
      if (!resizeDragRef.current) return;
      resizeDragRef.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const renderUtilityPane = useCallback((utility: "session" | "tasks") => {
    if (utility === "session") {
      return (
        <SessionContextPanel
          state={state}
          selectedAgent={selectedContextAgent}
          onSelectAgent={setSelectedContextAgent}
          onSendDM={(agent, text) => sendDM(agent, text)}
        />
      );
    }
    return (
      <KanbanPanel
        variant="drawer"
        sessionId={state.sessionId}
        cards={state.cards}
        agents={state.agents}
        isRunning={state.isRunning}
        onCreateCard={(title, desc, planner, implementer, reviewer, coordinator) => createCard(title, desc, planner, implementer, reviewer, coordinator)}
        onUpdateCard={updateCard}
        onStartCard={startCard}
        onDelegateCard={delegateCard}
        onMarkDone={markCardDone}
        onDeleteCard={deleteCard}
      />
    );
  }, [state, selectedContextAgent, createCard, updateCard, startCard, delegateCard, markCardDone, deleteCard]);

  const latestUserSummary = useMemo(() => {
    for (let i = state.messages.length - 1; i >= 0; i -= 1) {
      const msg = state.messages[i];
      if (msg.role !== "user") continue;
      const compact = msg.content.replace(/\s+/g, " ").trim();
      if (!compact) continue;
      return compact.length > 64 ? `${compact.slice(0, 63)}…` : compact;
    }
    return null;
  }, [state.messages]);

  if (showPicker || !state.sessionId) {
    return <SessionPicker onSelect={handleSelect} onCreate={handleCreate} defaultAgents={state.agents} />;
  }

  return (
    <div className="flex flex-col h-[100dvh] bg-ui-canvas text-ui-strong text-sm">
      {/* Header */}
      <div className="border-b border-ui-soft shrink-0" style={{ background: "var(--bg-surface)" }}>
        <div className="h-[52px] flex items-center px-4 gap-3">
          {/* Left: sessions + logo */}
          <div className="relative" ref={sessionMenuRef}>
            <button
              onClick={() => setShowSessionMenu((v) => !v)}
              className="h-8 px-2.5 rounded-md border border-ui-soft bg-ui-surface text-[11px] font-mono text-ui-subtle hover:text-ui hover:bg-ui-elevated inline-flex items-center gap-1.5 cursor-pointer"
              title="Sessions"
            >
              <span className="[font-variant-caps:small-caps] tracking-[0.06em]">SESSIONS</span>
              <ChevronDown size={12} />
            </button>
            {showSessionMenu && (
              <div className="absolute left-0 top-full mt-2 w-[min(360px,80vw)] ui-panel border-ui-strong bg-ui-elevated shadow-xl z-50 p-2">
                <div className="flex items-center justify-between px-1 pb-1">
                  <span className="text-[10px] font-semibold font-mono text-ui-subtle uppercase tracking-[0.08em]">Recent sessions</span>
                  <button
                    onClick={() => {
                      setShowSessionMenu(false);
                      handleBack();
                    }}
                    className="text-[10px] font-mono text-ui-subtle hover:text-ui cursor-pointer"
                  >
                    Open all
                  </button>
                </div>
                <div className="max-h-[320px] overflow-y-auto space-y-1">
                  {loadingSessions ? (
                    <div className="px-2 py-2 text-[11px] text-ui-faint">Loading…</div>
                  ) : recentSessions.length === 0 ? (
                    <div className="px-2 py-2 text-[11px] text-ui-faint">No sessions yet</div>
                  ) : (
                    recentSessions.map((s) => {
                      const sessionAgentTypes = Array.from(
                        new Set(
                          (s.agent_names ?? [])
                            .map((agent) => (typeof agent === "string" ? agent : agent.type ?? agent.name))
                            .map((value) => value?.toLowerCase().trim())
                            .filter((value): value is string => !!value)
                        )
                      );
                      const visibleAgentTypes = sessionAgentTypes.slice(0, 3);
                      const hiddenAgentCount = Math.max(0, sessionAgentTypes.length - visibleAgentTypes.length);

                      return (
                        <button
                          key={s.id}
                          onClick={() => {
                            setShowSessionMenu(false);
                            joinSession(s.id);
                          }}
                          className={`w-full text-left rounded-md px-2 py-2 border transition-colors cursor-pointer ${
                            s.id === state.sessionId
                              ? "border-ui-info-soft bg-ui-info-soft"
                              : "hover:border-ui-soft hover:bg-ui-soft"
                          }`}
                          style={s.id === state.sessionId ? undefined : { borderColor: "transparent" }}
                          title={s.title}
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <div className="flex items-center -space-x-1 shrink-0">
                              {visibleAgentTypes.map((agentType, idx) => (
                                <span
                                  key={`${s.id}-${agentType}-${idx}`}
                                  className={`w-4 h-4 rounded-full border border-ui bg-ui-card flex items-center justify-center ${AGENT_COLORS[agentType] ?? "text-ui-subtle"}`}
                                  title={agentType}
                                >
                                  <AgentIcon agent={agentType} size={9} />
                                </span>
                              ))}
                              {hiddenAgentCount > 0 && (
                                <span
                                  className="w-4 h-4 rounded-full border border-ui bg-ui-card flex items-center justify-center text-[8px] font-mono text-ui-faint"
                                  title={`${hiddenAgentCount} more agents`}
                                >
                                  +{hiddenAgentCount}
                                </span>
                              )}
                            </div>
                            <div className="min-w-0">
                              <div className="text-[12px] text-ui truncate">{s.title || s.id}</div>
                              <div className="text-[10px] text-ui-faint font-mono truncate">{s.id}</div>
                            </div>
                          </div>
                        </button>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>
          <div className="flex items-center shrink-0">
            <div className="logo-icon-gradient flex items-center justify-center" aria-label="Multiagents logo" title="Multiagents">
              <svg viewBox="0 0 24 24" className="w-5 h-5" aria-hidden="true" focusable="false">
                <defs>
                  <linearGradient id="multiagents-logo-gradient" x1="2" y1="22" x2="22" y2="2" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stopColor="var(--agent-claude)" />
                    <stop offset="50%" stopColor="var(--agent-codex)" />
                    <stop offset="100%" stopColor="var(--agent-kimi)" />
                  </linearGradient>
                </defs>
                <path
                  d="M3.5 18.5 8 7.5l4 7 4-8 4.5 12"
                  fill="none"
                  stroke="url(#multiagents-logo-gradient)"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <circle cx="8" cy="7.5" r="1.35" fill="var(--agent-claude)" />
                <circle cx="12" cy="14.5" r="1.35" fill="var(--agent-codex)" />
                <circle cx="16" cy="6.5" r="1.35" fill="var(--agent-kimi)" />
              </svg>
            </div>
          </div>
          <div className="w-px h-5 border-l border-ui-soft shrink-0 hidden sm:block" />

          {latestUserSummary && (
            <span className="text-[13px] text-ui-muted font-medium min-w-0 truncate hidden md:block">
              {latestUserSummary}
            </span>
          )}

          {/* Right: controls */}
          <div className="flex items-center gap-2 text-xs text-ui-subtle shrink-0 ml-auto min-w-0">
            {state.currentRound > 0 && (
              <span className="text-[10px] font-mono text-ui-faint hidden md:inline">R{state.currentRound}</span>
            )}
            <span
              className="hidden sm:inline-flex max-w-[220px] items-center rounded-md border border-ui-soft px-2 py-1 text-[10px] font-mono text-ui-muted truncate"
              title={state.sessionId}
            >
              {state.sessionId}
            </span>
            <button
              onClick={handleCopySessionId}
              className="p-1.5 rounded-md transition-colors cursor-pointer text-ui-subtle hover:text-ui hover:bg-ui-soft"
              title="Copy session ID"
              aria-label="Copy session ID"
            >
              <Copy size={13} />
            </button>
            <button
              onClick={() => setShowSettings(v => !v)}
              className={`p-1.5 rounded-md transition-colors cursor-pointer ${showSettings ? "text-ui-strong" : "text-ui-subtle hover:text-ui"}`}
              style={showSettings ? { background: 'var(--bg-active)' } : undefined}
              title="Settings"
            >
              <Settings size={14} />
            </button>
          </div>
        </div>
      </div>
      <PermissionBanner permissions={state.pendingPermissions} onRespond={respondToPermission} />
      <div className="flex-1 min-h-0 overflow-hidden grid" style={{ gridTemplateColumns: workspaceGridTemplate }}>
        <div className="min-w-0 min-h-0 overflow-hidden">
          <div className="flex h-full overflow-hidden">
            <SplitLayout
              state={state}
              onSendDM={sendDM}
              onStopAgent={stopAgent}
              onRemoveAgent={removeAgent}
              onAddAgent={addAgent}
              density={density}
            >
              <PromptInput
                onSubmit={sendMessage}
                onStopRound={stopRound}
                onResume={resume}
                isRunning={state.isRunning}
                isPaused={state.isPaused}
                connected={state.connected}
                agents={state.agents}
              />
            </SplitLayout>
          </div>
        </div>
        {pinnedUtilityList.map((utility) => (
          <div key={`pinned-${utility}`} className="relative min-h-0 border-l border-ui-soft bg-ui-surface flex flex-col overflow-hidden">
            <div
              onMouseDown={(e) => startResizePane(utility, e.clientX)}
              className="absolute left-0 top-0 bottom-0 w-2 -ml-1 cursor-col-resize hover:bg-ui-soft/60 transition-colors z-10"
              title={`Resize ${utility}`}
            />
            <div className="h-11 px-3 border-b border-ui-soft flex items-center justify-between shrink-0">
              <span className="text-[10px] font-semibold font-mono text-ui-subtle uppercase tracking-[0.08em]">
                {utility === "session" ? "Context" : "Tasks"}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPinnedUtilities((prev) => ({ ...prev, [utility]: false }))}
                className="text-ui-subtle hover:text-ui !p-1.5"
                icon={<X size={13} />}
                aria-label={`Close pinned ${utility}`}
                title={`Close ${utility}`}
              >
                <span className="sr-only">Close</span>
              </Button>
            </div>
            <div className="flex-1 min-h-0">{renderUtilityPane(utility)}</div>
          </div>
        ))}
      </div>
      <div className="h-11 border-t border-ui-soft bg-ui-surface px-3 md:px-4 flex items-center gap-2 shrink-0">
        <button
          onClick={() => {
            if (pinnedUtilities.session) {
              setPinnedUtilities((prev) => ({ ...prev, session: false }));
              return;
            }
            setActiveUtility((v) => (v === "session" ? null : "session"));
          }}
          className={`inline-flex items-center gap-1.5 text-[10px] font-mono px-3 py-1.5 rounded-md border transition-colors cursor-pointer ${
            activeUtility === "session" || pinnedUtilities.session
              ? "text-ui-info bg-ui-info-soft border-ui-info-soft"
              : "text-ui-info bg-ui-surface border-ui-soft hover:bg-ui-info-soft"
          }`}
          title="Toggle context"
        >
          <FileText size={12} />
          Context {sessionUtilityCount > 0 ? `(${sessionUtilityCount})` : ""}
        </button>
        <button
          onClick={() => {
            if (pinnedUtilities.tasks) {
              setPinnedUtilities((prev) => ({ ...prev, tasks: false }));
              return;
            }
            setActiveUtility((v) => (v === "tasks" ? null : "tasks"));
          }}
          className={`inline-flex items-center gap-1.5 text-[10px] font-mono px-3 py-1.5 rounded-md border transition-colors cursor-pointer ${
            activeUtility === "tasks" || pinnedUtilities.tasks
              ? "text-ui-warn bg-ui-warn-soft border-ui-warn-soft"
              : "text-ui-warn bg-ui-surface border-ui-soft hover:bg-ui-warn-soft"
          }`}
          title="Toggle tasks"
        >
          <ListTodo size={12} />
          Tasks ({state.cards.length})
        </button>
        <span
          className="ml-auto flex items-center gap-1 text-[10px] font-mono text-ui-subtle"
          title={state.connected ? "Connected" : state.reconnecting ? "Reconnecting" : "Disconnected"}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${state.connected ? "dot-status-streaming" : state.reconnecting ? "dot-status-warn animate-pulse" : "dot-status-failed"}`} />
          {state.connected ? "Online" : state.reconnecting ? "Reconnecting" : "Offline"}
        </span>
      </div>
      {activeUtility && (
        <div
          className="fixed inset-0 z-50 overlay-backdrop flex items-center justify-center p-4"
          style={{ backdropFilter: "blur(6px)" }}
          onClick={() => setActiveUtility(null)}
        >
          <div
            className="w-[min(1100px,96vw)] h-[min(78vh,760px)] ui-modal border border-ui-strong flex flex-col"
            style={{ boxShadow: "var(--shadow-modal)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="h-11 px-4 border-b border-ui-soft flex items-center justify-between shrink-0">
              <span className="text-[10px] font-semibold font-mono text-ui-subtle uppercase tracking-[0.08em]">
                {activeUtility === "session" ? "Context" : "Tasks"}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    if (activeUtility) {
                      setPinnedUtilities((prev) => ({ ...prev, [activeUtility]: true }));
                      setActiveUtility(null);
                    }
                  }}
                  className="text-ui-subtle hover:text-ui !p-1.5"
                  icon={<Pin size={13} />}
                  aria-label="Pin utility modal"
                  title="Pin"
                >
                  <span className="sr-only">Pin</span>
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveUtility(null)}
                  className="text-ui-subtle hover:text-ui !p-1.5"
                  icon={<X size={14} />}
                  aria-label="Close utility modal"
                  title="Close"
                >
                  <span className="sr-only">Close</span>
                </Button>
              </div>
            </div>
            <div className="flex-1 min-h-0">
              {activeUtility && renderUtilityPane(activeUtility)}
            </div>
          </div>
        </div>
      )}
      <SettingsModal open={showSettings} onClose={() => setShowSettings(false)} />
      <div className="sr-only" aria-live="polite">
        {Object.values(state.agentStatuses).filter((s) => s === "streaming").length} agents streaming
      </div>
    </div>
  );
}
