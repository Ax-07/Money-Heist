import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const variants = cva("inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 disabled:pointer-events-none disabled:opacity-50", {
  variants: {variant: {default: "bg-slate-100 text-slate-950 hover:bg-white", secondary: "bg-slate-800 text-slate-100 hover:bg-slate-700", ghost: "text-slate-300 hover:bg-slate-800/70 hover:text-white", danger: "bg-red-950/80 text-red-200 border border-red-800 hover:bg-red-900/80"}, size: {sm: "h-8 px-3", default: "h-9 px-4", icon: "h-9 w-9"}},
  defaultVariants: {variant: "default", size: "default"}
});
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof variants> {}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({className, variant, size, ...props}, ref) => <button ref={ref} className={cn(variants({variant, size}), className)} {...props}/>);
Button.displayName = "Button";
