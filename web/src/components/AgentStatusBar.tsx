import { useState, useEffect, useRef, useCallback } from "react";
import { MoreVertical, Plus } from "lucide-react";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";
import type { AppState } from "../types";

interface Props {
  state: AppState;
  onStopAgent?: (agent: string) => void;
  onRemoveAgent?: (name: string) => void;
  onAddAgent?: (name: string, agentType: string, role: string) => void;
}

const STATUS_LABELS: Record<string, string> = {
  idle: "Idle",
  streaming: "Streaming",
  done: "Done",
  failed: "Failed",
};

const DEFAULT_STATUS_LABEL = "Unknown";

const STATUS_COLORS: Record<string, string> = {
  idle: "text-zinc-500",
  streaming: "text-emerald-400",
  done: "text-zinc-400",
  failed: "text-red-400",
};

const DEFAULT_STATUS_COLOR = "text-zinc-600";

const STATUS_DOTS: Record<string, string> = {
  idle: "bg-zinc-600",
  streaming: "bg-emerald-400 animate-pulse",
  done: "bg-zinc-500",
  failed: "bg-red-400",
};

const DEFAULT_STATUS_DOT = "bg-zinc-700";

const AGENT_TYPES = ["claude", "codex", "kimi"] as const;

function StreamTimer({ agent, statuses }: { agent: string; statuses: Record<string, string> }) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(Date.now());

  useEffect(() => {
    startRef.current = Date.now();
    setElapsed(0);
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [agent, statuses]);

  return <span className="text-[9px] text-zinc-600">{elapsed}s</span>;
}

export default function AgentStatusBar({ state, onStopAgent, onRemoveAgent, onAddAgent }: Props) {
  const [menuAgent, setMenuAgent] = useState<string | null>(null);
  const [showAddPopover, setShowAddPopover] = useState(false);
  const [newType, setNewType] = useState<string>("claude");
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const addRef = useRef<HTMLDivElement>(null);

  // Close menus on outside click
  const handleOutsideClick = useCallback((e: MouseEvent) => {
    if (menuAgent && menuRef.current && !menuRef.current.contains(e.target as Node)) {
      setMenuAgent(null);
    }
    if (showAddPopover && addRef.current && !addRef.current.contains(e.target as Node)) {
      setShowAddPopover(false);
    }
  }, [menuAgent, showAddPopover]);

  useEffect(() => {
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [handleOutsideClick]);

  const handleAdd = () => {
    const name = newName.trim() || (newType.charAt(0).toUpperCase() + newType.slice(1));
    if (onAddAgent) {
      onAddAgent(name, newType, newRole.trim());
    }
    setNewName("");
    setNewRole("");
    setNewType("claude");
    setShowAddPopover(false);
  };

  if (state.agents.length === 0 && !onAddAgent) return null;

  return (
    <div className="border-b border-zinc-800 bg-zinc-950/50 px-3 py-2 md:px-4 shrink-0">
      <div className="max-w-3xl mx-auto flex items-center gap-3">
        <span className="text-[10px] text-zinc-600 uppercase tracking-wider shrink-0">Agents</span>
        <div
          className="flex items-center gap-3 overflow-x-auto flex-1 min-w-0"
          style={{ maskImage: "linear-gradient(to right, black calc(100% - 16px), transparent)" }}
        >
          {state.agents.map((agentInfo) => {
            const status = state.agentStatuses[agentInfo.name] || "idle";
            const agentColor = AGENT_COLORS[agentInfo.type] || "text-zinc-400";
            const dotClass = STATUS_DOTS[status] ?? DEFAULT_STATUS_DOT;
            const labelClass = STATUS_COLORS[status] ?? DEFAULT_STATUS_COLOR;
            const statusLabel = STATUS_LABELS[status] ?? DEFAULT_STATUS_LABEL;

            return (
              <div
                key={agentInfo.name}
                className="relative flex items-center gap-1.5 px-2 py-1 rounded bg-zinc-900/50 border border-zinc-800 shrink-0"
                title={`${agentInfo.name}: ${statusLabel}`}
              >
                <div className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
                <span className={`${agentColor}`}>
                  <AgentIcon agent={agentInfo.type} size={12} />
                </span>
                <span className={`text-[10px] ${labelClass}`}>{agentInfo.name}</span>
                {status === "streaming" && (
                  <StreamTimer agent={agentInfo.name} statuses={state.agentStatuses} />
                )}
                {(onStopAgent || onRemoveAgent) && (
                  <button
                    onClick={(e) => { e.stopPropagation(); setMenuAgent(menuAgent === agentInfo.name ? null : agentInfo.name); }}
                    className="ml-0.5 p-0.5 rounded hover:bg-zinc-700 transition-colors text-zinc-500 hover:text-zinc-300"
                    title={`Options for ${agentInfo.name}`}
                  >
                    <MoreVertical size={10} />
                  </button>
                )}
                {/* Context menu popover */}
                {menuAgent === agentInfo.name && (
                  <div
                    ref={menuRef}
                    className="absolute top-full right-0 mt-1 z-50 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl py-1 min-w-[100px]"
                  >
                    {status === "streaming" && onStopAgent && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onStopAgent(agentInfo.name); setMenuAgent(null); }}
                        className="w-full text-left px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors"
                      >
                        Stop
                      </button>
                    )}
                    {onRemoveAgent && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onRemoveAgent(agentInfo.name); setMenuAgent(null); }}
                        className="w-full text-left px-3 py-1.5 text-xs text-red-400 hover:bg-zinc-700 transition-colors"
                      >
                        Remove
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {/* Add agent button */}
          {onAddAgent && (
            <div className="relative shrink-0" ref={addRef}>
              <button
                onClick={() => setShowAddPopover(!showAddPopover)}
                className="flex items-center justify-center w-6 h-6 rounded bg-zinc-900/50 border border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
                title="Add agent"
              >
                <Plus size={12} />
              </button>
              {showAddPopover && (
                <div className="absolute top-full left-0 mt-1 z-50 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl p-3 min-w-[200px]">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className={AGENT_COLORS[newType] || "text-zinc-400"}>
                        <AgentIcon agent={newType} size={12} />
                      </span>
                      <select
                        value={newType}
                        onChange={(e) => setNewType(e.target.value)}
                        className="flex-1 bg-zinc-700 border border-zinc-600 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500"
                      >
                        {AGENT_TYPES.map(t => (
                          <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                        ))}
                      </select>
                    </div>
                    <input
                      type="text"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="Name (auto)"
                      className="w-full px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-zinc-500"
                    />
                    <input
                      type="text"
                      value={newRole}
                      onChange={(e) => setNewRole(e.target.value)}
                      placeholder="Role (optional)"
                      className="w-full px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-zinc-500"
                    />
                    <button
                      onClick={handleAdd}
                      className="w-full px-2 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded text-xs text-zinc-200 transition-colors"
                    >
                      Add
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        {state.currentRound > 0 && (
          <div className="flex items-center gap-3 shrink-0">
            <span className="text-zinc-700">|</span>
            <span className="text-[10px] text-zinc-500">
              Round {state.currentRound}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
