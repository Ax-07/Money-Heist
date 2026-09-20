"use client";

import type { DecisionIndicatorPoint, ScannerThresholds } from "@/lib/api/decision-chart-schemas";

function number(value: number | null, digits = 2): string {
  return value === null || !Number.isFinite(value) ? "—" : value.toFixed(digits);
}

function Signal({ label, value, threshold }: { label: string; value: string; threshold: string }) {
  return (
    <div className="rounded-md border border-slate-800/90 bg-slate-950/70 px-3 py-2">
      <p className="text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-600">{label}</p>
      <p className="mt-1 font-mono text-xs text-slate-200">{value}</p>
      <p className="mt-1 text-[9px] text-slate-600">{threshold}</p>
    </div>
  );
}

export function DecisionIndicatorSummary({
  points,
  cursorTime,
  thresholds,
}: {
  points: DecisionIndicatorPoint[];
  cursorTime: number | null;
  thresholds: ScannerThresholds;
}) {
  const current = cursorTime === null
    ? undefined
    : points.slice().reverse().find(point => point.time <= cursorTime);

  return (
    <div className="border-t border-slate-800/90 bg-slate-950/75 px-3 py-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Signaux de décision</span>
        {current && <span className="rounded border border-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-500">{current.regime}</span>}
        <span className="ml-auto text-[10px] text-slate-600">valeurs Scanner au curseur</span>
      </div>

      {!current ? (
        <p className="rounded-md border border-slate-800 px-3 py-2 text-xs text-slate-500">
          Warmup Scanner non atteint à ce point du replay.
        </p>
      ) : (
        <>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <Signal
              label="Momentum"
              value={`RSI ${number(current.rsi_14)}`}
              threshold={`extrême ≤ ${thresholds.momentum_low_rsi} / ≥ ${thresholds.momentum_high_rsi}`}
            />
            <Signal
              label="Tendance"
              value={`ADX ${number(current.adx_14)} · spread ${number(current.ema_spread_pct, 3)}%`}
              threshold={`ADX ≥ ${thresholds.trend_adx_threshold} + |spread| ≥ ${thresholds.trend_ema_spread_pct}%`}
            />
            <Signal
              label="Volatilité / volume"
              value={`ATR ×${number(current.atr_expansion_ratio, 2)} · vol ×${number(current.volume_ratio, 2)}`}
              threshold={`ATR ≥ ×${thresholds.volatility_expansion_ratio} · vol ≥ ×${thresholds.volume_expansion_ratio}`}
            />
            <Signal
              label="Breakout range"
              value={`haut ${number(current.distance_to_range_high_pct, 3)}% · bas ${number(current.distance_to_range_low_pct, 3)}%`}
              threshold={`buffer ±${thresholds.range_break_buffer_pct}%`}
            />
          </div>

          <details className="mt-2 rounded-md border border-slate-800/80 px-3 py-2 text-[10px] text-slate-500">
            <summary className="cursor-pointer select-none text-slate-400">Détails indicateurs</summary>
            <div className="mt-2 grid gap-x-4 gap-y-1 font-mono sm:grid-cols-2 xl:grid-cols-4">
              <span>EMA {number(current.ema_fast)} / {number(current.ema_slow)}</span>
              <span>Range20 {number(current.prior_range_low_20)} → {number(current.prior_range_high_20)}</span>
              <span>MACD {number(current.macd_line, 4)}</span>
              <span>signal {number(current.macd_signal, 4)}</span>
              <span>hist {number(current.macd_histogram, 4)}</span>
              <span>ATR14 {number(current.atr_14, 4)} · {number(current.atr_pct, 4)}%</span>
              <span>RV20 {number(current.realized_volatility_20_pct, 4)}%</span>
              <span>BB width {number(current.bollinger_width_pct, 4)}%</span>
              <span>warmup {current.warmup_complete ? "OK" : "INCOMPLETE"}</span>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
