import type { AppState } from "../types";

const AGENT_COLORS: Record<string, string> = {
  claude: "text-orange-400",
  codex: "text-emerald-400",
  kimi: "text-violet-400",
};

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + "..." : s;
}

function extractDetail(toolInput: Record<string, unknown>): string {
  const path = toolInput.path ?? toolInput.file_path ?? toolInput.command ?? "";
  if (typeof path === "string") return truncate(path, 60);
  return "";
}

interface Props {
  permissions: AppState["pendingPermissions"];
  onRespond: (requestId: string, approved: boolean, agent?: string) => void;
}

export default function PermissionBanner({ permissions, onRespond }: Props) {
  if (permissions.length === 0) return null;

  return (
    <div className="border-b border-amber-700/50 bg-amber-900/20 px-4 py-2 space-y-1.5 shrink-0">
      {permissions.map((p) => {
        const agentColor = AGENT_COLORS[p.agent] ?? "text-zinc-300";
        const detail = extractDetail(p.tool_input);
        return (
          <div key={p.request_id} className="flex items-center gap-2 text-xs">
            <span className={`font-medium ${agentColor}`}>{p.agent}</span>
            <span className="text-zinc-400">wants to</span>
            <code className="px-1.5 py-0.5 bg-zinc-800 rounded text-amber-300 text-[11px]">{p.tool_name}</code>
            {detail && <span className="text-zinc-500 truncate max-w-xs" title={detail}>{detail}</span>}
            <span className="flex-1" />
            <button
              onClick={() => onRespond(p.request_id, true, p.agent)}
              className="px-2 py-0.5 rounded bg-emerald-700/60 hover:bg-emerald-600/80 text-emerald-200 text-[11px] transition-colors"
            >
              Approve
            </button>
            <button
              onClick={() => onRespond(p.request_id, false, p.agent)}
              className="px-2 py-0.5 rounded bg-red-700/60 hover:bg-red-600/80 text-red-200 text-[11px] transition-colors"
            >
              Deny
            </button>
          </div>
        );
      })}
    </div>
  );
}
