import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

type Tone = "neutral" | "success" | "warn" | "error" | "accent";

interface Props extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

const TONE_CLASS: Record<Tone, string> = {
  neutral: "badge-neutral",
  success: "badge-success",
  warn: "badge-warn",
  error: "badge-danger",
  accent: "badge-accent",
};

export default function Badge({ tone = "neutral", className, ...props }: Props) {
  return (
    <span
      className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide", TONE_CLASS[tone], className)}
      {...props}
    />
  );
}
