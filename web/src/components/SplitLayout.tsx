import { useCallback, useRef } from "react";
import type { AppState } from "../types";
import SharedChat from "./SharedChat";

interface Props {
  state: AppState;
  onSendDM?: (agent: string, text: string) => void;
  onStopAgent?: (agent: string) => void;
  onRemoveAgent?: (name: string) => void;
  onAddAgent?: (name: string, agentType: string, role: string) => void;
  density?: "compact" | "comfortable";
  children?: React.ReactNode;
  rightPanel?: React.ReactNode;
}

export default function SplitLayout({
  state,
  onSendDM: _onSendDM,
  onStopAgent,
  onRemoveAgent,
  onAddAgent,
  density = "comfortable",
  children,
  rightPanel,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  const handleExpandAgent = useCallback((agent: string) => {
    void agent;
  }, []);

  return (
    <div ref={containerRef} className="flex flex-1 min-w-0 overflow-hidden">
      {/* Center: Shared Chat + Input */}
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <SharedChat
          state={state}
          onExpandAgent={handleExpandAgent}
          onStopAgent={onStopAgent}
          onRemoveAgent={onRemoveAgent}
          onAddAgent={onAddAgent}
          density={density}
        />
        {children}
      </div>
      {rightPanel}
    </div>
  );
}
