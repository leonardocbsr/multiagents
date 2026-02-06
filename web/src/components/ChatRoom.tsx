import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
import type { AppState } from "../types";
import MessageBubble from "./MessageBubble";
import StreamingBubble from "./StreamingBubble";
import { Button } from "./ui";

interface Props {
  state: AppState;
  density?: "compact" | "comfortable";
}

export default function ChatRoom({ state, density = "comfortable" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [isNearBottom, setIsNearBottom] = useState(true);
  const [renderLimit, setRenderLimit] = useState(300);

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
  const hiddenMessages = Math.max(0, state.messages.length - renderLimit);
  const renderedMessages = hiddenMessages > 0 ? state.messages.slice(-renderLimit) : state.messages;

  return (
    <div className={`relative flex-1 overflow-auto bg-ui-surface ${density === "compact" ? "p-2 md:p-3" : "p-3 md:p-4"}`} ref={containerRef}>
      <div className={`max-w-3xl mx-auto ${density === "compact" ? "space-y-2.5" : "space-y-4"}`}>
        {hiddenMessages > 0 && (
          <Button
            onClick={() => setRenderLimit((n) => n + 300)}
            variant="secondary"
            size="sm"
            className="mx-auto block text-[10px] bg-ui-surface border-ui-strong text-ui-subtle hover:text-ui hover:bg-ui-elevated"
          >
            Show older ({hiddenMessages} hidden)
          </Button>
        )}
        {renderedMessages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} agents={state.agents} density={density} />
        ))}
        {activeStreams.map(([agent, stream]) => (
          <StreamingBubble key={`stream-${agent}`} agent={agent} stream={stream} agents={state.agents} />
        ))}
        <div ref={bottomRef} />
      </div>
      {!isNearBottom && (
        <Button
          onClick={scrollToBottom}
          variant="secondary"
          size="sm"
          className="sticky bottom-3 left-1/2 -translate-x-1/2 w-8 h-8 !p-0 rounded-full bg-ui-elevated border-ui-strong text-ui-muted hover:bg-ui-soft hover:text-ui shadow-lg"
          title="Jump to bottom"
          icon={<ArrowDown size={14} />}
        >
          <span className="sr-only">Jump to bottom</span>
        </Button>
      )}
    </div>
  );
}
