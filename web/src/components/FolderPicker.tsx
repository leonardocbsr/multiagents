import { useEffect, useState, useRef, useCallback } from "react";
import { Folder, ChevronRight, X, Keyboard } from "lucide-react";
import { fetchDirectories } from "../api";

interface Props {
  open: boolean;
  initialPath?: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export default function FolderPicker({ open, initialPath, onSelect, onClose }: Props) {
  const [path, setPath] = useState(initialPath || "~");
  const [dirs, setDirs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manualMode, setManualMode] = useState(false);
  const [manualPath, setManualPath] = useState("");
  const manualRef = useRef<HTMLInputElement>(null);

  const navigate = useCallback((to: string) => {
    setError(null);
    setPath(to);
    setManualMode(false);
  }, []);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    fetchDirectories(path)
      .then((data) => {
        setPath(data.path);
        setDirs(data.directories);
      })
      .catch(() => setError("Failed to list directory"))
      .finally(() => setLoading(false));
  }, [open, path]);

  useEffect(() => {
    if (manualMode) setTimeout(() => manualRef.current?.focus(), 0);
  }, [manualMode]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const segments = path.split("/").filter(Boolean);

  const goManual = () => {
    const v = manualPath.trim();
    if (v) navigate(v);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center" onClick={onClose}>
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-lg mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-200">Select folder</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Breadcrumbs */}
        <div className="px-4 py-2 border-b border-zinc-800 overflow-x-auto">
          <div className="flex items-center gap-1 text-xs text-zinc-400 whitespace-nowrap">
            <button onClick={() => navigate("/")} className="hover:text-zinc-200 transition-colors">/</button>
            {segments.map((seg, i) => {
              const prefix = "/" + segments.slice(0, i + 1).join("/");
              return (
                <span key={prefix} className="flex items-center gap-1">
                  <ChevronRight size={12} className="text-zinc-600" />
                  <button onClick={() => navigate(prefix)} className="hover:text-zinc-200 transition-colors">{seg}</button>
                </span>
              );
            })}
          </div>
        </div>

        {/* Error */}
        {error && <div className="px-4 py-2 text-xs text-red-400">{error}</div>}

        {/* Directory list */}
        <div className="max-h-[50vh] overflow-y-auto">
          {loading ? (
            <p className="px-4 py-6 text-xs text-zinc-600 text-center">Loading...</p>
          ) : dirs.length === 0 ? (
            <p className="px-4 py-6 text-xs text-zinc-600 text-center">No subdirectories</p>
          ) : (
            dirs.map((name) => (
              <button
                key={name}
                onClick={() => navigate(path + "/" + name)}
                className="w-full flex items-center gap-2 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800 transition-colors text-left"
              >
                <Folder size={14} className="text-zinc-500 shrink-0" />
                <span className="truncate">{name}</span>
              </button>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-zinc-800 px-4 py-3 space-y-2">
          {manualMode ? (
            <div className="flex gap-2">
              <input
                ref={manualRef}
                type="text"
                value={manualPath}
                onChange={(e) => setManualPath(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") goManual(); }}
                placeholder="/path/to/folder"
                className="flex-1 px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
              />
              <button onClick={goManual} className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded text-sm text-zinc-200 transition-colors">Go</button>
            </div>
          ) : null}
          <div className="flex items-center gap-2">
            <button
              onClick={() => onSelect(path)}
              disabled={loading}
              className="flex-1 px-3 py-2 bg-zinc-700 hover:bg-zinc-600 rounded text-sm text-zinc-200 transition-colors disabled:opacity-50"
            >
              Select this folder
            </button>
            <button
              onClick={() => setManualMode(!manualMode)}
              className="p-2 text-zinc-500 hover:text-zinc-300 transition-colors"
              title={manualMode ? "Browse" : "Type path"}
            >
              <Keyboard size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
