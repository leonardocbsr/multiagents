import { useState, useEffect, useCallback } from "react";
import { Plus, X } from "lucide-react";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";
import type { AgentInfo } from "../types";
import { fetchSettings } from "../api";

interface Props {
  open: boolean;
  defaultAgents: AgentInfo[];
  onStart: (agents: AgentInfo[], config?: Record<string, unknown>) => void;
  onClose: () => void;
}

const AGENT_TYPES = ["claude", "codex", "kimi"] as const;

function generateName(type: string, existing: AgentInfo[]): string {
  const base = type.charAt(0).toUpperCase() + type.slice(1);
  const existingNames = new Set(existing.map((a) => a.name.toLowerCase()));
  if (!existingNames.has(base.toLowerCase())) return base;
  // Find the next available number (case-insensitive)
  for (let i = 2; ; i++) {
    const candidate = `${base}-${i}`;
    if (!existingNames.has(candidate.toLowerCase())) return candidate;
  }
}

function findDuplicateNames(agents: AgentInfo[]): Set<number> {
  const dupes = new Set<number>();
  const seen = new Map<string, number>();
  agents.forEach((a, i) => {
    const lower = a.name.toLowerCase();
    if (seen.has(lower)) {
      dupes.add(seen.get(lower)!);
      dupes.add(i);
    } else {
      seen.set(lower, i);
    }
  });
  return dupes;
}

