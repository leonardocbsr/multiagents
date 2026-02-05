import { useState, useMemo, useRef, useEffect } from "react";
import { ChevronDown, ChevronRight, ListTodo, Plus } from "lucide-react";
import type { AgentInfo, Card, CardStatus } from "../types";
import CardItem from "./CardItem";
import CardForm from "./CardForm";

interface Props {
  sessionId?: string | null;
  variant?: "sidebar" | "drawer";
  cards: Card[];
  agents: AgentInfo[];
  isRunning: boolean;
  onCreateCard: (title: string, description: string, planner?: string, implementer?: string, reviewer?: string, coordinator?: string) => void;
  onUpdateCard: (cardId: string, fields: { title?: string; description?: string; planner?: string; implementer?: string; reviewer?: string; coordinator?: string }) => void;
  onStartCard: (cardId: string) => void;
  onDelegateCard: (cardId: string) => void;
  onMarkDone: (cardId: string) => void;
  onDeleteCard: (cardId: string) => void;
}

interface SectionDef {
  status: CardStatus;
  label: string;
  labelColor: string;
}

const MIN_WIDTH = 240;
const MAX_WIDTH = 600;
const DEFAULT_WIDTH_RATIO = 0.24;
const COLLAPSED_WIDTH = 96;

const SECTIONS: SectionDef[] = [
  { status: "backlog", label: "Backlog", labelColor: "text-ui-muted" },
  { status: "coordinating", label: "Coordinating", labelColor: "text-ui-violet" },
  { status: "planning", label: "Planning", labelColor: "text-ui-muted" },
  { status: "implementing", label: "Implementing", labelColor: "text-ui-info" },
  { status: "reviewing", label: "Reviewing", labelColor: "text-ui-warn" },
  { status: "done", label: "Done", labelColor: "text-ui-success" },
];

