import { useState, useEffect, useRef, useCallback } from "react";
import { Plus } from "lucide-react";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";
import type { AppState } from "../types";
import { Button, Input, Select } from "./ui";

interface Props {
  state: AppState;
  onStopAgent?: (agent: string) => void;
  onRemoveAgent?: (name: string) => void;
  onAddAgent?: (name: string, agentType: string, role: string) => void;
  className?: string;
}

const STATUS_DOTS: Record<string, string> = {
  idle: "dot-status-idle",
  streaming: "dot-status-streaming",
  done: "dot-status-done",
  failed: "dot-status-failed",
};

const DEFAULT_STATUS_DOT = "dot-status-idle";
const STATUS_DOT_ANIM_CLASSES: Record<string, string> = {
  idle: "status-breathe-idle",
  streaming: "status-breathe-streaming",
  done: "status-breathe-done",
  failed: "status-breathe-failed",
};
const DEFAULT_STATUS_DOT_ANIM_CLASS = "status-breathe-idle";

const AGENT_TYPES = ["claude", "codex", "kimi"] as const;

function generateUniqueAgentName(type: string, existing: { name: string }[]): string {
  const base = type.charAt(0).toUpperCase() + type.slice(1);
  const existingNames = new Set(existing.map((a) => a.name.toLowerCase()));
  if (!existingNames.has(base.toLowerCase())) return base;
  for (let i = 2; ; i++) {
    const candidate = `${base}-${i}`;
    if (!existingNames.has(candidate.toLowerCase())) return candidate;
  }
}

