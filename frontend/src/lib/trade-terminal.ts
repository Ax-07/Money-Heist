import type { OverlaySelection } from "@/lib/analytics-overlay-state";
import type { BacktestReplay } from "@/lib/api/schemas";

export type DecisionChartDisplayMode = "MIXED" | "TRADES" | "DECISIONS";
export type ReplayTrade = BacktestReplay["trades"][number];
export type ReplayTrace = BacktestReplay["traces"][number];

export type SelectedTradePlan = {
  side: string;
  entryPrice: number;
  stopPrice: number;
  targets: number[];
};

function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function millis(value: string): number | null {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function directionFromTrace(trace: ReplayTrace): string {
  const details = object(trace.details);
  return String(details.direction ?? "").toUpperCase();
}

export function finalTraceForOpportunity(
  traces: readonly ReplayTrace[],
  opportunityId: string | null | undefined,
): ReplayTrace | undefined {
  if (!opportunityId) return undefined;
  return traces.find(
    trace => trace.opportunity_id === opportunityId && trace.phase.toUpperCase() === "FINAL",
  );
}

export function opportunityIdForTrade(
  trade: ReplayTrade,
  traces: readonly ReplayTrace[],
): string | null {
  const openedAt = millis(trade.opened_at);
  if (openedAt === null) return null;
  const side = trade.side.toUpperCase();
  const candidates = traces.filter(trace => {
    if (trace.phase.toUpperCase() !== "FINAL" || !trace.opportunity_id) return false;
    const observedAt = millis(trace.observed_at);
    if (observedAt === null || Math.abs(observedAt - openedAt) > 2000) return false;
    const direction = directionFromTrace(trace);
    return !direction || direction === side;
  });
  const unique = Array.from(new Set(candidates.map(trace => trace.opportunity_id)));
  return unique.length === 1 ? unique[0] ?? null : null;
}

export function tradeForOpportunity(
  trades: readonly ReplayTrade[],
  traces: readonly ReplayTrace[],
  opportunityId: string | null | undefined,
): ReplayTrade | undefined {
  const trace = finalTraceForOpportunity(traces, opportunityId);
  if (!trace) return undefined;
  const observedAt = millis(trace.observed_at);
  if (observedAt === null) return undefined;
  const direction = directionFromTrace(trace);
  const candidates = trades.filter(trade => {
    const openedAt = millis(trade.opened_at);
    return openedAt !== null
      && Math.abs(openedAt - observedAt) <= 2000
      && (!direction || trade.side.toUpperCase() === direction);
  });
  return candidates.length === 1 ? candidates[0] : undefined;
}

export function tradePlanForOpportunity(
  traces: readonly ReplayTrace[],
  opportunityId: string | null | undefined,
): SelectedTradePlan | null {
  const trace = finalTraceForOpportunity(traces, opportunityId);
  if (!trace) return null;
  const details = object(trace.details);
  const trade = object(details.trade);
  const entryPrice = Number(trade.entry_price);
  const stopPrice = Number(trade.stop_price);
  const targets = Array.isArray(trade.targets)
    ? trade.targets.map(Number).filter(Number.isFinite)
    : [];
  const side = String(details.direction ?? "").toUpperCase();
  if (!side || !Number.isFinite(entryPrice) || !Number.isFinite(stopPrice) || targets.length === 0) {
    return null;
  }
  return { side, entryPrice, stopPrice, targets };
}

export function closedTradeSelection(trade: ReplayTrade): OverlaySelection {
  return {
    objectType: "ClosedTrade",
    objectId: trade.trade_id,
    opportunityId: null,
    timestamp: trade.closed_at,
    navigationTimestamp: trade.closed_at,
    label: `Sortie ${trade.side.toUpperCase()}`,
    details: {
      trade_id: trade.trade_id,
      side: trade.side.toUpperCase(),
      quantity: trade.quantity,
      entry_price: trade.entry_price,
      exit_price: trade.exit_price,
      opened_at: trade.opened_at,
      closed_at: trade.closed_at,
      net_pnl: trade.net_pnl,
      fees: trade.fees,
      slippage_cost: trade.slippage_cost ?? "—",
    },
  };
}

export function selectionForTrade(
  trade: ReplayTrade,
  traces: readonly ReplayTrace[],
): OverlaySelection {
  const opportunityId = opportunityIdForTrade(trade, traces);
  const trace = finalTraceForOpportunity(traces, opportunityId);
  if (!opportunityId || !trace) return closedTradeSelection(trade);
  return {
    objectType: "ProfessorFinal",
    objectId: `terminal:${opportunityId}`,
    opportunityId,
    timestamp: trace.observed_at,
    navigationTimestamp: trace.observed_at,
    label: `FINAL ${trade.side.toUpperCase()}`,
    details: {
      result: trade.side.toUpperCase(),
      trade_id: trade.trade_id,
      opened_at: trade.opened_at,
      closed_at: trade.closed_at,
    },
  };
}

export function selectedTradeFromContext(
  replay: BacktestReplay,
  opportunityId: string | null | undefined,
  selection: OverlaySelection | null | undefined,
): ReplayTrade | undefined {
  const selectedTradeId = selection?.details.trade_id
    ?? ((selection?.objectType === "ClosedTrade" || selection?.objectType === "ClosedTradeEntry")
      ? selection.objectId
      : undefined);
  if (selectedTradeId) {
    const direct = replay.trades.find(trade => trade.trade_id === selectedTradeId);
    if (direct) return direct;
  }
  return tradeForOpportunity(replay.trades, replay.traces, opportunityId);
}

export function tradeDurationLabel(openedAt: string, closedAt: string): string {
  const start = millis(openedAt);
  const end = millis(closedAt);
  if (start === null || end === null || end < start) return "—";
  const totalMinutes = Math.round((end - start) / 60000);
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return `${days}j ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function sessionTradeStats(replay: BacktestReplay) {
  let wins = 0;
  let losses = 0;
  let flats = 0;
  let netPnl = 0;
  for (const trade of replay.trades) {
    const pnl = Number(trade.net_pnl);
    if (!Number.isFinite(pnl)) continue;
    netPnl += pnl;
    if (pnl > 0) wins += 1;
    else if (pnl < 0) losses += 1;
    else flats += 1;
  }
  const equities = replay.equity
    .map(point => Number(point.equity))
    .filter(value => Number.isFinite(value));
  const first = equities[0];
  const last = equities.at(-1);
  const equityReturnPct = first !== undefined && last !== undefined && first > 0
    ? ((last - first) / first) * 100
    : null;
  return { total: replay.trades.length, wins, losses, flats, netPnl, equityReturnPct };
}

const RISK_LABELS: Record<string, string> = {
  MIN_EXPECTED_RR: "RR insuffisant",
  MAX_POSITIONS_LIMIT: "max positions atteint",
  MAX_PORTFOLIO_RISK: "risque portefeuille max",
  MAX_CORRELATED_EXPOSURE: "exposition corrélée max",
  MAX_LEVERAGE: "levier max",
  DAILY_LOSS_LIMIT: "perte journalière max",
  MAX_DRAWDOWN_LIMIT: "drawdown max",
  STOP_ON_WRONG_SIDE: "stop invalide",
  EXPIRED_PROPOSAL: "proposition expirée",
};

export function riskReasonLabel(code: string): string {
  return RISK_LABELS[code.toUpperCase()] ?? code;
}
