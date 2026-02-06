import { createContext, useCallback, useContext, useState, useRef } from "react";
import { CheckCircle, AlertCircle, Info, X } from "lucide-react";
import { Button, Panel } from "./ui";

type ToastType = "info" | "error" | "success";
type ToastOptions = {
  durationMs?: number;
  actionLabel?: string;
  onAction?: () => void;
  dedupeKey?: string;
};

interface Toast {
  id: number;
  message: string;
  type: ToastType;
  durationMs: number;
  remainingMs: number;
  startedAt: number;
  paused: boolean;
  actionLabel?: string;
  onAction?: () => void;
  dedupeKey: string;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType, options?: ToastOptions) => void;
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

const ICONS: Record<ToastType, typeof Info> = { info: Info, error: AlertCircle, success: CheckCircle };
const COLORS: Record<ToastType, string> = {
  info: "border-ui-info-soft",
  error: "border-ui-danger-soft",
  success: "border-ui-success-soft",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);
  const timers = useRef<Record<number, ReturnType<typeof setTimeout> | undefined>>({});

  const dismiss = useCallback((id: number) => {
    if (timers.current[id]) clearTimeout(timers.current[id]);
    delete timers.current[id];
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const scheduleDismiss = useCallback((id: number, delayMs: number) => {
    if (timers.current[id]) clearTimeout(timers.current[id]);
    timers.current[id] = setTimeout(() => dismiss(id), delayMs);
  }, [dismiss]);

  const pauseToast = useCallback((id: number) => {
    setToasts((prev) => prev.map((t) => {
      if (t.id !== id || t.paused) return t;
      const elapsed = Date.now() - t.startedAt;
      const remaining = Math.max(0, t.remainingMs - elapsed);
      if (timers.current[id]) clearTimeout(timers.current[id]);
      delete timers.current[id];
      return { ...t, paused: true, remainingMs: remaining };
    }));
  }, []);

  const resumeToast = useCallback((id: number) => {
    setToasts((prev) => prev.map((t) => {
      if (t.id !== id || !t.paused) return t;
      const startedAt = Date.now();
      scheduleDismiss(id, t.remainingMs);
      return { ...t, paused: false, startedAt };
    }));
  }, [scheduleDismiss]);

  const toast = useCallback((message: string, type: ToastType = "info", options: ToastOptions = {}) => {
    const durationMs = options.durationMs ?? 3000;
    const dedupeKey = options.dedupeKey ?? `${type}:${message}`;
    const now = Date.now();
    let targetId: number | null = null;
    setToasts((prev) => {
      const existing = prev.find((t) => t.dedupeKey === dedupeKey);
      if (existing) {
        targetId = existing.id;
        return prev.map((t) => t.id === existing.id
          ? {
            ...t,
            message,
            type,
            durationMs,
            remainingMs: durationMs,
            startedAt: now,
            paused: false,
            actionLabel: options.actionLabel,
            onAction: options.onAction,
          }
          : t
        );
      }
      const id = nextId.current++;
      targetId = id;
      const next: Toast = {
        id,
        message,
        type,
        durationMs,
        remainingMs: durationMs,
        startedAt: now,
        paused: false,
        actionLabel: options.actionLabel,
        onAction: options.onAction,
        dedupeKey,
      };
      return [...prev.slice(-2), next];
    });
    if (targetId !== null) scheduleDismiss(targetId, durationMs);
  }, [scheduleDismiss]);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none max-w-sm">
        {toasts.map((t) => {
          const Icon = ICONS[t.type];
          return (
            <div
              key={t.id}
              onMouseEnter={() => pauseToast(t.id)}
              onMouseLeave={() => resumeToast(t.id)}
              className={`ui-panel relative pointer-events-auto flex items-center gap-2 bg-ui-elevated border-ui-strong border-l-4 ${COLORS[t.type]} px-3 py-2 text-xs text-ui shadow-lg animate-slide-up`}
            >
              <Icon size={14} className="shrink-0" />
              <span className="flex-1">{t.message}</span>
              {t.actionLabel && t.onAction && (
                <Button
                  onClick={() => {
                    t.onAction?.();
                    dismiss(t.id);
                  }}
                  variant="ghost"
                  size="sm"
                  className="text-[11px] text-ui underline underline-offset-2 shrink-0"
                >
                  {t.actionLabel}
                </Button>
              )}
              <Button onClick={() => dismiss(t.id)} variant="ghost" size="sm" className="text-ui-subtle hover:text-ui shrink-0" icon={<X size={12} />}>
                <span className="sr-only">Dismiss</span>
              </Button>
              <Panel className="absolute left-0 bottom-0 h-[2px] w-full bg-ui-soft/70 rounded-b overflow-hidden p-0 border-none">
                <div
                  className="h-full bg-ui-soft"
                  style={{
                    width: `${Math.max(0, Math.min(100, (t.remainingMs / t.durationMs) * 100))}%`,
                    transition: t.paused ? "none" : `width ${Math.max(50, t.remainingMs)}ms linear`,
                  }}
                />
              </Panel>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
