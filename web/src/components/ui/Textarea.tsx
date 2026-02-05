import type { TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

interface Props extends TextareaHTMLAttributes<HTMLTextAreaElement> {}

export default function Textarea({ className, ...props }: Props) {
  return <textarea className={cn("ui-field px-2 py-1.5 text-sm resize-y", className)} {...props} />;
}
