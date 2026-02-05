import { useState, useRef, useCallback, useEffect } from "react";
import { ArrowUp, Play, Square } from "lucide-react";
import { AgentIcon, AGENT_COLORS } from "./AgentIcons";
import { useToast } from "./Toast";
import type { AgentInfo } from "../types";

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
    <div className="border-t border-zinc-800 px-3 py-2 md:px-4 md:py-3 shrink-0 relative">
      <div className="max-w-3xl mx-auto flex gap-2 items-center">
        <div className="relative flex-1">
          <input
            ref={inputRef}
            type="text" 
            value={value} 
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={isRunning ? "Send a message to intervene..." : "Send a message... (type @ to mention)"}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
            disabled={!connected}
          />
          
          {/* Mention autocomplete dropdown */}
          {showMentions && filteredAgents.length > 0 && (
            <div 
              className="absolute bottom-full left-0 mb-1 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl overflow-hidden min-w-[150px] z-50"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="text-[10px] text-zinc-500 px-3 py-1 border-b border-zinc-800 uppercase tracking-wider">
                Mention agent
              </div>
              {filteredAgents.map((agentInfo, index) => (
                <button
                  key={agentInfo.name}
                  onClick={() => insertMention(agentInfo.name)}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-left text-sm hover:bg-zinc-800 transition-colors ${
                    index === selectedIndex ? "bg-zinc-800" : ""
                  }`}
                >
                  <span className={AGENT_COLORS[agentInfo.type] || "text-zinc-400"}>
                    <AgentIcon agent={agentInfo.type} size={14} />
                  </span>
                  <span className="text-zinc-300">{agentInfo.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        
        <button 
          onClick={handleSubmit} 
          disabled={!value.trim() || !connected}
          className="w-8 h-8 flex items-center justify-center rounded-lg bg-zinc-700 text-zinc-300 hover:bg-zinc-600 disabled:opacity-30 transition-colors" 
          title="Send"
        >
          <ArrowUp size={16} strokeWidth={2.5} />
        </button>
        
        {isRunning && !isPaused && (
          <button
            onClick={onStopRound}
            className="w-8 h-8 flex items-center justify-center rounded-lg bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors"
            title="Stop round"
          >
            <Square size={14} fill="currentColor" />
          </button>
        )}

        {isPaused && (
          <button
            onClick={onResume}
            className="w-8 h-8 flex items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors"
            title="Resume next round"
          >
            <Play size={14} fill="currentColor" />
          </button>
        )}
      </div>
    </div>
  );
}
