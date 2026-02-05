import type { AppState } from "../types";
import { Button } from "./ui";

const AGENT_COLORS: Record<string, string> = {
  claude: "agent-color-claude",
  codex: "agent-color-codex",
  kimi: "agent-color-kimi",
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
    <div className="border-b surface-warn px-4 py-2 space-y-1.5 shrink-0">
      {permissions.map((p) => {
        const agentColor = AGENT_COLORS[p.agent] ?? "text-ui";
        const detail = extractDetail(p.tool_input);
        return (
          <div key={p.request_id} className="flex items-center gap-2 text-xs">
            <span className={`font-medium ${agentColor}`}>{p.agent}</span>
            <span className="text-ui-muted">wants to</span>
            <code className="px-1.5 py-0.5 bg-ui-elevated rounded text-ui-warn text-[11px]">{p.tool_name}</code>
            {detail && <span className="text-ui-subtle truncate max-w-xs" title={detail}>{detail}</span>}
            <span className="flex-1" />
            <Button
              onClick={() => onRespond(p.request_id, true, p.agent)}
              variant="ghost"
              size="sm"
              className="px-2 py-0.5 rounded btn-ui-success text-[11px]"
            >
              Approve
            </Button>
            <Button
              onClick={() => onRespond(p.request_id, false, p.agent)}
              variant="ghost"
              size="sm"
              className="px-2 py-0.5 rounded btn-ui-danger text-[11px]"
            >
              Deny
            </Button>
          </div>
        );
      })}
    </div>
  );
}
