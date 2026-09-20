"use client";

import type { BacktestReplay } from "@/lib/api/schemas";
import {
  sessionTradeStats,
  type DecisionChartDisplayMode,
  type ReplayTrade,
} from "@/lib/trade-terminal";

const MODES: Array<{ value: DecisionChartDisplayMode; label: string; title: string }> = [
  { value: "MIXED", label: "Mixte", title: "Décisions, Risk et trades exécutés" },
  { value: "TRADES", label: "Trades", title: "Uniquement les entrées/sorties PAPER exécutées" },
  { value: "DECISIONS", label: "Décisions", title: "Professor FINAL et rejets Risk, sans exécutions" },
];

function signed(value: number, digits = 2): string {
  if (!Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

export function TradeTerminalBar({
  replay,
  mode,
  selectedTradeId,
  onModeChange,
  onSelectTrade,
}: {
  replay: BacktestReplay;
  mode: DecisionChartDisplayMode;
  selectedTradeId: string | null;
  onModeChange: (mode: DecisionChartDisplayMode) => void;
  onSelectTrade: (trade: ReplayTrade) => void;
}) {
  const stats = sessionTradeStats(replay);
  const ordered = [...replay.trades].sort(
    (left, right) => Date.parse(left.opened_at) - Date.parse(right.opened_at),
  );
  const selectedIndex = selectedTradeId
    ? ordered.findIndex(trade => trade.trade_id === selectedTradeId)
    : -1;
  const previous = selectedIndex > 0 ? ordered[selectedIndex - 1] : undefined;
  const next = selectedIndex >= 0 && selectedIndex < ordered.length - 1
    ? ordered[selectedIndex + 1]
    : undefined;

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-950/80 px-3 py-2">
      <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Terminal</span>
      <span className="font-mono text-[10px] text-slate-400">{stats.total} trades</span>
      <span className="text-[10px] text-emerald-300">{stats.wins} WIN</span>
      <span className="text-[10px] text-rose-300">{stats.losses} LOSS</span>
      {stats.flats > 0 && <span className="text-[10px] text-slate-500">{stats.flats} FLAT</span>}
      {stats.equityReturnPct !== null && (
        <span className={stats.equityReturnPct >= 0 ? "font-mono text-[10px] text-emerald-300" : "font-mono text-[10px] text-rose-300"}>
          equity {signed(stats.equityReturnPct)}%
        </span>
      )}
      <span className={stats.netPnl >= 0 ? "font-mono text-[10px] text-emerald-300" : "font-mono text-[10px] text-rose-300"}>
        PnL {signed(stats.netPnl, 4)}
      </span>

      <div className="ml-auto flex items-center gap-1">
        {MODES.map(item => (
          <button
            key={item.value}
            type="button"
            title={item.title}
            aria-pressed={mode === item.value}
            onClick={() => onModeChange(item.value)}
            className="rounded border border-slate-800 px-2 py-1 text-[10px] text-slate-500 hover:text-slate-200 aria-pressed:border-violet-500/60 aria-pressed:bg-violet-500/10 aria-pressed:text-violet-200"
          >
            {item.label}
          </button>
        ))}
        <span className="mx-1 h-4 w-px bg-slate-800" />
        <button
          type="button"
          disabled={!previous}
          onClick={() => previous && onSelectTrade(previous)}
          className="rounded border border-slate-800 px-2 py-1 text-[10px] text-slate-400 disabled:opacity-25"
          aria-label="Trade précédent"
        >
          ‹ Trade
        </button>
        <button
          type="button"
          disabled={!next}
          onClick={() => next && onSelectTrade(next)}
          className="rounded border border-slate-800 px-2 py-1 text-[10px] text-slate-400 disabled:opacity-25"
          aria-label="Trade suivant"
        >
          Trade ›
        </button>
      </div>
    </div>
  );
}
