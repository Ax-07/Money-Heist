import React from "react";
import { cn } from "@/lib/utils";

export function StatusBadge({ value, className }: { value: string; className?: string }) {
  const upper = value.toUpperCase();
  const tone = upper.includes("LIVE")
    ? "border-red-800 bg-red-950/50 text-red-200"
    : ["LONG", "APPROVED", "ACTIVE", "FILLED", "COMPLETED", "CLEAR"].some((x) => upper.includes(x))
      ? "border-emerald-800 bg-emerald-950/50 text-emerald-200"
      : ["SHORT", "REJECTED", "FAILED", "CRITICAL"].some((x) => upper.includes(x))
        ? "border-rose-800 bg-rose-950/50 text-rose-200"
        : ["RESIZED", "CAUTION", "WARNING", "PROBATION"].some((x) => upper.includes(x))
          ? "border-amber-800 bg-amber-950/50 text-amber-200"
          : ["PAPER", "SHADOW", "BACKTEST", "OOS"].some((x) => upper.includes(x))
            ? "border-violet-800 bg-violet-950/50 text-violet-200"
            : "border-slate-700 bg-slate-900 text-slate-300";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-[11px] font-semibold tracking-wide",
        tone,
        className,
      )}
    >
      {value}
    </span>
  );
}
