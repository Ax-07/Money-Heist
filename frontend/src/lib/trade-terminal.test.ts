import { describe, expect, it } from "vitest";
import type { BacktestReplay } from "@/lib/api/schemas";
import {
  opportunityIdForTrade,
  riskReasonLabel,
  sessionTradeStats,
  tradeDurationLabel,
  tradePlanForOpportunity,
} from "./trade-terminal";

const trace = {
  sequence: 1,
  observed_at: "2026-09-12T12:00:00Z",
  role: "OOS" as const,
  opportunity_id: "opp-1",
  agent: "professor",
  phase: "FINAL",
  title: "LONG",
  details: {
    direction: "LONG",
    trade: { entry_price: "100", stop_price: "95", targets: ["110", "115"] },
  },
  targets: [],
};

const trade = {
  trade_id: "trade-1",
  system_id: "balanced_v1",
  symbol: "BTC/USDC",
  side: "LONG",
  quantity: "2",
  entry_price: "100",
  exit_price: "110",
  opened_at: "2026-09-12T12:00:00Z",
  closed_at: "2026-09-12T15:30:00Z",
  net_pnl: "18",
  fees: "2",
  slippage_cost: "1",
};

describe("professional trade terminal helpers", () => {
  it("joins a closed PAPER trade to its FINAL opportunity without a temporal nearest-neighbor", () => {
    expect(opportunityIdForTrade(trade, [trace])).toBe("opp-1");
  });

  it("reads SL/TP only from the persisted Professor FINAL proposal", () => {
    expect(tradePlanForOpportunity([trace], "opp-1")).toEqual({
      side: "LONG",
      entryPrice: 100,
      stopPrice: 95,
      targets: [110, 115],
    });
  });

  it("formats trade duration and risk reasons", () => {
    expect(tradeDurationLabel(trade.opened_at, trade.closed_at)).toBe("3h 30m");
    expect(riskReasonLabel("MIN_EXPECTED_RR")).toBe("RR insuffisant");
  });

  it("builds session stats from real trades and equity", () => {
    const replay = {
      trades: [trade, { ...trade, trade_id: "trade-2", net_pnl: "-5" }],
      traces: [trace],
      equity: [
        { observed_at: "2026-09-12T12:00:00Z", equity: "1000", data_kind: "PAPER_EXECUTED" },
        { observed_at: "2026-09-12T16:00:00Z", equity: "1013", data_kind: "PAPER_EXECUTED" },
      ],
    } as unknown as BacktestReplay;
    expect(sessionTradeStats(replay)).toMatchObject({ total: 2, wins: 1, losses: 1, netPnl: 13 });
    expect(sessionTradeStats(replay).equityReturnPct).toBeCloseTo(1.3);
  });
});
