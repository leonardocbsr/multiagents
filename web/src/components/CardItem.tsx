import { useState } from "react";
import { ChevronDown, ChevronRight, Play, Check, Users, Trash2 } from "lucide-react";
import type { Card } from "../types";
import { AgentIcon, AGENT_COLORS, AGENT_BG_COLORS } from "./AgentIcons";

interface Props {
  card: Card;
  agents: string[];
  isRunning: boolean;
  onStart: () => void;
  onDelegate: () => void;
  onMarkDone: () => void;
  onDelete: () => void;
  onUpdate: (fields: { title?: string; description?: string; planner?: string; implementer?: string; reviewer?: string; coordinator?: string }) => void;
}

const ACTIVE_STATUSES = new Set(["coordinating", "planning", "implementing", "reviewing"]);

function getActiveAgent(card: Card): string | null {
  if (card.status === "coordinating") return card.coordinator || null;
  if (card.status === "planning") return card.planner || null;
  if (card.status === "implementing") return card.implementer || null;
  if (card.status === "reviewing") return card.reviewer || null;
  return null;
}

export default function CardItem({ card, agents: _agents, isRunning, onStart, onDelegate, onMarkDone, onDelete }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const isActive = ACTIVE_STATUSES.has(card.status) && isRunning;
  const activeAgent = getActiveAgent(card);
  const borderColor = isActive && activeAgent ? (AGENT_BG_COLORS[activeAgent] ?? "bg-zinc-500") : "";

  const roles = [
    { key: "C", label: "Coordinator", agent: card.coordinator },
    { key: "P", label: "Planner", agent: card.planner },
    { key: "I", label: "Implementer", agent: card.implementer },
    { key: "R", label: "Reviewer", agent: card.reviewer },
  ].filter((r) => r.agent);

  return (
    <div
      className={`bg-zinc-900 border border-zinc-800 rounded-lg p-3 transition-colors ${
        isActive ? `border-l-2 ${borderColor.replace("bg-", "border-l-")} animate-pulse` : ""
      }`}
    >
      {/* Compact view */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full text-left"
      >
        <div className="flex items-start gap-2">
          <span className="text-zinc-500 mt-0.5 shrink-0">
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-zinc-200 truncate">{card.title}</div>
            {roles.length > 0 && (
              <div className="flex items-center gap-2 mt-1">
                {roles.map((r) => (
                  <span key={r.key} className="flex items-center gap-0.5 text-[10px] text-zinc-500">
                    <span className={AGENT_COLORS[r.agent] ?? "text-zinc-400"}>
                      <AgentIcon agent={r.agent} size={10} />
                    </span>
                    <span>{r.key}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </button>

      {/* Expanded view */}
      {expanded && (
        <div className="mt-3 border-t border-zinc-800 pt-3 space-y-3">
          {/* Description */}
          {card.description && (
            <p className="text-xs text-zinc-400 whitespace-pre-wrap">{card.description}</p>
          )}

          {/* Role assignments */}
          <div className="space-y-1">
            <RoleRow label="Coordinator" agent={card.coordinator} />
            <RoleRow label="Planner" agent={card.planner} />
            <RoleRow label="Implementer" agent={card.implementer} />
            <RoleRow label="Reviewer" agent={card.reviewer} />
          </div>

          {/* History */}
          {card.history.length > 0 && (
            <div>
              <button
                onClick={(e) => { e.stopPropagation(); setShowHistory((v) => !v); }}
                className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                {showHistory ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                History ({card.history.length})
              </button>
              {showHistory && (
                <div className="mt-1 space-y-1">
                  {card.history.map((entry, i) => (
                    <div key={i} className="text-[10px] text-zinc-500 pl-3 border-l border-zinc-800">
                      <span className="font-medium text-zinc-400">{entry.phase}</span>
                      {" "}
                      <span className={AGENT_COLORS[entry.agent] ?? "text-zinc-400"}>{entry.agent}</span>
                      {entry.content && (
                        <span className="text-zinc-600"> — {entry.content.slice(0, 100)}{entry.content.length > 100 ? "..." : ""}</span>
                      )}
                      <div className="text-zinc-600">{formatTimestamp(entry.timestamp)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            {card.status === "backlog" && (
              <>
                <ActionButton onClick={onStart} icon={<Play size={12} />} label="Start" variant="primary" />
                <ActionButton onClick={onDelegate} icon={<Users size={12} />} label="Delegate" variant="secondary" />
              </>
            )}
            {card.status === "reviewing" && (
              <ActionButton onClick={onMarkDone} icon={<Check size={12} />} label="Mark Done" variant="success" />
            )}
            <ActionButton onClick={onDelete} icon={<Trash2 size={12} />} label="Delete" variant="danger" />
          </div>
        </div>
      )}
    </div>
  );
}

function RoleRow({ label, agent }: { label: string; agent: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-zinc-500 w-20 shrink-0">{label}</span>
      {agent ? (
        <span className="flex items-center gap-1">
          <span className={AGENT_COLORS[agent] ?? "text-zinc-400"}>
            <AgentIcon agent={agent} size={12} />
          </span>
          <span className="text-zinc-300 capitalize">{agent}</span>
        </span>
      ) : (
        <span className="text-zinc-600">Unassigned</span>
      )}
    </div>
  );
}

function ActionButton({ onClick, icon, label, variant }: {
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  variant: "primary" | "secondary" | "success" | "danger";
}) {
  const styles = {
    primary: "bg-blue-600 hover:bg-blue-500 text-white",
    secondary: "bg-zinc-700 hover:bg-zinc-600 text-zinc-300",
    success: "bg-emerald-600 hover:bg-emerald-500 text-white",
    danger: "text-red-400/60 hover:text-red-400 hover:bg-red-500/10",
  };
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition-colors ${styles[variant]}`}
    >
      {icon}
      {label}
    </button>
  );
}

function formatTimestamp(ts: string): string {
  try {
    const date = new Date(ts);
    return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  } catch {
    return ts;
  }
}
