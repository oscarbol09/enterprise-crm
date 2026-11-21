import * as React from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "success" | "warning" | "destructive" | "outline";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variantStyles = {
    default: "bg-primary text-primary-foreground border border-primary",
    secondary: "bg-secondary text-secondary-foreground border border-border/60",
    success: "bg-success/10 text-success border border-success/25",
    warning: "bg-warning/10 text-warning border border-warning/30",
    destructive: "bg-destructive/10 text-destructive border border-destructive/25",
    outline: "text-foreground border border-border bg-transparent",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium transition-colors",
        variantStyles[variant],
        className
      )}
      {...props}
    />
  );
}
