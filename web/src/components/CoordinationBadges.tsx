import { 
  UserPlus, 
  ArrowRight, 
  CheckCircle2, 
  AlertCircle, 
  Search, 
  CheckSquare2, 
  HelpCircle, 
  PlayCircle,
  type LucideIcon
} from "lucide-react";
import type { CoordinationPatterns } from "../types";

interface Props {
  patterns: CoordinationPatterns;
  currentAgent?: string; // Highlight if current agent is mentioned
}

const STATUS_ICONS: Record<string, LucideIcon> = {
  EXPLORE: Search,
  DECISION: CheckSquare2,
  BLOCKED: AlertCircle,
  DONE: CheckCircle2,
  TODO: PlayCircle,
  QUESTION: HelpCircle,
  READY: PlayCircle,
  "IN PROGRESS": PlayCircle,
};

const STATUS_COLORS: Record<string, string> = {
  EXPLORE: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  DECISION: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  BLOCKED: "bg-red-500/20 text-red-300 border-red-500/30",
  DONE: "bg-green-500/20 text-green-300 border-green-500/30",
  TODO: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  QUESTION: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  READY: "bg-cyan-500/20 text-cyan-300 border-cyan-500/30",
  "IN PROGRESS": "bg-sky-500/20 text-sky-300 border-sky-500/30",
};
const DEFAULT_STATUS_ICON = HelpCircle;
const DEFAULT_STATUS_COLOR = "bg-zinc-500/20 text-zinc-300 border-zinc-500/30";

export default function CoordinationBadges({ patterns, currentAgent }: Props) {
  const hasPatterns = 
    patterns.mentions.length > 0 ||
    patterns.agreements.length > 0 ||
    patterns.handoffs.length > 0 ||
    patterns.statuses.length > 0;
  
  if (!hasPatterns) return null;

  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {/* Status badges */}
      {patterns.statuses.map((status, i) => {
        const Icon = STATUS_ICONS[status] || DEFAULT_STATUS_ICON;
        const colorClass = STATUS_COLORS[status] || DEFAULT_STATUS_COLOR;
        return (
          <span
            key={`status-${i}`}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border ${colorClass}`}
          >
            <Icon size={10} />
            {status}
          </span>
        );
      })}
      
      {/* Mention badges */}
      {patterns.mentions.map((agent, i) => {
        const isCurrentAgent = currentAgent && agent.toLowerCase() === currentAgent.toLowerCase();
        return (
          <span
            key={`mention-${i}`}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border bg-sky-500/20 text-sky-300 border-sky-500/30 ${isCurrentAgent ? 'ring-1 ring-sky-400' : ''}`}
          >
            <UserPlus size={10} />
            @{agent}
          </span>
        );
      })}
      
      {/* Agreement badges */}
      {patterns.agreements.map((agent, i) => (
        <span
          key={`agree-${i}`}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
        >
          <CheckCircle2 size={10} />
          +1 {agent}
        </span>
      ))}
      
      {/* Handoff badges */}
      {patterns.handoffs.map((handoff, i) => (
        <span
          key={`handoff-${i}`}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border bg-violet-500/20 text-violet-300 border-violet-500/30"
          title={handoff.context}
        >
          <ArrowRight size={10} />
          → {handoff.agent}
        </span>
      ))}
    </div>
  );
}
