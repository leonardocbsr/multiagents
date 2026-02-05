import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export interface TabItem<T extends string> {
  id: T;
  label: string;
}

interface Props<T extends string> {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}

export default function Tabs<T extends string>({ items, value, onChange, className }: Props<T>) {
  return (
    <div className={cn("flex gap-1", className)}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => onChange(item.id)}
          className={item.id === value ? "ui-tab-active" : "ui-tab-inactive"}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

interface PaneProps {
  open: boolean;
  children: ReactNode;
  className?: string;
}

export function TabPane({ open, children, className }: PaneProps) {
  if (!open) return null;
  return <div className={className}>{children}</div>;
}
