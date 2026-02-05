import { useState, useEffect, useCallback } from "react";
import { Plus, X } from "lucide-react";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";
import type { AgentInfo } from "../types";
import { fetchSettings } from "../api";
import { Button, Input, Modal, Panel, Select, Textarea } from "./ui";

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
  const [focusCycleTick, setFocusCycleTick] = useState(0);

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
      if (e.key === "Tab") setFocusCycleTick((n) => n + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, handleClose]);
  useEffect(() => {
    if (!open) return;
    const root = document.querySelector('[data-roster-editor="true"]');
    if (!root) return;
    const focusable = root.querySelectorAll<HTMLElement>(
      'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])',
    );
    if (focusCycleTick === 0) {
      focusable[0]?.focus();
    }
  }, [open, focusCycleTick]);

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
    <Modal
      open={open}
      onClose={handleClose}
      title="Create Session"
      className="max-w-lg"
      footer={(
        <div className="flex items-center gap-2">
          <Button
            onClick={() => {
              if (!canStart) return;
              const config = Object.fromEntries(
                Object.entries(sessionConfig).filter(([, v]) => v !== undefined && v !== "")
              );
              onStart(agents, Object.keys(config).length > 0 ? config : undefined);
            }}
            disabled={!canStart}
            className="flex-1 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Create Session
          </Button>
          <Button onClick={handleClose} variant="ghost">
            Cancel
          </Button>
        </div>
      )}
    >
      <div
        data-roster-editor="true"
        role="dialog"
        aria-modal="true"
        aria-label="Configure agents"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Agent rows */}
        <div className="max-h-[50vh] overflow-y-auto space-y-3">
          {agents.map((agent, index) => {
            const isDuplicate = duplicates.has(index);
            const isEmpty = !agent.name.trim();
            const agentColor = AGENT_COLORS[agent.type] || "text-ui-muted";

            return (
              <Panel key={index} className="flex flex-col gap-2 bg-ui-elevated">
                <div className="flex items-center gap-2">
                  {/* Type select */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className={agentColor}>
                      <AgentIcon agent={agent.type} size={14} />
                    </span>
                    <Select
                      value={agent.type}
                      onChange={(e) => handleTypeChange(index, e.target.value)}
                      className="text-xs appearance-none cursor-pointer"
                    >
                      {AGENT_TYPES.map(t => (
                        <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                      ))}
                    </Select>
                  </div>

                  {/* Name input */}
                  <Input
                    type="text"
                    value={agent.name}
                    onChange={(e) => updateAgent(index, { name: e.target.value })}
                    placeholder="Agent name"
                    className={`flex-1 min-w-0 text-xs ${
                      isDuplicate || isEmpty ? "border-ui-danger-soft" : "border-ui-strong"
                    }`}
                  />

                  {/* Remove button */}
                  <Button
                    onClick={() => removeAgent(index)}
                    variant="ghost"
                    size="sm"
                    className="p-1 text-ui-subtle hover:text-ui-danger hover:bg-ui-soft shrink-0"
                    title="Remove agent"
                    icon={<X size={14} />}
                  >
                    <span className="sr-only">Remove</span>
                  </Button>
                </div>

                {/* Role input */}
                <Input
                  type="text"
                  value={agent.role}
                  onChange={(e) => updateAgent(index, { role: e.target.value })}
                  placeholder="Optional role description..."
                  className="w-full text-xs text-ui"
                />

                {/* Error messages */}
                {isDuplicate && (
                  <p className="text-[10px] text-ui-danger">Duplicate name</p>
                )}
                {isEmpty && (
                  <p className="text-[10px] text-ui-danger">Name cannot be empty</p>
                )}
              </Panel>
            );
          })}
        </div>

        {/* Add agent button */}
        <div className="pb-3">
          <Button
            onClick={addAgent}
            variant="ghost"
            size="sm"
            className="text-ui-muted hover:text-ui"
            icon={<Plus size={14} />}
          >
            <span>Add Agent</span>
          </Button>
        </div>

        {/* Session-level config overrides */}
        <details className="pb-3">
          <summary className="text-xs text-ui-subtle cursor-pointer hover:text-ui transition-colors">
            Session Settings (Overrides)
          </summary>
          <div className="mt-2 space-y-3">
            <p className="text-[10px] text-ui-subtle">
              Leave blank to use defaults.
            </p>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-ui-faint">
                Active overrides: {Object.keys(sessionConfig).length}
              </span>
              <Button
                type="button"
                onClick={() => setSessionConfig({})}
                variant="ghost"
                size="sm"
                className="text-[10px] text-ui-muted hover:text-ui"
              >
                Reset All Overrides
              </Button>
            </div>
            {settingsError && (
              <p className="text-[10px] text-ui-warn">{settingsError}</p>
            )}

            <div className="space-y-2">
              <p className="text-[10px] text-ui-muted uppercase tracking-wide">Agent Models</p>
              {AGENT_TYPES.map(type => {
                const key = `agents.${type}.model`;
                return (
                  <div key={key} className="flex items-center gap-2">
                    <span className="text-xs text-ui-muted capitalize w-14">{type}</span>
                    <Input
                      type="text"
                      value={getResolvedText(key)}
                      onChange={(e) => setTextOverride(key, e.target.value)}
                      className="flex-1 text-xs"
                    />
                  </div>
                );
              })}
            </div>

            <div className="space-y-2">
              <p className="text-[10px] text-ui-muted uppercase tracking-wide">Agent System Prompts</p>
              {AGENT_TYPES.map(type => {
                const key = `agents.${type}.system_prompt`;
                return (
                  <div key={key} className="flex items-start gap-2">
                    <span className="text-xs text-ui-muted capitalize w-14 pt-1">{type}</span>
                    <Textarea
                      value={getResolvedText(key)}
                      onChange={(e) => setTextOverride(key, e.target.value)}
                      rows={2}
                      className="flex-1 text-xs font-mono"
                    />
                  </div>
                );
              })}
            </div>

            <div className="space-y-2">
              <p className="text-[10px] text-ui-muted uppercase tracking-wide">Agent Permissions</p>
              {AGENT_TYPES.map(type => {
                const key = `agents.${type}.permissions`;
                const defaultValue = String(getDefault(key) ?? "bypass");
                const current = String(getResolved(key) ?? defaultValue);
                return (
                  <div key={key} className="flex items-center gap-2">
                    <span className="text-xs text-ui-muted capitalize w-14">{type}</span>
                    <Select
                      value={current}
                      onChange={(e) => setSelectOverride(key, e.target.value)}
                      className="flex-1 text-xs"
                    >
                      <option value="bypass">Bypass</option>
                      <option value="auto">Auto</option>
                      <option value="manual">Manual</option>
                    </Select>
                  </div>
                );
              })}
            </div>

            <div className="space-y-2">
              <p className="text-[10px] text-ui-muted uppercase tracking-wide">Runtime</p>
              {[
                "timeouts.idle",
                "timeouts.parse",
                "timeouts.send",
                "timeouts.hard",
                "permissions.timeout",
              ].map((key) => (
                <div key={key} className="flex items-center gap-2">
                  <span className="text-xs text-ui-muted w-32">{key}</span>
                  <Input
                    type="number"
                    value={getResolvedNumber(key)}
                    onChange={(e) => setNumberOverride(key, e.target.value)}
                    className="flex-1 text-xs"
                  />
                </div>
              ))}
              <div className="flex items-center gap-2">
                <span className="text-xs text-ui-muted w-32">memory.model</span>
                <Input
                  type="text"
                  value={getResolvedText("memory.model")}
                  onChange={(e) => setTextOverride("memory.model", e.target.value)}
                  className="flex-1 text-xs"
                />
              </div>
            </div>
          </div>
        </details>
      </div>
    </Modal>
  );
}
