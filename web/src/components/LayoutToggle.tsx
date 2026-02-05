import { Columns3, MessageSquare } from "lucide-react";

export type LayoutMode = "unified" | "split";

interface Props {
  mode: LayoutMode;
  onChange: (mode: LayoutMode) => void;
}

export default function LayoutToggle({ mode, onChange }: Props) {
  return (
    <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-md overflow-hidden">
      <button
        onClick={() => onChange("split")}
        className={`flex items-center gap-1 px-2 py-1 text-[10px] transition-colors ${
          mode === "split"
            ? "bg-zinc-700 text-zinc-200"
            : "text-zinc-500 hover:text-zinc-300"
        }`}
        title="Split view"
      >
        <Columns3 size={11} />
        Split
      </button>
      <button
        onClick={() => onChange("unified")}
        className={`flex items-center gap-1 px-2 py-1 text-[10px] transition-colors ${
          mode === "unified"
            ? "bg-zinc-700 text-zinc-200"
            : "text-zinc-500 hover:text-zinc-300"
        }`}
        title="Unified view"
      >
        <MessageSquare size={11} />
        Chat
      </button>
    </div>
  );
}
