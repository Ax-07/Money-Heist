import type { CampaignSummary } from "@/lib/api/schemas";

export type CampaignPeriodSummary = CampaignSummary["design"];

export type FunnelSnapshot = {
  candidates: number;
  noTrade: number | null;
  proposals: number | null;
  riskRejected: number | null;
  riskAuthorized: number | null;
  orders: number;
  fills: number | null;
  closedTrades: number;
};

export function numberOrNull(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function quoteAsset(symbol: string): string {
  const normalized = symbol.trim().toUpperCase();
  const slash = normalized.lastIndexOf("/");
  return slash >= 0 && slash < normalized.length - 1 ? normalized.slice(slash + 1) : "";
}

export function formatNumber(value: string | number | null | undefined, digits = 2): string {
  const parsed = numberOrNull(value);
  if (parsed === null) return "—";
  return parsed.toLocaleString("fr-FR", { minimumFractionDigits: 0, maximumFractionDigits: digits });
}

export function formatSignedNumber(value: string | number | null | undefined, digits = 2): string {
  const parsed = numberOrNull(value);
  if (parsed === null) return "—";
  const formatted = Math.abs(parsed).toLocaleString("fr-FR", { minimumFractionDigits: 0, maximumFractionDigits: digits });
  return `${parsed > 0 ? "+" : parsed < 0 ? "−" : ""}${formatted}`;
}

export function formatFractionPercent(value: string | number | null | undefined, digits = 1): string {
  const parsed = numberOrNull(value);
  if (parsed === null) return "—";
  return `${(parsed * 100).toLocaleString("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits })} %`;
}

export function netReturnPercent(period: CampaignPeriodSummary, initialBalance: string | number | null | undefined): number | null {
  const net = numberOrNull(period.trading_net.value);
  const initial = numberOrNull(initialBalance);
  if (net === null || initial === null || initial <= 0) return null;
  return (net / initial) * 100;
}

export function formatPercentValue(value: number | null, digits = 2): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${value.toLocaleString("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits })} %`;
}

export function metricValue(metric: { value: string | null; status: string }, digits = 2): string {
  if (metric.value !== null) return formatNumber(metric.value, digits);
  const normalized = metric.status.trim().toUpperCase();
  return normalized && normalized !== "AVAILABLE" ? normalized.replaceAll("_", " ") : "—";
}

export function funnelSnapshot(period: CampaignPeriodSummary): FunnelSnapshot {
  const counts = period.decision_funnel?.counts;
  return {
    candidates: counts?.candidate_opportunities ?? period.opportunities,
    noTrade: counts?.professor_no_trade ?? null,
    proposals: counts?.trade_proposals_created ?? null,
    riskRejected: counts?.risk_rejected ?? null,
    riskAuthorized: counts ? counts.risk_approved + counts.risk_resized : null,
    orders: counts?.orders_submitted ?? period.executed_orders,
    fills: counts?.fills ?? null,
    closedTrades: period.closed_trades,
  };
}
