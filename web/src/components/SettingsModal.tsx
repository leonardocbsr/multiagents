import { useState, useEffect, useCallback, useRef } from "react";
import { RotateCcw } from "lucide-react";
import { useSettings } from "../hooks/useSettings";
import MemoryManagementPanel from "./MemoryManagementPanel";
import { Button, FieldRow, Input, Modal, Panel, Select, Switch, Tabs, Textarea } from "./ui";

interface Props {
  open: boolean;
  onClose: () => void;
}

type Tab = "agents" | "permissions" | "features" | "timeouts" | "memory" | "advanced";

const AGENT_TYPES = ["claude", "codex", "kimi"] as const;

export default function SettingsModal({ open, onClose }: Props) {
  const { settings, loading, error, update, reset } = useSettings();
  const [tab, setTab] = useState<Tab>("agents");
  const [dirty, setDirty] = useState<Record<string, unknown>>({});
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) setDirty({});
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open || !modalRef.current) return;
    const root = modalRef.current;
    const focusable = root.querySelectorAll<HTMLElement>(
      'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])',
    );
    focusable[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = Array.from(focusable).filter((el) => !el.hasAttribute("disabled"));
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

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
    { id: "permissions", label: "Permissions" },
    { id: "features", label: "Features" },
    { id: "timeouts", label: "Timeouts" },
    { id: "memory", label: "Memory" },
    { id: "advanced", label: "Advanced" },
  ];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Settings"
      className="max-w-lg h-[78vh]"
      footer={(
        <div className="flex flex-col gap-2">
          {error && (
            <p className="text-xs text-ui-danger px-1">{error}</p>
          )}
          <div className="flex items-center gap-2">
            <Button onClick={handleSave} className="flex-1">
              {Object.keys(dirty).length > 0 ? "Save & Close" : "Close"}
            </Button>
            <Button onClick={onClose} variant="ghost">Cancel</Button>
          </div>
        </div>
      )}
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        onClick={(e) => e.stopPropagation()}
        className="h-full flex flex-col"
      >
        <Tabs items={tabs} value={tab} onChange={setTab} className="pb-3 shrink-0" />
        <div className="space-y-4 flex-1 min-h-0 overflow-y-auto pr-1">
          {loading && <p className="text-xs text-ui-subtle">Loading...</p>}

          {!loading && tab === "agents" && (
            <>
              {AGENT_TYPES.map(type => {
                const modelKey = `agents.${type}.model`;
                const promptKey = `agents.${type}.system_prompt`;
                const model = getValue(modelKey) as string | null;
                const prompt = getValue(promptKey) as string | null;
                return (
                  <Panel key={type} className="space-y-2 bg-ui-elevated">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-ui capitalize">{type}</span>
                    </div>
                    <div>
                      <label className="text-[10px] text-ui-subtle uppercase tracking-wide">Model</label>
                      <div className="flex items-center gap-1">
                        <Input
                          type="text"
                          value={model || ""}
                          onChange={(e) => setField(modelKey, e.target.value || null)}
                          placeholder="CLI default"
                          className="flex-1 text-xs"
                        />
                        {model && (
                          <Button onClick={() => handleReset(modelKey)} variant="ghost" size="sm" title="Reset to default" icon={<RotateCcw size={12} />} />
                        )}
                      </div>
                    </div>
                    <div>
                      <label className="text-[10px] text-ui-subtle uppercase tracking-wide">Base System Prompt</label>
                      <div className="flex items-start gap-1">
                        <Textarea
                          value={prompt || ""}
                          onChange={(e) => setField(promptKey, e.target.value || null)}
                          placeholder="Default prompt"
                          rows={3}
                          className="flex-1 text-xs font-mono"
                        />
                        {prompt && (
                          <Button onClick={() => handleReset(promptKey)} variant="ghost" size="sm" className="mt-0.5" title="Reset to default" icon={<RotateCcw size={12} />} />
                        )}
                      </div>
                    </div>
                  </Panel>
                );
              })}
            </>
          )}

          {!loading && tab === "permissions" && (
            <>
              {AGENT_TYPES.map(type => {
                const key = `agents.${type}.permissions`;
                const value = (getValue(key) as string) || "bypass";
                return (
                  <FieldRow
                    key={type}
                    label={type}
                    description={type === "codex" ? "Policy-based only (no per-tool blocking)" : "Permission mode for tool use"}
                    className="capitalize"
                    control={(
                    <Select
                      value={value}
                      onChange={(e) => setField(key, e.target.value)}
                      className="w-32"
                    >
                      <option value="bypass">Bypass All</option>
                      <option value="auto">Auto (Smart)</option>
                      <option value="manual">Ask User</option>
                    </Select>
                    )}
                  />
                );
              })}
              <FieldRow
                label="Permission Timeout"
                description="Seconds before pending requests auto-deny (0 = no timeout)"
                control={(
                <div className="flex items-center gap-1">
                  <Input
                    type="number"
                    value={(() => {
                      const raw = getValue("permissions.timeout");
                      return typeof raw === "string" || typeof raw === "number" ? raw : raw ?? "";
                    })() as string | number}
                    onChange={(e) => {
                      const raw = e.target.value;
                      if (raw === "") { setField("permissions.timeout", ""); return; }
                      const num = Number(raw);
                      if (!Number.isNaN(num)) setField("permissions.timeout", num);
                    }}
                    className="w-20 text-xs text-right"
                  />
                  <span className="text-[10px] text-ui-subtle w-3">s</span>
                </div>
                )}
              />
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
                <FieldRow key={key} label={label} description={desc} control={(
                  <div className="flex items-center gap-1">
                    <Input
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
                      className="w-20 text-xs text-right"
                    />
                    <span className="text-[10px] text-ui-subtle w-3">{unit}</span>
                  </div>
                )} />
              );
              })}
            </>
          )}

          {!loading && tab === "features" && (
            <>
              <Panel className="space-y-3 bg-ui-elevated">
                <div className="pb-2 border-b border-ui">
                  <div className="flex items-center gap-2">
                    <p className="text-[10px] text-ui-subtle uppercase tracking-wide">Layout</p>
                    <span className="inline-flex items-center rounded-full border border-ui-warn-soft bg-ui-warn-soft px-2 py-0.5 text-[9px] font-mono uppercase tracking-[0.08em] text-ui-warn">
                      Deprecated
                    </span>
                  </div>
                </div>
                <FieldRow
                  label="Enable Split Layout"
                  description="Disable to force chat-only mode for all users."
                  control={(
                    <div className="flex items-center gap-2">
                      <Switch checked={getValue("ui.layout.split_enabled") !== false} onChange={(next) => setField("ui.layout.split_enabled", next)} />
                      <Button onClick={() => handleReset("ui.layout.split_enabled")} variant="ghost" size="sm" title="Reset to default" icon={<RotateCcw size={12} />} />
                    </div>
                  )}
                />

                <FieldRow
                  label="Allow Layout Switching"
                  description="Show or hide the Split/Chat toggle in the header."
                  control={(
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={getValue("ui.layout.allow_switch") !== false}
                        onChange={(next) => setField("ui.layout.allow_switch", next)}
                        disabled={getValue("ui.layout.split_enabled") === false}
                      />
                      <Button onClick={() => handleReset("ui.layout.allow_switch")} variant="ghost" size="sm" title="Reset to default" icon={<RotateCcw size={12} />} />
                    </div>
                  )}
                />

                <FieldRow label="Default Layout" description="Layout used when switching is disabled." control={(
                  <div className="flex items-center gap-1">
                    <Select
                      value={(getValue("ui.layout.default") as string) === "chat" ? "chat" : "split"}
                      onChange={(e) => setField("ui.layout.default", e.target.value)}
                      disabled={getValue("ui.layout.split_enabled") === false}
                      className="w-28"
                    >
                      <option value="split">Split</option>
                      <option value="chat">Chat</option>
                    </Select>
                    <Button onClick={() => handleReset("ui.layout.default")} variant="ghost" size="sm" title="Reset to default" icon={<RotateCcw size={12} />} />
                  </div>
                )} />
              </Panel>
              <Panel className="space-y-3 bg-ui-elevated">
                <div className="pb-2 border-b border-ui">
                  <p className="text-[10px] text-ui-subtle uppercase tracking-wide">Appearance</p>
                </div>
                <FieldRow label="Theme Mode" description="Choose dark, light, or follow system." control={(
                  <div className="flex items-center gap-1">
                    <Select
                      value={(() => {
                        const raw = getValue("ui.theme.mode");
                        return raw === "light" || raw === "system" ? raw : "dark";
                      })()}
                      onChange={(e) => setField("ui.theme.mode", e.target.value)}
                      className="w-28"
                    >
                      <option value="dark">Dark</option>
                      <option value="light">Light</option>
                      <option value="system">System</option>
                    </Select>
                    <Button onClick={() => handleReset("ui.theme.mode")} variant="ghost" size="sm" title="Reset to default" icon={<RotateCcw size={12} />} />
                  </div>
                )} />
                <FieldRow label="Accent" description="Primary accent for highlights and actions." control={(
                  <div className="flex items-center gap-1">
                    <Select
                      value={(() => {
                        const raw = getValue("ui.theme.accent");
                        return raw === "emerald" || raw === "amber" ? raw : "cyan";
                      })()}
                      onChange={(e) => setField("ui.theme.accent", e.target.value)}
                      className="w-28"
                    >
                      <option value="cyan">Cyan</option>
                      <option value="emerald">Emerald</option>
                      <option value="amber">Amber</option>
                    </Select>
                    <Button onClick={() => handleReset("ui.theme.accent")} variant="ghost" size="sm" title="Reset to default" icon={<RotateCcw size={12} />} />
                  </div>
                )} />
                <FieldRow label="Density" description="Compact packs more content; cozy adds breathing room." control={(
                  <div className="flex items-center gap-1">
                    <Select
                      value={(getValue("ui.theme.density") as string) === "compact" ? "compact" : "cozy"}
                      onChange={(e) => setField("ui.theme.density", e.target.value)}
                      className="w-28"
                    >
                      <option value="compact">Compact</option>
                      <option value="cozy">Cozy</option>
                    </Select>
                    <Button onClick={() => handleReset("ui.theme.density")} variant="ghost" size="sm" title="Reset to default" icon={<RotateCcw size={12} />} />
                  </div>
                )} />
              </Panel>
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
                <FieldRow key={key} label={label} description={desc} control={(
                  <Input
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
                    className="w-28 text-xs text-right"
                  />
                )} />
              );
              })}
            </>
          )}

          {tab === "memory" && (
            <MemoryManagementPanel active={open && tab === "memory"} />
          )}
        </div>
      </div>
    </Modal>
  );
}
