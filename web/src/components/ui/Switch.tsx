import { cn } from "../../lib/cn";

interface Props {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  className?: string;
}

export default function Switch({ checked, onChange, disabled, className }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={cn(
        "relative h-5 w-9 rounded-full border transition-colors",
        checked ? "bg-ui-soft border-ui-strong" : "bg-ui-surface border-ui",
        disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
        className,
      )}
    >
        <span
        className={cn(
          "absolute top-0.5 left-0.5 h-3.5 w-3.5 rounded-full bg-ui-knob transition-transform",
          checked ? "translate-x-4" : "translate-x-0",
        )}
      />
    </button>
  );
}
