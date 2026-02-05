import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "../../lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
}

const VARIANT_CLASS: Record<Variant, string> = {
  primary: "ui-btn-primary",
  secondary: "ui-btn-secondary",
  ghost: "ui-btn-ghost",
  danger: "ui-btn text-ui-danger border border-ui-strong bg-ui-soft",
};

const SIZE_CLASS: Record<Size, string> = {
  sm: "text-xs px-2 py-1",
  md: "text-sm",
};

export default function Button({
  variant = "secondary",
  size = "md",
  icon,
  className,
  children,
  ...props
}: Props) {
  return (
    <button className={cn(VARIANT_CLASS[variant], SIZE_CLASS[size], className)} {...props}>
      {icon}
      {children}
    </button>
  );
}
