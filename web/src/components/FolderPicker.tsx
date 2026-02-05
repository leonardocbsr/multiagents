import { useEffect, useState, useRef, useCallback } from "react";
import { Folder, ChevronRight, Keyboard } from "lucide-react";
import { fetchDirectories } from "../api";
import Button from "./ui/Button";
import Input from "./ui/Input";
import Modal from "./ui/Modal";

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
  const modalRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    if (!open || !modalRef.current) return;
    const root = modalRef.current;
    const focusable = root.querySelectorAll<HTMLElement>(
      'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])',
    );
    focusable[0]?.focus();
  }, [open]);

  if (!open) return null;

  const segments = path.split("/").filter(Boolean);

  const goManual = () => {
    const v = manualPath.trim();
    if (v) navigate(v);
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Choose Workspace"
      className="max-w-lg"
      footer={(
        <div className="space-y-2">
          {manualMode ? (
            <div className="flex gap-2">
              <Input
                ref={manualRef}
                type="text"
                value={manualPath}
                onChange={(e) => setManualPath(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") goManual(); }}
                placeholder="/path/to/folder"
                className="flex-1"
              />
              <Button onClick={goManual} size="sm">Go</Button>
            </div>
          ) : null}
          <div className="flex items-center gap-2">
            <Button onClick={() => onSelect(path)} disabled={loading} className="flex-1">Use this folder</Button>
            <Button onClick={() => setManualMode(!manualMode)} variant="ghost" size="sm" title={manualMode ? "Browse" : "Type path"} icon={<Keyboard size={14} />}>
              <span className="sr-only">Toggle manual path mode</span>
            </Button>
          </div>
        </div>
      )}
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label="Select folder"
      >

        {/* Breadcrumbs */}
        <div className="px-4 py-2 border-b border-ui overflow-x-auto">
          <div className="flex items-center gap-1 text-xs text-ui-muted whitespace-nowrap">
            <Button onClick={() => navigate("/")} variant="ghost" size="sm" className="!p-0 hover:text-ui">/</Button>
            {segments.map((seg, i) => {
              const prefix = "/" + segments.slice(0, i + 1).join("/");
              return (
                <span key={prefix} className="flex items-center gap-1">
                  <ChevronRight size={12} className="text-ui-faint" />
                  <Button onClick={() => navigate(prefix)} variant="ghost" size="sm" className="!p-0 hover:text-ui">{seg}</Button>
                </span>
              );
            })}
          </div>
        </div>

        {/* Error */}
        {error && <div className="px-4 py-2 text-xs text-ui-danger">{error}</div>}

        {/* Directory list */}
        <div className="max-h-[50vh] overflow-y-auto">
          {loading ? (
            <p className="px-4 py-6 text-xs text-ui-faint text-center">Loading...</p>
          ) : dirs.length === 0 ? (
            <p className="px-4 py-6 text-xs text-ui-faint text-center">No subdirectories</p>
          ) : (
            dirs.map((name) => (
              <Button
                key={name}
                onClick={() => navigate(path + "/" + name)}
                variant="ghost"
                className="w-full justify-start gap-2 px-4 py-2 text-sm text-ui hover:bg-ui-elevated text-left"
              >
                <Folder size={14} className="text-ui-subtle shrink-0" />
                <span className="truncate">{name}</span>
              </Button>
            ))
          )}
        </div>

      </div>
    </Modal>
  );
}
