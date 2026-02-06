import type { ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "../../lib/cn";
import Button from "./Button";

interface Props {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}

export default function Modal({ open, title, onClose, children, footer, className }: Props) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 overlay-backdrop flex items-center justify-center" onClick={onClose}>
      <div className={cn("ui-modal w-full max-w-lg mx-4 max-h-[80vh] flex flex-col", className)} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-ui shrink-0">
          <h2 className="text-sm font-medium text-ui">{title}</h2>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close modal" icon={<X size={16} />} />
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-3">{children}</div>
        {footer && <div className="border-t border-ui px-4 py-3 shrink-0">{footer}</div>}
      </div>
    </div>
  );
}
