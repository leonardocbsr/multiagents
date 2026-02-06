import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

type DivProps = HTMLAttributes<HTMLDivElement>;

export function Card({ className, ...props }: DivProps) {
  return <div className={cn("ui-card", className)} {...props} />;
}

export function CardHeader({ className, ...props }: DivProps) {
  return <div className={cn("ui-card-header", className)} {...props} />;
}

export function CardContent({ className, ...props }: DivProps) {
  return <div className={cn("ui-card-content", className)} {...props} />;
}

export function CardFooter({ className, ...props }: DivProps) {
  return <div className={cn("ui-card-footer", className)} {...props} />;
}
