export type TradeResultSource = {
  quantity?: string | number | null;
  entry_price?: string | number | null;
  net_pnl?: string | number | null;
};

export type TradeResultKind = "WIN" | "LOSS" | "FLAT";

export function netTradeReturnPct(trade: TradeResultSource): number | null {
  if (
    trade.quantity === null
    || trade.quantity === undefined
    || trade.quantity === ""
    || trade.entry_price === null
    || trade.entry_price === undefined
    || trade.entry_price === ""
    || trade.net_pnl === null
    || trade.net_pnl === undefined
    || trade.net_pnl === ""
  ) return null;

  const quantity = Math.abs(Number(trade.quantity));
  const entryPrice = Number(trade.entry_price);
  const netPnl = Number(trade.net_pnl);
  const entryNotional = quantity * entryPrice;
  if (
    !Number.isFinite(quantity)
    || !Number.isFinite(entryPrice)
    || !Number.isFinite(netPnl)
    || entryNotional <= 0
  ) return null;
  return (netPnl / entryNotional) * 100;
}

export function tradeResultKind(
  netPnl: string | number | null | undefined,
): TradeResultKind | null {
  if (netPnl === null || netPnl === undefined || netPnl === "") return null;
  const value = Number(netPnl);
  if (!Number.isFinite(value)) return null;
  if (value > 0) return "WIN";
  if (value < 0) return "LOSS";
  return "FLAT";
}
