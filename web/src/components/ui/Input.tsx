import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

interface Props extends InputHTMLAttributes<HTMLInputElement> {}

const Input = forwardRef<HTMLInputElement, Props>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn("ui-field px-2 py-1.5 text-sm", className)} {...props} />;
});

export default Input;