export default function KanbanPanel({
  sessionId,
  variant = "sidebar",
  cards,
  agents,
  isRunning,
  onCreateCard,
  onUpdateCard,
  onStartCard,
  onDelegateCard,
  onMarkDone,
  onDeleteCard,
}: Props) {
  const [showForm, setShowForm] = useState(false);
  const sectionCollapsedKey = `kanban-sections-collapsed:${sessionId ?? "global"}`;
  const panelCollapsedKey = `kanban-panel-collapsed:${sessionId ?? "global"}`;
  const [sectionCollapsed, setSectionCollapsed] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem(sectionCollapsedKey) || "{}");
    } catch { return {}; }
  });
  useEffect(() => {
    try {
      setSectionCollapsed(JSON.parse(localStorage.getItem(sectionCollapsedKey) || "{}"));
    } catch {
      setSectionCollapsed({});
    }
  }, [sectionCollapsedKey]);
  useEffect(() => {
    localStorage.setItem(sectionCollapsedKey, JSON.stringify(sectionCollapsed));
  }, [sectionCollapsed, sectionCollapsedKey]);
  const [isPanelCollapsed, setIsPanelCollapsed] = useState(false);
  useEffect(() => {
    try {
      setIsPanelCollapsed(localStorage.getItem(panelCollapsedKey) === "1");
    } catch {
      setIsPanelCollapsed(false);
    }
  }, [panelCollapsedKey]);
  useEffect(() => {
    try {
      localStorage.setItem(panelCollapsedKey, isPanelCollapsed ? "1" : "0");
    } catch {}
  }, [panelCollapsedKey, isPanelCollapsed]);

  const [width, setWidth] = useState(() => {
    try {
      const stored = Number(localStorage.getItem("kanban-width"));
      if (Number.isFinite(stored)) {
        return Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, stored));
      }
    } catch {}
    const fromViewport = Math.round(window.innerWidth * DEFAULT_WIDTH_RATIO);
    return Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, fromViewport));
  });
  const isResizing = useRef(false);

  useEffect(() => {
    const onMove = (e: MouseEvent | TouchEvent) => {
      if (!isResizing.current) return;
      const clientX = "touches" in e ? e.touches[0].clientX : e.clientX;
      setWidth(Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, window.innerWidth - clientX)));
    };
    const onEnd = () => {
      if (isResizing.current) {
        isResizing.current = false;
        try {
          localStorage.setItem("kanban-width", String(width));
        } catch {}
      }
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onEnd);
    window.addEventListener("touchmove", onMove);
    window.addEventListener("touchend", onEnd);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onEnd);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onEnd);
    };
  }, [width]);

  const startResize = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    isResizing.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  const grouped = useMemo(() => {
    const groups: Record<CardStatus, Card[]> = {
      backlog: [],
      coordinating: [],
      planning: [],
      reviewing: [],
      implementing: [],
      done: [],
    };
    for (const card of cards) {
      if (groups[card.status]) {
        groups[card.status].push(card);
      }
    }
    return groups;
  }, [cards]);

  const isSectionCollapsed = (status: CardStatus) => {
    // If user explicitly set collapse state, honor it
    if (status in sectionCollapsed) return sectionCollapsed[status];
    // Auto-collapse empty sections
    if (grouped[status].length === 0) return true;
    return false;
  };

  const toggleSection = (status: CardStatus) => {
    setSectionCollapsed((prev) => ({ ...prev, [status]: !isSectionCollapsed(status) }));
  };

  const handleCreate = (title: string, description: string, planner?: string, implementer?: string, reviewer?: string, coordinator?: string) => {
    onCreateCard(title, description, planner, implementer, reviewer, coordinator);
    setShowForm(false);
  };
  const tasksSummary = `${cards.length} cards · ${cards.filter((c) => c.status !== "done").length} active`;
  const isSidebar = variant === "sidebar";
  const effectiveWidth = isSidebar ? (isPanelCollapsed ? COLLAPSED_WIDTH : width) : undefined;

  return (
    <div
      style={isSidebar ? { width: effectiveWidth } : undefined}
      className={`${isSidebar ? "shrink-0 border-l" : ""} border-ui-soft flex flex-col h-full bg-ui-surface overflow-hidden relative`}
    >
      {/* Resize handle */}
      {isSidebar && !isPanelCollapsed && (
        <div
          onMouseDown={startResize}
          onTouchStart={startResize}
          className="absolute left-0 top-0 bottom-0 w-2 cursor-col-resize hover:bg-ui-soft transition-colors z-10 flex items-center justify-center"
        >
          <div className="flex flex-col gap-0.5 opacity-40">
            <div className="w-0.5 h-0.5 rounded-full bg-ui-subtle" />
            <div className="w-0.5 h-0.5 rounded-full bg-ui-subtle" />
            <div className="w-0.5 h-0.5 rounded-full bg-ui-subtle" />
          </div>
        </div>
      )}
      {/* Header */}
      {isSidebar && isPanelCollapsed ? (
        <div className="h-11 border-b border-ui-soft shrink-0">
          <button
            onClick={() => setIsPanelCollapsed(false)}
            className="w-full h-full flex items-center justify-start gap-2 px-3 hover:bg-ui-elevated transition-colors cursor-pointer"
            title={`Expand tasks · ${tasksSummary}`}
          >
            <span
              className="inline-flex items-center justify-center w-6 h-6 rounded-md border border-ui-strong bg-ui-elevated text-ui"
              style={{ boxShadow: "0 0 0 1px color-mix(in srgb, var(--border-active) 35%, transparent)" }}
            >
              <ListTodo size={13} />
            </span>
            <span className="text-[10px] font-semibold font-mono text-ui-subtle uppercase tracking-[0.08em]">Tasks</span>
          </button>
        </div>
      ) : (
        <div className="h-11 flex items-center justify-between px-4 border-b border-ui-soft shrink-0">
          {isSidebar ? (
            <button
              onClick={() => setIsPanelCollapsed(true)}
              className="flex items-center gap-2 min-w-0 text-left cursor-pointer"
              title="Collapse tasks"
            >
              <span className="text-ui-subtle shrink-0">
                <ChevronRight size={12} />
              </span>
              <span className="text-[10px] font-semibold font-mono text-ui-subtle uppercase tracking-[0.08em]">Tasks</span>
              <span className="text-[10px] font-mono text-ui-faint truncate">{tasksSummary}</span>
            </button>
          ) : (
            <div className="min-w-0">
              <span className="text-[10px] font-mono text-ui-faint truncate">{tasksSummary}</span>
            </div>
          )}
          <button
            onClick={() => setShowForm((v) => !v)}
            className="flex items-center justify-center text-ui-subtle hover:text-ui transition-colors cursor-pointer"
            style={{ width: 24, height: 24, background: 'var(--bg-active)', border: '1px solid var(--border-active)', borderRadius: 6 }}
            title="Add task"
          >
            <Plus size={12} />
          </button>
        </div>
      )}

      {/* Scrollable content */}
      {(!isSidebar || !isPanelCollapsed) && (
      <div className="flex-1 overflow-y-auto p-3 space-y-1">
        {showForm && (
          <CardForm
            agents={agents.map((a) => a.name)}
            onSubmit={handleCreate}
            onCancel={() => setShowForm(false)}
          />
        )}
        {isSidebar ? (
          <>
            {SECTIONS.map((section) => {
              const sectionCards = grouped[section.status];
              const isCollapsed = isSectionCollapsed(section.status);

              return (
                <div key={section.status}>
                  <button
                    onClick={() => toggleSection(section.status)}
                    className="w-full flex items-center gap-1.5 py-1.5 text-xs cursor-pointer"
                  >
                    <span className="text-ui-subtle">
                      {isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
                    </span>
                    <span className={`font-mono text-[10px] uppercase tracking-[0.08em] ${section.labelColor}`}>{section.label}</span>
                    {sectionCards.length > 0 && (
                      <span
                        className="text-[10px] font-mono text-ui-faint"
                        style={{ background: 'var(--bg-card)', padding: '1px 6px', borderRadius: 4 }}
                      >
                        {sectionCards.length}
                      </span>
                    )}
                  </button>

                  {!isCollapsed && sectionCards.length > 0 && (
                    <div className="space-y-2 pb-2">
                      {sectionCards.map((card) => (
                        <CardItem
                          key={card.id}
                          card={card}
                          agents={agents}
                          isRunning={isRunning}
                          onStart={() => onStartCard(card.id)}
                          onDelegate={() => onDelegateCard(card.id)}
                          onMarkDone={() => onMarkDone(card.id)}
                          onDelete={() => onDeleteCard(card.id)}
                          onUpdate={(fields) => onUpdateCard(card.id, fields)}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </>
        ) : (
          <div className="h-full min-h-0 overflow-auto pb-1">
            <div className="h-full min-h-0 min-w-max flex gap-3 pr-1">
              {SECTIONS.map((section) => {
                const sectionCards = grouped[section.status];
                return (
                  <div key={section.status} className="w-[290px] shrink-0 rounded-lg border border-ui bg-ui-elevated flex flex-col max-h-full">
                    <div className="h-10 px-3 border-b border-ui-soft flex items-center gap-2 shrink-0">
                      <span className={`font-mono text-[10px] uppercase tracking-[0.08em] ${section.labelColor}`}>{section.label}</span>
                      <span className="ml-auto text-[10px] font-mono text-ui-faint">{sectionCards.length}</span>
                    </div>
                    <div className="flex-1 overflow-y-auto p-2 space-y-2">
                      {sectionCards.length === 0 ? (
                        <div className="text-[11px] text-ui-faint px-1 py-2">No cards</div>
                      ) : (
                        sectionCards.map((card) => (
                          <CardItem
                            key={card.id}
                            card={card}
                            agents={agents}
                            isRunning={isRunning}
                            onStart={() => onStartCard(card.id)}
                            onDelegate={() => onDelegateCard(card.id)}
                            onMarkDone={() => onMarkDone(card.id)}
                            onDelete={() => onDeleteCard(card.id)}
                            onUpdate={(fields) => onUpdateCard(card.id, fields)}
                          />
                        ))
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
      )}
    </div>
  );
}