export default function AgentStatusBar({ state, onStopAgent, onRemoveAgent, onAddAgent, className }: Props) {
  const [activePopover, setActivePopover] = useState<string | null>(null);
  const [showAddPopover, setShowAddPopover] = useState(false);
  const [newType, setNewType] = useState<string>("claude");
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState("");
  const [pinned, setPinned] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem("pinned-agents");
      return new Set(raw ? JSON.parse(raw) as string[] : []);
    } catch {
      return new Set();
    }
  });
  const popoverRef = useRef<HTMLDivElement>(null);
  const addRef = useRef<HTMLDivElement>(null);
  const addPopoverRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const agentBadgeRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const handleOutsideClick = useCallback((e: MouseEvent) => {
    const target = e.target as Node;
    if (activePopover && popoverRef.current && !popoverRef.current.contains(target)) {
      setActivePopover(null);
    }
    if (showAddPopover) {
      const inButton = addRef.current?.contains(target);
      const inPopover = addPopoverRef.current?.contains(target);
      if (!inButton && !inPopover) {
        setShowAddPopover(false);
      }
    }
  }, [activePopover, showAddPopover]);

  useEffect(() => {
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [handleOutsideClick]);

  const handleAdd = () => {
    const name = newName.trim() || generateUniqueAgentName(newType, state.agents);
    if (onAddAgent) {
      onAddAgent(name, newType, newRole.trim());
    }
    setNewName("");
    setNewRole("");
    setNewType("claude");
    setShowAddPopover(false);
  };

  useEffect(() => {
    try {
      localStorage.setItem("pinned-agents", JSON.stringify(Array.from(pinned)));
    } catch {}
  }, [pinned]);

  if (state.agents.length === 0 && !onAddAgent) return null;

  const sortedAgents = [...state.agents].sort((a, b) => {
    const ap = pinned.has(a.name) ? 0 : 1;
    const bp = pinned.has(b.name) ? 0 : 1;
    if (ap !== bp) return ap - bp;
    return a.name.localeCompare(b.name);
  });

  const previewName = newName.trim() || generateUniqueAgentName(newType, state.agents);
  const nameCollision = state.agents.some((a) => a.name.toLowerCase() === previewName.toLowerCase());

  return (
    <div className={`flex items-center gap-1.5 min-w-0 flex-1 ${className ?? ""}`}>
      <div className="relative w-full flex items-center gap-1.5">
        <div
          ref={scrollerRef}
          className="relative flex items-center gap-1.5 overflow-x-auto whitespace-nowrap flex-1 min-w-0"
        >
          {sortedAgents.map((agentInfo) => {
            const visualStatus = state.agentStatuses[agentInfo.name] || "idle";
            const agentColor = AGENT_COLORS[agentInfo.type] || "text-ui-muted";
            const dotClass = STATUS_DOTS[visualStatus] ?? DEFAULT_STATUS_DOT;
            const dotAnimClass = STATUS_DOT_ANIM_CLASSES[visualStatus] ?? DEFAULT_STATUS_DOT_ANIM_CLASS;

            return (
              <div
                key={agentInfo.name}
                ref={(el) => { agentBadgeRefs.current[agentInfo.name] = el; }}
                onClick={() => setActivePopover(activePopover === agentInfo.name ? null : agentInfo.name)}
                className="relative flex items-center gap-1.5 px-2 py-1 rounded-full shrink-0 cursor-pointer transition-colors border border-ui"
                title={agentInfo.name}
              >
                <span className={agentColor}>
                  <AgentIcon agent={agentInfo.type} size={12} />
                </span>
                <span className="text-[11px] font-medium text-ui">{agentInfo.name}</span>
                <div className={`w-2 h-2 rounded-full border border-ui-strong ${dotClass} ${dotAnimClass}`} />
              </div>
            );
          })}

          {onAddAgent && (
            <div className="shrink-0" ref={addRef}>
              <Button
                onClick={() => setShowAddPopover(!showAddPopover)}
                variant="ghost"
                size="sm"
                className="w-6 h-6 !p-0 border border-dashed border-ui-dashed text-ui-subtle hover:text-ui hover:bg-ui-elevated rounded-full"
                title="Add agent"
              >
                <Plus size={11} />
              </Button>
            </div>
          )}
        </div>
        {/* Agent action popover */}
        {activePopover && (() => {
          const badge = agentBadgeRefs.current[activePopover];
          const status = state.agentStatuses[activePopover] || "idle";
          if (!badge) return null;
          return (
            <div
              ref={popoverRef}
              className="ui-panel absolute top-full mt-1 z-50 bg-ui-elevated border-ui-strong shadow-xl py-1 min-w-[120px] p-0"
              style={{ left: badge.offsetLeft }}
            >
              {status === "streaming" && onStopAgent && (
                <Button
                  onClick={(e) => { e.stopPropagation(); onStopAgent(activePopover); setActivePopover(null); }}
                  variant="ghost"
                  className="w-full justify-start rounded-none px-3 py-1.5 text-xs text-ui-warn hover:bg-ui-soft"
                >
                  Stop
                </Button>
              )}
              <Button
                onClick={(e) => {
                  e.stopPropagation();
                  setPinned((prev) => {
                    const next = new Set(prev);
                    if (next.has(activePopover)) next.delete(activePopover);
                    else next.add(activePopover);
                    return next;
                  });
                  setActivePopover(null);
                }}
                variant="ghost"
                className="w-full justify-start rounded-none px-3 py-1.5 text-xs text-ui hover:bg-ui-soft"
              >
                {pinned.has(activePopover) ? "Unpin" : "Pin"}
              </Button>
              {onRemoveAgent && (
                <Button
                  onClick={(e) => { e.stopPropagation(); onRemoveAgent(activePopover); setActivePopover(null); }}
                  variant="ghost"
                  className="w-full justify-start rounded-none px-3 py-1.5 text-xs text-ui-danger hover:bg-ui-soft"
                >
                  Remove
                </Button>
              )}
            </div>
          );
        })()}
        {showAddPopover && addRef.current && (
          <div
            ref={addPopoverRef}
            className="ui-panel absolute top-full mt-1 z-50 bg-ui-elevated border-ui-strong shadow-xl p-3 min-w-[200px]"
            style={{ left: addRef.current.offsetLeft }}
          >
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className={AGENT_COLORS[newType] || "text-ui-muted"}>
                  <AgentIcon agent={newType} size={12} />
                </span>
                <Select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value)}
                  className="flex-1 text-xs"
                >
                  {AGENT_TYPES.map(t => (
                    <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                  ))}
                </Select>
              </div>
              <Input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Name (auto)"
                className="w-full text-xs"
              />
              <Input
                type="text"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                placeholder="Role (optional)"
                className="w-full text-xs"
              />
              <div className="text-[10px] text-ui-subtle">
                Final name: <span className="text-ui">{previewName}</span>
              </div>
              {nameCollision && (
                <div className="text-[10px] text-ui-danger">Name already exists</div>
              )}
              <Button
                onClick={handleAdd}
                disabled={nameCollision}
                className="w-full text-xs"
              >
                Add
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
