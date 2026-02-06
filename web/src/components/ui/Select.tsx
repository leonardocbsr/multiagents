import type { SelectHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

interface Props extends SelectHTMLAttributes<HTMLSelectElement> {}

export default function Select({ className, ...props }: Props) {
  return <select className={cn("ui-field px-2 py-1.5 text-xs", className)} {...props} />;
}
