import { useEffect, useState, useRef } from "react";
import { Plus, Trash2, Settings } from "lucide-react";
import { fetchSessions, deleteSession, type ServerSession } from "../api";
import { useToast } from "./Toast";
import FolderPicker from "./FolderPicker";
import RosterEditor from "./RosterEditor";
import type { AgentInfo } from "../types";
import SettingsModal from "./SettingsModal";

interface Props {
  onSelect: (sessionId: string) => void;
  onCreate: (workingDir?: string, agents?: AgentInfo[], config?: Record<string, unknown>) => void;
  connectionStatus?: string | null;
  connectionError?: boolean;
  defaultAgents?: AgentInfo[];
}

export default function SessionPicker({ onSelect, onCreate, connectionStatus, connectionError, defaultAgents = [] }: Props) {
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
    <div className="flex items-center justify-center h-[100dvh] overflow-y-auto bg-zinc-950 text-zinc-100 font-mono">
      <div className="w-full max-w-md p-6 my-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold">Multiagents</h1>
          <button
            onClick={() => setShowSettings(true)}
            className="text-zinc-500 hover:text-zinc-300 transition-colors"
            title="Settings"
          >
            <Settings size={16} />
          </button>
        </div>
        {connectionStatus && (
          <div className={`mb-4 rounded-lg border px-3 py-2 text-xs ${connectionError ? "border-red-500/30 bg-red-500/10 text-red-200" : "border-amber-500/30 bg-amber-500/10 text-amber-200"}`}>
            {connectionStatus}
          </div>
        )}
        <button onClick={() => setShowPicker(true)}
          className="w-full flex items-center gap-2 px-4 py-3 bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors mb-4">
          <Plus size={16} /><span className="text-sm">New Chat</span>
        </button>
        <div className="space-y-2">
          <p className="text-xs text-zinc-500 uppercase tracking-wide">Recent</p>
          {loading ? (
            <p className="text-xs text-zinc-600 py-2">Loading sessions...</p>
          ) : sessions.length === 0 ? (
            <p className="text-xs text-zinc-600 py-2">No sessions yet</p>
          ) : (
            <div className="max-h-[60vh] overflow-y-auto -mr-2 pr-2 space-y-2 pb-6" style={{ maskImage: "linear-gradient(to bottom, black calc(100% - 24px), transparent)" }}>
              {sessions.map((s) => (
                <div key={s.id} className="relative group">
                  <button onClick={() => onSelect(s.id)}
                    className="w-full text-left px-4 py-3 bg-zinc-900 hover:bg-zinc-800 rounded-lg transition-colors pr-10">
                    <p className="text-sm text-zinc-300 truncate" title={s.title}>{s.title}</p>
                    <p className="text-xs text-zinc-600">{s.agent_names.map(a => typeof a === "string" ? a : a.name).join(", ")}</p>
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(s.id); }}
                    className={`absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md transition-colors ${
                      confirmId === s.id
                        ? "text-red-400 bg-red-500/10"
                        : "text-zinc-600 hover:text-red-400 hover:bg-zinc-700"
                    }`}
                    title={confirmId === s.id ? "Click again to confirm" : "Delete session"}
                  >
                    {confirmId === s.id ? (
                      <span className="text-[10px] font-medium">Delete?</span>
                    ) : (
                      <Trash2 size={14} />
                    )}
                  </button>
                </div>
              ))}
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
