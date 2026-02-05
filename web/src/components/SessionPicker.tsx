import { useEffect, useState, useRef } from "react";
import { Plus, Trash2, Settings } from "lucide-react";
import { fetchSessions, deleteSession, type ServerSession } from "../api";
import { useToast } from "./Toast";
import FolderPicker from "./FolderPicker";
import RosterEditor from "./RosterEditor";
import type { AgentInfo } from "../types";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";
import SettingsModal from "./SettingsModal";
import Button from "./ui/Button";
import Panel from "./ui/Panel";

interface Props {
  onSelect: (sessionId: string) => void;
  onCreate: (workingDir?: string, agents?: AgentInfo[], config?: Record<string, unknown>) => void;
  defaultAgents?: AgentInfo[];
}

export default function SessionPicker({ onSelect, onCreate, defaultAgents = [] }: Props) {
  const [sessions, setSessions] = useState<ServerSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [showPicker, setShowPicker] = useState(false);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const confirmTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const { toast } = useToast();
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    fetchSessions()
      .then(setSessions)
      .catch(() => toast("Failed to load sessions", "error"))
      .finally(() => setLoading(false));
  }, [toast]);

  const handleDelete = (id: string) => {
    if (confirmId !== id) {
      setConfirmId(id);
      clearTimeout(confirmTimer.current);
      confirmTimer.current = setTimeout(() => setConfirmId(null), 2000);
      return;
    }
    setConfirmId(null);
    clearTimeout(confirmTimer.current);
    deleteSession(id)
      .then(() => setSessions((prev) => prev.filter((x) => x.id !== id)))
      .catch(() => toast("Failed to delete session", "error"));
  };

  return (
    <div className="flex items-center justify-center h-[100dvh] overflow-y-auto bg-ui-canvas text-ui-strong">
      <div className="w-full max-w-lg p-6 my-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <div className="logo-icon-gradient flex items-center justify-center" aria-label="Multiagents logo" title="Multiagents">
              <svg viewBox="0 0 24 24" className="w-5 h-5" aria-hidden="true" focusable="false">
                <defs>
                  <linearGradient id="multiagents-logo-gradient-picker" x1="2" y1="22" x2="22" y2="2" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stopColor="var(--agent-claude)" />
                    <stop offset="50%" stopColor="var(--agent-codex)" />
                    <stop offset="100%" stopColor="var(--agent-kimi)" />
                  </linearGradient>
                </defs>
                <path
                  d="M3.5 18.5 8 7.5l4 7 4-8 4.5 12"
                  fill="none"
                  stroke="url(#multiagents-logo-gradient-picker)"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <circle cx="8" cy="7.5" r="1.35" fill="var(--agent-claude)" />
                <circle cx="12" cy="14.5" r="1.35" fill="var(--agent-codex)" />
                <circle cx="16" cy="6.5" r="1.35" fill="var(--agent-kimi)" />
              </svg>
            </div>
            <h1 className="text-xl font-semibold">Multiagents</h1>
          </div>
          <Button
            onClick={() => setShowSettings(true)}
            variant="ghost"
            size="sm"
            title="Settings"
            icon={<Settings size={16} />}
          >
            <span className="sr-only">Settings</span>
          </Button>
        </div>
        <Button onClick={() => setShowPicker(true)} className="w-full mb-4" icon={<Plus size={16} />}>
          <span className="[font-variant-caps:small-caps] tracking-[0.06em]">NEW SESSION</span>
        </Button>
        <div className="space-y-2">
          <p className="text-xs text-ui-subtle [font-variant-caps:small-caps] tracking-[0.08em]">RECENT SESSIONS</p>
          {loading ? (
            <p className="text-xs text-ui-faint py-2">Loading sessions...</p>
          ) : sessions.length === 0 ? (
            <p className="text-xs text-ui-faint py-2">No sessions yet</p>
          ) : (
            <div className="max-h-[60vh] overflow-y-auto -mr-2 pr-2 space-y-2 pb-6" style={{ maskImage: "linear-gradient(to bottom, black calc(100% - 24px), transparent)" }}>
              {sessions.map((s) => {
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
                <Panel key={s.id} className="relative group p-0">
                  <Button onClick={() => onSelect(s.id)} variant="ghost" className="w-full justify-start text-left px-4 py-3 hover:bg-ui-elevated rounded-lg pr-10">
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
                        <p className="text-sm text-ui truncate" title={s.title}>{s.title || s.id}</p>
                        <p className="text-xs text-ui-faint font-mono truncate">{s.id}</p>
                      </div>
                    </div>
                  </Button>
                  <Button
                    onClick={(e) => { e.stopPropagation(); handleDelete(s.id); }}
                    variant="ghost"
                    size="sm"
                    className={`absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md transition-colors ${
                      confirmId === s.id
                        ? "text-ui-danger bg-ui-danger-soft"
                        : "text-ui-faint hover:text-ui-danger hover:bg-ui-soft"
                    }`}
                    title={confirmId === s.id ? "Click again to confirm" : "Delete session"}
                  >
                    {confirmId === s.id ? (
                      <span className="text-[10px] font-medium">Delete?</span>
                    ) : (
                      <Trash2 size={14} />
                    )}
                  </Button>
                </Panel>
                );
              })}
            </div>
          )}
        </div>
      </div>
      <FolderPicker
        open={showPicker}
        onSelect={(path) => { setShowPicker(false); setSelectedPath(path); }}
        onClose={() => setShowPicker(false)}
      />
      <RosterEditor
        open={!!selectedPath}
        defaultAgents={defaultAgents}
        onStart={(agents, config) => { onCreate(selectedPath!, agents, config); setSelectedPath(null); }}
        onClose={() => setSelectedPath(null)}
      />
      <SettingsModal open={showSettings} onClose={() => setShowSettings(false)} />
    </div>
  );
}
