import { useState, useRef, useCallback, useEffect } from "react";
import { Play, Square } from "lucide-react";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";
import { useToast } from "./Toast";
import type { AgentInfo } from "../types";
import { Button, Input, Panel } from "./ui";

const DEFAULT_AGENTS: AgentInfo[] = [
  { name: "claude", type: "claude", role: "" },
  { name: "codex", type: "codex", role: "" },
  { name: "kimi", type: "kimi", role: "" },
];

interface Props {
  onSubmit: (text: string) => boolean | void;
  onStopRound: () => void;
  onResume: () => void;
  isRunning: boolean;
  isPaused: boolean;
  connected: boolean;
  agents?: AgentInfo[];
}

export default function PromptInput({
  onSubmit,
  onStopRound,
  onResume,
  isRunning,
  isPaused,
  connected,
  agents = DEFAULT_AGENTS,
}: Props) {
  const { toast } = useToast();
  const [value, setValue] = useState("");
  const [showMentions, setShowMentions] = useState(false);
  const [mentionQuery, setMentionQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isFocused, setIsFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const mentionStartIndex = useRef<number>(-1);
  const mentionEndIndex = useRef<number>(-1);

  const filteredAgents = agents.filter(agentInfo =>
    agentInfo.name.toLowerCase().includes(mentionQuery.toLowerCase())
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    const cursorPos = e.target.selectionStart || 0;

    // Check if we just typed "@" or are in a mention
    const lastAtIndex = newValue.lastIndexOf("@", cursorPos - 1);

    if (lastAtIndex !== -1) {
      // Check if there's a space between @ and cursor (meaning we're not in a mention)
      const textAfterAt = newValue.slice(lastAtIndex + 1, cursorPos);
      const hasSpace = textAfterAt.includes(" ");

      if (!hasSpace && cursorPos > lastAtIndex) {
        mentionStartIndex.current = lastAtIndex;
        // Find end of mention token (next space or end of string)
        const textAfterCursor = newValue.slice(cursorPos);
        const nextSpaceIndex = textAfterCursor.search(/\s/);
        mentionEndIndex.current = nextSpaceIndex === -1
          ? newValue.length
          : cursorPos + nextSpaceIndex;
        setMentionQuery(textAfterAt);
        setShowMentions(true);
        setSelectedIndex(0);
      } else {
        setShowMentions(false);
      }
    } else {
      setShowMentions(false);
    }

    setValue(newValue);
  };

  const insertMention = useCallback((agent: string) => {
    if (mentionStartIndex.current === -1) return;

    const before = value.slice(0, mentionStartIndex.current);
    const after = value.slice(mentionEndIndex.current);
    const newValue = `${before}@${agent} ${after}`;

    setValue(newValue);
    setShowMentions(false);
    mentionStartIndex.current = -1;
    mentionEndIndex.current = -1;

    // Focus back on input
    setTimeout(() => {
      inputRef.current?.focus();
      const newCursorPos = before.length + agent.length + 2; // +2 for @ and space
      inputRef.current?.setSelectionRange(newCursorPos, newCursorPos);
    }, 0);
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (showMentions && filteredAgents.length > 0) {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setSelectedIndex(prev => (prev + 1) % filteredAgents.length);
          return;
        case "ArrowUp":
          e.preventDefault();
          setSelectedIndex(prev => (prev - 1 + filteredAgents.length) % filteredAgents.length);
          return;
        case "Enter":
          e.preventDefault();
          insertMention(filteredAgents[selectedIndex].name);
          return;
        case "Escape":
          setShowMentions(false);
          return;
        case "Tab":
          e.preventDefault();
          insertMention(filteredAgents[selectedIndex].name);
          return;
      }
    }

    if (e.key === "Enter") {
      const trimmed = value.trim();
      if (!trimmed) return;
      const ok = onSubmit(trimmed);
      if (ok === false) {
        toast("Not connected — message not sent", "error");
        return;
      }
      setValue("");
      setShowMentions(false);
    }
  };

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    const ok = onSubmit(trimmed);
    if (ok === false) {
      toast("Not connected — message not sent", "error");
      return;
    }
    setValue("");
    setShowMentions(false);
  };

  // Close mentions when clicking outside
  useEffect(() => {
    const handleClickOutside = () => setShowMentions(false);
    if (showMentions) {
      document.addEventListener("click", handleClickOutside);
      return () => document.removeEventListener("click", handleClickOutside);
    }
  }, [showMentions]);

  return (
    <div className="shrink-0 relative border-t border-ui-soft bg-ui-surface px-6 py-3">
      <div className="max-w-3xl mx-auto">
        <div
          className="flex gap-3 items-center rounded-xl border px-4 py-2.5 transition-all"
          style={{
            background: "var(--bg-surface)",
            borderColor: isFocused ? "var(--border-active)" : "var(--border-medium)",
            boxShadow: isFocused
              ? "0 0 0 1px color-mix(in srgb, var(--border-active) 55%, transparent)"
              : "none",
          }}
        >
          {/* Arrow prefix */}
          <span className="text-ui-faint text-sm font-mono shrink-0 select-none">&rarr;</span>

          <div className="relative flex-1">
            <Input
              ref={inputRef}
              type="text"
              value={value}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder={isRunning ? "Send a message to intervene..." : "Send a message... (@ to mention)"}
              className="w-full border-0 rounded-none px-0 py-1 text-[13px] text-ui placeholder:text-ui-faint focus:outline-none focus:ring-0"
              style={{ background: "inherit" }}
              disabled={!connected}
            />

            {/* Mention autocomplete dropdown */}
            {showMentions && filteredAgents.length > 0 && (
              <Panel
                className="absolute bottom-full left-0 mb-2 bg-ui-elevated border-ui-strong overflow-hidden min-w-[220px] max-w-[320px] z-50 p-0"
                onClick={(e) => e.stopPropagation()}
              >
                {filteredAgents.map((agentInfo, index) => (
                  <Button
                    key={agentInfo.name}
                    onClick={() => insertMention(agentInfo.name)}
                    variant="ghost"
                    size="sm"
                    className={`w-full flex items-center justify-start gap-2 px-3 py-1.5 text-left text-[12px] hover:bg-ui-soft transition-colors ${
                      index === selectedIndex ? "bg-ui-soft" : ""
                    }`}
                  >
                    <span className={AGENT_COLORS[agentInfo.type] || "text-ui-muted"}>
                      <AgentIcon agent={agentInfo.type} size={14} />
                    </span>
                    <span className="text-ui">{agentInfo.name}</span>
                  </Button>
                ))}
              </Panel>
            )}
          </div>

          {/* Send button — prototype style */}
          <button
            onClick={handleSubmit}
            disabled={!value.trim() || !connected}
            className="shrink-0 flex items-center gap-1.5 font-mono text-[11px] text-ui-muted disabled:opacity-30 transition-colors hover:text-ui cursor-pointer disabled:cursor-default"
            style={{ background: 'var(--bg-active)', border: '1px solid var(--border-active)', borderRadius: '8px', padding: '6px 12px' }}
            title="Send (Enter)"
          >
            <span className="text-[9px] opacity-60">&#8984;</span>
            Send
          </button>

          {/* Stop / Resume controls */}
          {isRunning && !isPaused && (
            <>
              <div className="w-px h-5 border-l border-ui-soft shrink-0" />
              <Button
                onClick={onStopRound}
                variant="ghost"
                size="sm"
                className="w-7 h-7 !p-0 rounded-lg bg-ui-danger-soft text-ui-danger"
                title="Stop round"
                icon={<Square size={13} fill="currentColor" />}
              >
                <span className="sr-only">Stop round</span>
              </Button>
            </>
          )}

          {isPaused && (
            <>
              <div className="w-px h-5 border-l border-ui-soft shrink-0" />
              <Button
                onClick={onResume}
                variant="ghost"
                size="sm"
                className="w-7 h-7 !p-0 rounded-lg bg-ui-success-soft text-ui-success"
                title="Resume next round"
                icon={<Play size={13} fill="currentColor" />}
              >
                <span className="sr-only">Resume next round</span>
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
