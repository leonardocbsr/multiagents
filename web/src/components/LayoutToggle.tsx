import { Columns3, MessageSquare } from "lucide-react";
import { cn } from "../lib/cn";
import { Button } from "./ui";

export type LayoutMode = "unified" | "split";

interface Props {
  mode: LayoutMode;
  onChange: (mode: LayoutMode) => void;
}

export default function LayoutToggle({ mode, onChange }: Props) {
  const baseClass = "flex items-center gap-1 px-2 py-1 text-[10px] border transition-colors";
  const activeClass = "bg-ui-soft border-ui-strong text-ui-strong font-semibold";
  const inactiveClass = "bg-ui-surface border-ui-soft text-ui-subtle hover:text-ui hover:bg-ui-elevated";

  return (
    <div className="flex items-center ui-panel overflow-hidden p-0">
      <Button
        onClick={() => onChange("split")}
        variant="ghost"
        size="sm"
        className={cn(baseClass,
          mode === "split"
            ? activeClass
            : inactiveClass
        )}
        title="Split view"
      >
        <Columns3 size={11} />
        Split
      </Button>
      <Button
        onClick={() => onChange("unified")}
        variant="ghost"
        size="sm"
        className={cn(baseClass,
          mode === "unified"
            ? activeClass
            : inactiveClass
        )}
        title="Unified view"
      >
        <MessageSquare size={11} />
        Chat
      </Button>
    </div>
  );
}
