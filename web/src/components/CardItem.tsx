import { useState } from "react";
import { Play, Check, Users, Trash2 } from "lucide-react";
import type { AgentInfo, Card } from "../types";
import { AgentIcon, AGENT_COLORS, AGENT_AVATAR_CLASSES } from "./AgentIcons";
import { Button, Modal } from "./ui";

interface Props {
  card: Card;
  agents: AgentInfo[];
  isRunning: boolean;
  onStart: () => void;
  onDelegate: () => void;
  onMarkDone: () => void;
  onDelete: () => void;
  onUpdate: (fields: { title?: string; description?: string; planner?: string; implementer?: string; reviewer?: string; coordinator?: string }) => void;
}

function resolveAgentType(agentName: string, agents: AgentInfo[]): string {
  const normalized = agentName.toLowerCase();
  const info = agents.find((a) => a.name.toLowerCase() === normalized);
  return info?.type ?? agentName;
}

/** Agent roles to show as icons, in display order */
const ROLE_ORDER: { key: "coordinator" | "planner" | "implementer" | "reviewer"; letter: string }[] = [
  { key: "coordinator", letter: "C" },
  { key: "planner", letter: "P" },
  { key: "implementer", letter: "I" },
  { key: "reviewer", letter: "R" },
];

export default function CardItem({ card, agents, onStart, onDelegate, onMarkDone, onDelete }: Props) {
  const [showModal, setShowModal] = useState(false);

  // Collect assigned roles for the icon row
  const assignedRoles = ROLE_ORDER.filter((r) => card[r.key]).map((r) => ({
    ...r,
    agent: card[r.key]!,
    type: resolveAgentType(card[r.key]!, agents),
  }));

  return (
    <>
      {/* Compact card — title + agent icons */}
      <button
        onClick={() => setShowModal(true)}
        className="w-full text-left transition-colors cursor-pointer group"
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border-medium)',
          borderRadius: '10px',
          padding: '12px 14px',
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-active)'; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-medium)'; }}
      >
        <div className="text-[12.5px] font-medium text-ui ui-clamp-2 leading-tight">{card.title}</div>
        {assignedRoles.length > 0 && (
          <div className="flex items-center gap-1 mt-2">
            {assignedRoles.map((r) => (
              <div
                key={r.key}
                className={`w-5 h-5 rounded-full flex items-center justify-center border ${AGENT_AVATAR_CLASSES[r.type] ?? ""}`}
                title={`${r.letter}: ${r.agent}`}
                style={{ borderWidth: '1.5px' }}
              >
                <span className={AGENT_COLORS[r.type] ?? "text-ui-muted"}>
                  <AgentIcon agent={r.type} size={9} />
                </span>
              </div>
            ))}
          </div>
        )}
      </button>

      {/* Detail modal */}
      <Modal
        open={showModal}
        onClose={() => setShowModal(false)}
        title={card.title}
        className="max-w-md"
        footer={(
          <div className="flex items-center gap-2">
            {card.status === "backlog" && (
              <>
                <ActionButton onClick={() => { onStart(); setShowModal(false); }} icon={<Play size={12} />} label="Start" variant="primary" />
                <ActionButton onClick={() => { onDelegate(); setShowModal(false); }} icon={<Users size={12} />} label="Delegate" variant="secondary" />
              </>
            )}
            {card.status === "reviewing" && (
              <ActionButton onClick={() => { onMarkDone(); setShowModal(false); }} icon={<Check size={12} />} label="Mark Done" variant="success" />
            )}
            <div className="flex-1" />
            <ActionButton onClick={() => { onDelete(); setShowModal(false); }} icon={<Trash2 size={12} />} label="Delete" variant="danger" />
          </div>
        )}
      >
        <div className="space-y-4">
          {/* Description */}
          {card.description && (
            <p className="text-xs text-ui-muted whitespace-pre-wrap leading-relaxed">{card.description}</p>
          )}

          {/* Role assignments */}
          <div className="space-y-1.5">
            {ROLE_ORDER.map((r) => {
              const agent = card[r.key];
              if (!agent) return null;
              const resolved = resolveAgentType(agent, agents);
              return (
                <div key={r.key} className="flex items-center gap-2 text-xs">
                  <span className="text-ui-subtle w-20 shrink-0 font-mono text-[10px] uppercase tracking-wider">{r.key}</span>
                  <span className="flex items-center gap-1.5">
                    <span className={AGENT_COLORS[resolved] ?? "text-ui-muted"}>
                      <AgentIcon agent={resolved} size={12} />
                    </span>
                    <span className="text-ui capitalize">{agent}</span>
                  </span>
                </div>
              );
            })}
          </div>

          {/* History */}
          {card.history.length > 0 && (
            <div>
              <div className="text-[10px] font-mono text-ui-subtle uppercase tracking-wider mb-1.5">History</div>
              <div className="space-y-1">
                {card.history.map((entry, i) => (
                  <div key={i} className="text-[10px] text-ui-subtle pl-3 border-l border-ui-soft">
                    <span className="font-medium text-ui-muted">{entry.phase}</span>
                    {" "}
                    <span className={AGENT_COLORS[resolveAgentType(entry.agent, agents)] ?? "text-ui-muted"}>{entry.agent}</span>
                    {entry.content && (
                      <span className="text-ui-faint"> — {entry.content.slice(0, 100)}{entry.content.length > 100 ? "..." : ""}</span>
                    )}
                    <div className="text-ui-faint">{formatTimestamp(entry.timestamp)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}

function ActionButton({ onClick, icon, label, variant }: {
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  variant: "primary" | "secondary" | "success" | "danger";
}) {
  const styles = {
    primary: "btn-ui-info text-ui-on-solid",
    secondary: "bg-ui-soft hover:bg-ui-soft text-ui",
    success: "btn-ui-success text-ui-on-solid",
    danger: "text-ui-danger hover:text-ui-danger bg-ui-danger-soft",
  };
  return (
    <Button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      size="sm"
      className={`ui-btn flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium ${styles[variant]}`}
    >
      {icon}
      {label}
    </Button>
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
