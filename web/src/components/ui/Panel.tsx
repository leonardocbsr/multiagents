import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

interface Props extends HTMLAttributes<HTMLDivElement> {
  padded?: boolean;
}

export default function Panel({ padded = true, className, ...props }: Props) {
  return <div className={cn("ui-panel", padded && "p-3", className)} {...props} />;
}
