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
  EXPLORE: "badge-info",
  DECISION: "badge-success",
  BLOCKED: "badge-danger",
  DONE: "badge-success",
  TODO: "badge-warn",
  QUESTION: "badge-violet",
  READY: "badge-cyan",
  "IN PROGRESS": "badge-info",
};
const DEFAULT_STATUS_ICON = HelpCircle;
const DEFAULT_STATUS_COLOR = "badge-neutral";

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
            className={`badge ${colorClass}`}
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
            className={`badge badge-info ${isCurrentAgent ? "ring-ui" : ""}`}
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
          className="badge badge-success"
        >
          <CheckCircle2 size={10} />
          +1 {agent}
        </span>
      ))}
      
      {/* Handoff badges */}
      {patterns.handoffs.map((handoff, i) => (
        <span
          key={`handoff-${i}`}
          className="badge badge-violet"
          title={handoff.context}
        >
          <ArrowRight size={10} />
          → {handoff.agent}
        </span>
      ))}
    </div>
  );
}
