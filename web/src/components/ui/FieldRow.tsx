import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

interface Props {
  label: string;
  description?: string;
  control: ReactNode;
  className?: string;
}

export default function FieldRow({ label, description, control, className }: Props) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <div className="flex-1 min-w-0">
        <label className="text-xs text-ui">{label}</label>
        {description && <p className="text-[10px] text-ui-faint">{description}</p>}
      </div>
      {control}
    </div>
  );
}
