import { useState, useEffect, useCallback } from "react";
import { X, RotateCcw } from "lucide-react";
import { useSettings } from "../hooks/useSettings";

interface Props {
  open: boolean;
  onClose: () => void;
}

type Tab = "agents" | "timeouts" | "advanced";

const AGENT_TYPES = ["claude", "codex", "kimi"] as const;

export default function SettingsModal({ open, onClose }: Props) {
  const { settings, loading, error, update, reset } = useSettings();
  const [tab, setTab] = useState<Tab>("agents");
  const [dirty, setDirty] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (open) setDirty({});
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const getValue = useCallback((key: string) => {
    if (key in dirty) return dirty[key];
    return settings?.[key] ?? null;
  }, [dirty, settings]);

  const setField = useCallback((key: string, value: unknown) => {
    setDirty(prev => ({ ...prev, [key]: value }));
  }, []);

  const handleSave = useCallback(async () => {
    const entries = Object.entries(dirty);
    if (entries.length > 0) {
      const resetKeys = entries.filter(([, value]) => value === "").map(([key]) => key);
      const updates = Object.fromEntries(entries.filter(([, value]) => value !== ""));
      if (resetKeys.length > 0) {
        for (const key of resetKeys) {
          await reset(key);
        }
      }
      if (Object.keys(updates).length > 0) {
        const ok = await update(updates);
        if (!ok) return;
      }
      setDirty({});
    }
    onClose();
  }, [dirty, update, reset, onClose]);

  const handleReset = useCallback(async (key: string) => {
    await reset(key);
    setDirty(prev => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, [reset]);

  if (!open) return null;

  const tabs: { id: Tab; label: string }[] = [
    { id: "agents", label: "Agents" },
    { id: "timeouts", label: "Timeouts" },
    { id: "advanced", label: "Advanced" },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center" onClick={onClose}>
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-lg mx-4 shadow-2xl max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0">
          <h2 className="text-sm font-medium text-zinc-200">Settings</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-4 pt-3 shrink-0">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded text-xs transition-colors ${
                tab === t.id ? "bg-zinc-700 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
          {loading && <p className="text-xs text-zinc-500">Loading...</p>}

          {!loading && tab === "agents" && (
            <>
              {AGENT_TYPES.map(type => {
                const modelKey = `agents.${type}.model`;
                const promptKey = `agents.${type}.system_prompt`;
                const model = getValue(modelKey) as string | null;
                const prompt = getValue(promptKey) as string | null;
                return (
                  <div key={type} className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-800 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-zinc-300 capitalize">{type}</span>
                    </div>
                    <div>
                      <label className="text-[10px] text-zinc-500 uppercase tracking-wide">Model</label>
                      <div className="flex items-center gap-1">
                        <input
                          type="text"
                          value={model || ""}
                          onChange={(e) => setField(modelKey, e.target.value || null)}
                          placeholder="CLI default"
                          className="flex-1 px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
                        />
                        {model && (
                          <button onClick={() => handleReset(modelKey)} className="p-1 text-zinc-500 hover:text-zinc-300" title="Reset to default">
                            <RotateCcw size={12} />
                          </button>
                        )}
                      </div>
                    </div>
                    <div>
                      <label className="text-[10px] text-zinc-500 uppercase tracking-wide">Base System Prompt</label>
                      <div className="flex items-start gap-1">
                        <textarea
                          value={prompt || ""}
                          onChange={(e) => setField(promptKey, e.target.value || null)}
                          placeholder="Default prompt"
                          rows={3}
                          className="flex-1 px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 font-mono resize-y"
                        />
                        {prompt && (
                          <button onClick={() => handleReset(promptKey)} className="p-1 text-zinc-500 hover:text-zinc-300 mt-0.5" title="Reset to default">
                            <RotateCcw size={12} />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {!loading && tab === "timeouts" && (
            <>
              {[
                { key: "timeouts.idle", label: "Idle Timeout", desc: "Seconds before an agent is considered stalled", unit: "s" },
                { key: "timeouts.parse", label: "Parse Timeout", desc: "Seconds to wait for output parsing", unit: "s" },
                { key: "timeouts.send", label: "Send Timeout", desc: "WebSocket send timeout", unit: "s" },
                { key: "timeouts.hard", label: "Hard Timeout", desc: "Absolute max runtime per agent (0 = disabled)", unit: "s" },
              ].map(({ key, label, desc, unit }) => {
                const rawValue = getValue(key);
                const inputValue = typeof rawValue === "string" || typeof rawValue === "number" ? rawValue : rawValue ?? "";
                return (
                <div key={key} className="flex items-center gap-3">
                  <div className="flex-1">
                    <label className="text-xs text-zinc-300">{label}</label>
                    <p className="text-[10px] text-zinc-600">{desc}</p>
                  </div>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      value={inputValue as string | number}
                      onChange={(e) => {
                        const raw = e.target.value;
                        if (raw === "") {
                          setField(key, "");
                          return;
                        }
                        const num = Number(raw);
                        if (Number.isNaN(num)) return;
                        setField(key, num);
                      }}
                      className="w-20 px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-xs text-zinc-200 text-right focus:outline-none focus:border-zinc-500"
                    />
                    <span className="text-[10px] text-zinc-500 w-3">{unit}</span>
                  </div>
                </div>
              );
              })}
            </>
          )}

          {!loading && tab === "advanced" && (
            <>
              {[
                { key: "memory.model", label: "Memory Model", desc: "Model used for memory summarization", type: "text" as const },
                { key: "server.warmup_ttl", label: "Warmup TTL", desc: "Idle seconds before warmed agents are cleaned up", type: "number" as const },
                { key: "server.max_events", label: "Max Events", desc: "Maximum events stored per session", type: "number" as const },
              ].map(({ key, label, desc, type }) => {
                const rawValue = getValue(key);
                const inputValue = typeof rawValue === "string" || typeof rawValue === "number" ? rawValue : rawValue ?? "";
                return (
                <div key={key} className="flex items-center gap-3">
                  <div className="flex-1">
                    <label className="text-xs text-zinc-300">{label}</label>
                    <p className="text-[10px] text-zinc-600">{desc}</p>
                  </div>
                  <input
                    type={type}
                    value={inputValue as string | number}
                    onChange={(e) => {
                      const raw = e.target.value;
                      if (type === "number") {
                        if (raw === "") {
                          setField(key, "");
                          return;
                        }
                        const num = Number(raw);
                        if (Number.isNaN(num)) return;
                        setField(key, num);
                        return;
                      }
                      setField(key, raw);
                    }}
                    className="w-28 px-2 py-1 bg-zinc-700 border border-zinc-600 rounded text-xs text-zinc-200 text-right focus:outline-none focus:border-zinc-500"
                  />
                </div>
              );
              })}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-zinc-800 px-4 py-3 flex flex-col gap-2 shrink-0">
          {error && (
            <p className="text-xs text-red-400 px-1">{error}</p>
          )}
          <div className="flex items-center gap-2">
          <button
            onClick={handleSave}
            className="flex-1 px-3 py-2 bg-zinc-700 hover:bg-zinc-600 rounded text-sm text-zinc-200 transition-colors"
          >
            {Object.keys(dirty).length > 0 ? "Save & Close" : "Close"}
          </button>
          <button onClick={onClose} className="px-3 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors">
            Cancel
          </button>
          </div>
        </div>
      </div>
    </div>
  );
}
