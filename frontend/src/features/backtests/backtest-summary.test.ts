import { describe, expect, it } from "vitest";
import type { CampaignSummary } from "@/lib/api/schemas";
import { funnelSnapshot, netReturnPercent, quoteAsset } from "./backtest-summary";

describe("backtest summary helpers", () => {
  it("derives the display-only net return from canonical trading net and initial capital", () => {
    const period = {trading_net:{value:"-376.99"}} as unknown as CampaignSummary["oos"];
    expect(netReturnPercent(period, "10000")).toBeCloseTo(-3.7699, 4);
  });

  it("uses the persisted Decision Funnel without inventing missing stages", () => {
    const period = {
      opportunities: 27,
      executed_orders: 3,
      closed_trades: 2,
      decision_funnel: {
        counts: {
          candidate_opportunities: 27,
          professor_no_trade: 17,
          trade_proposals_created: 10,
          risk_rejected: 7,
          risk_resized: 3,
          risk_approved: 0,
          orders_submitted: 3,
          fills: 3,
        },
      },
    } as unknown as CampaignSummary["oos"];
    expect(funnelSnapshot(period)).toEqual({
      candidates: 27,
      noTrade: 17,
      proposals: 10,
      riskRejected: 7,
      riskAuthorized: 3,
      orders: 3,
      fills: 3,
      closedTrades: 2,
    });
  });

  it("keeps quote-asset display explicit", () => {
    expect(quoteAsset("BTC/USDC")).toBe("USDC");
    expect(quoteAsset("BTC/EUR")).toBe("EUR");
  });
});
