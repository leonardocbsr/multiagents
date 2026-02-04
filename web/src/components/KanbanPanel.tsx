import { useState, useMemo, useRef, useEffect } from "react";
import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import type { Card, CardStatus } from "../types";
import CardItem from "./CardItem";
import CardForm from "./CardForm";

interface Props {
  cards: Card[];
  agents: string[];
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
  badgeColor: string;
}

const SECTIONS: SectionDef[] = [
  { status: "backlog", label: "Backlog", badgeColor: "bg-zinc-600" },
  { status: "coordinating", label: "Coordinating", badgeColor: "bg-purple-500" },
  { status: "planning", label: "Planning", badgeColor: "bg-blue-500" },
  { status: "reviewing", label: "Reviewing", badgeColor: "bg-amber-500" },
  { status: "implementing", label: "Implementing", badgeColor: "bg-emerald-500" },
  { status: "done", label: "Done", badgeColor: "bg-zinc-500" },
];

export default function KanbanPanel({
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
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem("kanban-collapsed") || "{}");
    } catch { return {}; }
  });
  useEffect(() => {
    localStorage.setItem("kanban-collapsed", JSON.stringify(collapsed));
  }, [collapsed]);

  const [width, setWidth] = useState(320);
  const isResizing = useRef(false);

  useEffect(() => {
    const onMove = (e: MouseEvent | TouchEvent) => {
      if (!isResizing.current) return;
      const clientX = "touches" in e ? e.touches[0].clientX : e.clientX;
      setWidth(Math.max(240, Math.min(600, window.innerWidth - clientX)));
    };
    const onEnd = () => {
      isResizing.current = false;
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
  }, []);

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
    if (status in collapsed) return collapsed[status];
    // Default: backlog expanded, others expanded only if they have cards
    if (status === "backlog") return false;
    return grouped[status].length === 0;
  };

  const toggleSection = (status: CardStatus) => {
    setCollapsed((prev) => ({ ...prev, [status]: !isSectionCollapsed(status) }));
  };

  const handleCreate = (title: string, description: string, planner?: string, implementer?: string, reviewer?: string, coordinator?: string) => {
    onCreateCard(title, description, planner, implementer, reviewer, coordinator);
    setShowForm(false);
  };

  return (
    <div style={{ width }} className="shrink-0 border-l border-zinc-800 flex flex-col h-full bg-zinc-950 overflow-hidden relative">
      {/* Resize handle */}
      <div
        onMouseDown={startResize}
        onTouchStart={startResize}
        className="absolute left-0 top-0 bottom-0 w-2 cursor-col-resize hover:bg-blue-500/50 active:bg-blue-500/50 transition-colors z-10"
      />
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 shrink-0">
        <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">Tasks</span>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="text-zinc-500 hover:text-zinc-300 transition-colors"
          title="Add task"
        >
          <Plus size={14} />
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1">
        {showForm && (
          <CardForm
            agents={agents}
            onSubmit={handleCreate}
            onCancel={() => setShowForm(false)}
          />
        )}

        {SECTIONS.map((section) => {
          const sectionCards = grouped[section.status];
          const isCollapsed = isSectionCollapsed(section.status);

          return (
            <div key={section.status}>
              <button
                onClick={() => toggleSection(section.status)}
                className="w-full flex items-center gap-1.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                <span className="text-zinc-500">
                  {isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
                </span>
                <span className="font-medium">{section.label}</span>
                {sectionCards.length > 0 && (
                  <span className={`${section.badgeColor} text-white text-[10px] font-medium rounded-full px-1.5 py-0 leading-4 min-w-[18px] text-center`}>
                    {sectionCards.length}
                  </span>
                )}
              </button>

              {!isCollapsed && (
                <div className="space-y-2 pb-2">
                  {sectionCards.length === 0 ? (
                    <div className="text-[10px] text-zinc-600 pl-5 py-1">No tasks</div>
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
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