export default function RosterEditor({ open, defaultAgents, onStart, onClose }: Props) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [sessionConfig, setSessionConfig] = useState<Record<string, unknown>>({});
  const [settingsDefaults, setSettingsDefaults] = useState<Record<string, unknown>>({});
  const [settingsError, setSettingsError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setAgents(defaultAgents.length > 0 ? [...defaultAgents] : [{ name: "Claude", type: "claude", role: "" }]);
      setSessionConfig({});
      setSettingsError(null);
      fetchSettings()
        .then((data) => setSettingsDefaults(data as Record<string, unknown>))
        .catch(() => {
          setSettingsDefaults({});
          setSettingsError("Failed to load defaults");
        });
    }
  }, [open, defaultAgents]);

  const handleClose = useCallback(() => {
    onClose();
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, handleClose]);

  const updateAgent = (index: number, patch: Partial<AgentInfo>) => {
    setAgents(prev => prev.map((a, i) => (i === index ? { ...a, ...patch } : a)));
  };

  const removeAgent = (index: number) => {
    setAgents(prev => prev.filter((_, i) => i !== index));
  };

  const addAgent = () => {
    const type = "claude";
    setAgents(prev => [...prev, { name: generateName(type, prev), type, role: "" }]);
  };

  const handleTypeChange = (index: number, newType: string) => {
    setAgents(prev => {
      const updated = [...prev];
      const old = updated[index];
      // Auto-update name if it looks auto-generated (matches type pattern)
      const oldBase = old.type.charAt(0).toUpperCase() + old.type.slice(1);
      const isAutoName =
        old.name === oldBase ||
        old.name.toLowerCase() === old.type ||
        /^[A-Z][a-z]+-\d+$/.test(old.name);
      updated[index] = { ...old, type: newType };
      if (isAutoName) {
        const withoutCurrent = updated.filter((_, i) => i !== index);
        updated[index].name = generateName(newType, withoutCurrent);
      }
      return updated;
    });
  };

  const duplicates = findDuplicateNames(agents);
  const hasEmptyNames = agents.some(a => !a.name.trim());
  const canStart = agents.length > 0 && duplicates.size === 0 && !hasEmptyNames;
  const getDefault = (key: string): unknown => settingsDefaults[key];
  const getResolved = (key: string): unknown => (key in sessionConfig ? sessionConfig[key] : getDefault(key));
  const getResolvedText = (key: string): string => {
    const value = getResolved(key);
    if (value === null || value === undefined) return "";
    return String(value);
  };
  const getResolvedNumber = (key: string): number | "" => {
    const value = getResolved(key);
    if (typeof value === "number") return value;
    if (typeof value === "string" && value !== "") {
      const num = Number(value);
      if (!Number.isNaN(num)) return num;
    }
    return "";
  };
  const setTextOverride = (key: string, raw: string) => {
    setSessionConfig((prev) => {
      const next = { ...prev };
      const defaultValue = getDefault(key);
      const defaultText = defaultValue === null || defaultValue === undefined ? "" : String(defaultValue);
      if (raw === defaultText) {
        delete next[key];
      } else {
        next[key] = raw || undefined;
      }
      return next;
    });
  };
  const setNumberOverride = (key: string, raw: string) => {
    setSessionConfig((prev) => {
      const next = { ...prev };
      if (raw === "") {
        delete next[key];
        return next;
      }
      const num = Number(raw);
      if (Number.isNaN(num)) return prev;
      const defaultValue = getDefault(key);
      if (typeof defaultValue === "number" && num === defaultValue) {
        delete next[key];
      } else {
        next[key] = num;
      }
      return next;
    });
  };
  const setSelectOverride = (key: string, raw: string) => {
    setSessionConfig((prev) => {
      const next = { ...prev };
      const defaultValue = String(getDefault(key) ?? "");
      if (raw === defaultValue) {
        delete next[key];
      } else {
        next[key] = raw;
      }
      return next;
    });
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center" onClick={handleClose}>
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-lg mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">Configure Agents</h2>
          <button onClick={handleClose} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Agent rows */}
        <div className="max-h-[50vh] overflow-y-auto px-4 py-3 space-y-3">
          {agents.map((agent, index) => {
            const isDuplicate = duplicates.has(index);
            const isEmpty = !agent.name.trim();
            const agentColor = AGENT_COLORS[agent.type] || "text-zinc-400";

            return (
              <div key={index} className="flex flex-col gap-2 p-3 rounded-lg bg-zinc-800/50 border border-zinc-800">
                <div className="flex items-center gap-2">
                  {/* Type select */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className={agentColor}>
                      <AgentIcon agent={agent.type} size={14} />
                    </span>
                    <select
                      value={agent.type}
                      onChange={(e) => handleTypeChange(index, e.target.value)}
                      className="bg-zinc-700 border border-zinc-600 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500 appearance-none cursor-pointer"
                    >
                      {AGENT_TYPES.map(t => (
                        <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                      ))}
                    </select>
                  </div>

                  {/* Name input */}
                  <input
                    type="text"
                    value={agent.name}
                    onChange={(e) => updateAgent(index, { name: e.target.value })}
                    placeholder="Agent name"
                    className={`flex-1 min-w-0 px-2 py-1 bg-zinc-700 border rounded text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-zinc-500 ${
                      isDuplicate || isEmpty ? "border-red-500/50" : "border-zinc-600"
                    }`}
                  />

                  {/* Remove button */}
                  <button
                    onClick={() => removeAgent(index)}
                    className="p-1 rounded text-zinc-500 hover:text-red-400 hover:bg-zinc-700 transition-colors shrink-0"
                    title="Remove agent"
                  >
                    <X size={14} />
                  </button>
                </div>

                {/* Role input */}
                <input
                  type="text"
                  value={agent.role}
                  onChange={(e) => updateAgent(index, { role: e.target.value })}
                  placeholder="Optional role description..."
                  className="w-full px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-xs text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
                />

                {/* Error messages */}
                {isDuplicate && (
                  <p className="text-[10px] text-red-400">Duplicate name</p>
                )}
                {isEmpty && (
                  <p className="text-[10px] text-red-400">Name cannot be empty</p>
                )}
              </div>
            );
          })}
        </div>

        {/* Add agent button */}
        <div className="px-4 pb-3">
          <button
            onClick={addAgent}
            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <Plus size={14} />
            <span>Add Agent</span>
          </button>
        </div>

        {/* Session-level config overrides */}
        <details className="px-4 pb-3">
          <summary className="text-xs text-zinc-500 cursor-pointer hover:text-zinc-300 transition-colors">
            Session Settings (Overrides)
          </summary>
          <div className="mt-2 space-y-3">
            <p className="text-[10px] text-zinc-500">
              Leave blank to use defaults.
            </p>
            {settingsError && (
              <p className="text-[10px] text-yellow-400">{settingsError}</p>
            )}

            <div className="space-y-2">
              <p className="text-[10px] text-zinc-400 uppercase tracking-wide">Agent Models</p>
              {AGENT_TYPES.map(type => {
                const key = `agents.${type}.model`;
                return (
                  <div key={key} className="flex items-center gap-2">
                    <span className="text-xs text-zinc-400 capitalize w-14">{type}</span>
                    <input
                      type="text"
                      value={getResolvedText(key)}
                      onChange={(e) => setTextOverride(key, e.target.value)}
                      className="flex-1 px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-zinc-500"
                    />
                  </div>
                );
              })}
            </div>

            <div className="space-y-2">
              <p className="text-[10px] text-zinc-400 uppercase tracking-wide">Agent System Prompts</p>
              {AGENT_TYPES.map(type => {
                const key = `agents.${type}.system_prompt`;
                return (
                  <div key={key} className="flex items-start gap-2">
                    <span className="text-xs text-zinc-400 capitalize w-14 pt-1">{type}</span>
                    <textarea
                      value={getResolvedText(key)}
                      onChange={(e) => setTextOverride(key, e.target.value)}
                      rows={2}
                      className="flex-1 px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-zinc-500 font-mono resize-y"
                    />
                  </div>
                );
              })}
            </div>

            <div className="space-y-2">
              <p className="text-[10px] text-zinc-400 uppercase tracking-wide">Agent Permissions</p>
              {AGENT_TYPES.map(type => {
                const key = `agents.${type}.permissions`;
                const defaultValue = String(getDefault(key) ?? "bypass");
                const current = String(getResolved(key) ?? defaultValue);
                return (
                  <div key={key} className="flex items-center gap-2">
                    <span className="text-xs text-zinc-400 capitalize w-14">{type}</span>
                    <select
                      value={current}
                      onChange={(e) => setSelectOverride(key, e.target.value)}
                      className="flex-1 px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-xs text-zinc-200 focus:outline-none focus:border-zinc-500"
                    >
                      <option value="bypass">Bypass</option>
                      <option value="auto">Auto</option>
                      <option value="manual">Manual</option>
                    </select>
                  </div>
                );
              })}
            </div>

            <div className="space-y-2">
              <p className="text-[10px] text-zinc-400 uppercase tracking-wide">Runtime</p>
              {[
                "timeouts.idle",
                "timeouts.parse",
                "timeouts.send",
                "timeouts.hard",
                "permissions.timeout",
              ].map((key) => (
                <div key={key} className="flex items-center gap-2">
                  <span className="text-xs text-zinc-400 w-32">{key}</span>
                  <input
                    type="number"
                    value={getResolvedNumber(key)}
                    onChange={(e) => setNumberOverride(key, e.target.value)}
                    className="flex-1 px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-zinc-500"
                  />
                </div>
              ))}
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-400 w-32">memory.model</span>
                <input
                  type="text"
                  value={getResolvedText("memory.model")}
                  onChange={(e) => setTextOverride("memory.model", e.target.value)}
                  className="flex-1 px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-xs text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-zinc-500"
                />
              </div>
            </div>
          </div>
        </details>

        {/* Footer */}
        <div className="border-t border-zinc-800 px-4 py-3 flex items-center gap-2">
          <button
            onClick={() => {
              if (!canStart) return;
              const config = Object.fromEntries(
                Object.entries(sessionConfig).filter(([, v]) => v !== undefined && v !== "")
              );
              onStart(agents, Object.keys(config).length > 0 ? config : undefined);
            }}
            disabled={!canStart}
            className="flex-1 px-3 py-2 bg-zinc-700 hover:bg-zinc-600 rounded text-sm text-zinc-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Start Chat
          </button>
          <button
            onClick={handleClose}
            className="px-3 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
