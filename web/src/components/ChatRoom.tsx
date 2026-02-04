import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
import type { AppState } from "../types";
import MessageBubble from "./MessageBubble";
import StreamingBubble from "./StreamingBubble";

interface Props {
  state: AppState;
}

export default function ChatRoom({ state }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [isNearBottom, setIsNearBottom] = useState(true);

  const checkScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const threshold = 80;
    setIsNearBottom(el.scrollHeight - el.scrollTop - el.clientHeight < threshold);
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener("scroll", checkScroll, { passive: true });
    return () => el.removeEventListener("scroll", checkScroll);
  }, [checkScroll]);

  useEffect(() => {
    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [state.messages, state.agentStreams, isNearBottom]);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const activeStreams = Object.entries(state.agentStreams).filter(
    ([agent]) => state.agentStatuses[agent] === "streaming"
  );

  return (
    <div className="relative flex-1 overflow-auto p-3 md:p-4" ref={containerRef}>
      <div className="max-w-3xl mx-auto space-y-4">
        {state.messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} agents={state.agents} />
        ))}
        {activeStreams.map(([agent, stream]) => (
          <StreamingBubble key={`stream-${agent}`} agent={agent} stream={stream} agents={state.agents} />
        ))}
        <div ref={bottomRef} />
      </div>
      {!isNearBottom && (
        <button
          onClick={scrollToBottom}
          className="sticky bottom-3 left-1/2 -translate-x-1/2 w-8 h-8 flex items-center justify-center rounded-full bg-zinc-800 border border-zinc-700 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 transition-colors shadow-lg"
          title="Jump to bottom"
        >
          <ArrowDown size={14} />
        </button>
      )}
    </div>
  );
}
