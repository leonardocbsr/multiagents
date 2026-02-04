import { useCallback, useEffect, useRef, useState } from "react";
import type { AppState } from "../types";
import AgentPanels from "./AgentPanels";
import SharedChat from "./SharedChat";

interface Props {
  state: AppState;
  onSendDM?: (agent: string, text: string) => void;
}

const MIN_WIDTH = 240;
const MAX_WIDTH = 500;
const DEFAULT_WIDTH = 300;
const STORAGE_KEY = "split-panel-width";

export default function SplitLayout({ state, onSendDM }: Props) {
  const [panelWidth, setPanelWidth] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) return Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, Number(stored)));
    } catch {}
    return DEFAULT_WIDTH;
  });
  const [expandedAgents, setExpandedAgents] = useState<Set<string>>(() => {
    return new Set(state.agents.length > 0 ? [state.agents[0].name] : []);
  });
  const dragging = useRef(false);
  const panelWidthRef = useRef(panelWidth);
  panelWidthRef.current = panelWidth;
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-expand first agent once agents become available
  useEffect(() => {
    if (state.agents.length > 0) {
      setExpandedAgents((prev) => {
        if (prev.size > 0) return prev;
        return new Set([state.agents[0].name]);
      });
    }
  }, [state.agents]);

  const handleToggleAgent = useCallback((agent: string) => {
    setExpandedAgents((prev) => {
      const next = new Set(prev);
      if (next.has(agent)) {
        next.delete(agent);
      } else {
        next.add(agent);
      }
      return next;
    });
  }, []);

  const handleExpandAgent = useCallback((agent: string) => {
    setExpandedAgents((prev) => {
      if (prev.has(agent)) return prev;
      const next = new Set(prev);
      next.add(agent);
      return next;
    });
  }, []);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
  }, []);

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, e.clientX - rect.left));
      setPanelWidth(newWidth);
    };
    const onMouseUp = () => {
      if (dragging.current) {
        dragging.current = false;
        localStorage.setItem(STORAGE_KEY, String(panelWidthRef.current));
      }
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  return (
    <div ref={containerRef} className="flex flex-1 overflow-hidden">
      {/* Left: Agent Panels */}
      <div
        className="shrink-0 border-r border-zinc-800 overflow-hidden flex flex-col"
        style={{ width: panelWidth }}
      >
        <AgentPanels
          state={state}
          expandedAgents={expandedAgents}
          onToggleAgent={handleToggleAgent}
          onSendDM={onSendDM}
        />
      </div>

      {/* Resize handle */}
      <div
        onMouseDown={onMouseDown}
        className="w-1 cursor-col-resize hover:bg-zinc-700 active:bg-zinc-600 transition-colors shrink-0"
      />

      {/* Center: Shared Chat */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <SharedChat state={state} onExpandAgent={handleExpandAgent} />
      </div>
    </div>
  );
}
