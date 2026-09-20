import { describe, expect, it } from "vitest";
import type { FrontendAnalyticsOverlays } from "@/lib/api/analytics-overlay-schemas";
import { buildDecisionOverlayMarkers, buildRiskRejectedPoints, buildTradeEntryMarkers, buildTradeExitMarkers, buildTradeLinkSegments } from "./analytics-overlays";

function overlays(): FrontendAnalyticsOverlays {
  return {
    analytics_available: true,
    funnel_stages: [
      {
        record_id: "stage-final-1",
        opportunity_id: "opp-1",
        stage: "FINAL",
        reached: true,
        stage_status: "COMPLETED",
        stage_result: "NO_TRADE",
        confidence: 0.72,
        reason_codes: ["NO_EDGE"],
        market_as_of: "2026-09-12T12:00:00Z",
        operational_at: "2026-09-12T12:00:01Z",
      },
    ],
  } as unknown as FrontendAnalyticsOverlays;
}

describe("decision-only chart markers", () => {
  it("keeps only Professor FINAL markers and renders no marker text", () => {
    const markers = buildDecisionOverlayMarkers(overlays(), null);
    expect(markers).toHaveLength(1);
    expect(markers[0]?.selection.objectType).toBe("ProfessorFinal");
    expect(markers[0]?.selection.opportunityId).toBe("opp-1");
    expect(markers[0]?.marker.text).toBeUndefined();
    expect(markers[0]?.marker.shape).toBe("circle");
  });

  it("renders a real PAPER exit on the decision candle containing closed_at", () => {
    const markers = buildTradeExitMarkers(
      [{
        trade_id: "trade-1",
        side: "LONG",
        quantity: "0.01",
        entry_price: "60000",
        exit_price: "61250",
        opened_at: "2026-09-12T11:00:00Z",
        closed_at: "2026-09-12T12:17:00Z",
        net_pnl: "12.3",
        fees: "0.7",
        slippage_cost: "0.1",
      }],
      [
        Math.floor(new Date("2026-09-12T12:00:00Z").getTime() / 1000),
        Math.floor(new Date("2026-09-12T13:00:00Z").getTime() / 1000),
      ],
    );
    expect(markers).toHaveLength(1);
    expect(Number(markers[0]?.marker.time)).toBe(Math.floor(new Date("2026-09-12T13:00:00Z").getTime() / 1000));
    expect(markers[0]?.marker.shape).toBe("square");
    expect(markers[0]?.marker.text).toBeUndefined();
    expect(markers[0]?.selection.objectType).toBe("ClosedTrade");
    expect(markers[0]?.selection.timestamp).toBe("2026-09-12T12:17:00Z");
    expect(markers[0]?.selection.details.exit_price).toBe("61250");
    expect(markers[0]?.selection.details.net_pnl).toBe("12.3");
  });

  it("replaces a rejected FINAL entry marker with one compact Risk point", () => {
    const base = overlays();
    const final = base.funnel_stages[0]!;
    const withRisk = {
      ...base,
      funnel_stages: [
        { ...final, stage_result: "LONG" },
        {
          record_id: "stage-risk-1",
          opportunity_id: "opp-1",
          stage: "RISK",
          reached: true,
          stage_status: "COMPLETED",
          stage_result: "REJECTED",
          confidence: null,
          severity: null,
          reason_codes: ["MIN_EXPECTED_RR"],
          market_as_of: "2026-09-12T12:00:00Z",
          operational_at: "2026-09-12T12:00:05Z",
        },
      ],
    } as unknown as FrontendAnalyticsOverlays;
    const candleTime = Math.floor(new Date("2026-09-12T12:00:00Z").getTime() / 1000);
    const points = buildRiskRejectedPoints(withRisk, [candleTime]);
    expect(points).toHaveLength(1);
    expect(Number(points[0]?.time)).toBe(candleTime);
    expect(points[0]?.direction).toBe("LONG");
    expect(points[0]?.selection.objectType).toBe("RiskDecision");
    expect(points[0]?.selection.opportunityId).toBe("opp-1");
    expect(points[0]?.selection.details.status).toBe("REJECTED");
    expect(points[0]?.selection.details.reasons).toBe("MIN_EXPECTED_RR");
    expect(buildDecisionOverlayMarkers(withRisk, null)).toHaveLength(0);
  });

  it("links real PAPER entry and exit geometry and colors only positive PnL as profitable", () => {
    const candleTimes = [
      Math.floor(new Date("2026-09-12T11:00:00Z").getTime() / 1000),
      Math.floor(new Date("2026-09-12T12:00:00Z").getTime() / 1000),
      Math.floor(new Date("2026-09-12T13:00:00Z").getTime() / 1000),
    ];
    const segments = buildTradeLinkSegments(
      [{
        trade_id: "trade-1",
        side: "LONG",
        quantity: "0.01",
        entry_price: "60000",
        exit_price: "61250",
        opened_at: "2026-09-12T11:17:00Z",
        closed_at: "2026-09-12T12:17:00Z",
        net_pnl: "12.3",
        fees: "0.7",
        slippage_cost: "0.1",
      }],
      candleTimes,
    );
    expect(segments).toHaveLength(1);
    expect(Number(segments[0]?.entryTime)).toBe(candleTimes[1]);
    expect(Number(segments[0]?.exitTime)).toBe(candleTimes[2]);
    expect(segments[0]?.entryTimestamp).toBe(Math.floor(new Date("2026-09-12T11:17:00Z").getTime() / 1000));
    expect(segments[0]?.exitTimestamp).toBe(Math.floor(new Date("2026-09-12T12:17:00Z").getTime() / 1000));
    expect(segments[0]?.entryPrice).toBe(60000);
    expect(segments[0]?.exitPrice).toBe(61250);
    expect(segments[0]?.profitable).toBe(true);
  });


  it("projects actual PAPER entries without chart text for Trades mode", () => {
    const candleTime = Math.floor(new Date("2026-09-12T13:00:00Z").getTime() / 1000);
    const markers = buildTradeEntryMarkers([{
      trade_id: "trade-entry-1",
      side: "LONG",
      quantity: "1",
      entry_price: "100",
      exit_price: "105",
      opened_at: "2026-09-12T12:10:00Z",
      closed_at: "2026-09-12T14:00:00Z",
      net_pnl: "5",
      fees: "0.2",
      slippage_cost: "0.1",
    }], [candleTime]);
    expect(markers).toHaveLength(1);
    expect(markers[0]?.selection.objectType).toBe("ClosedTradeEntry");
    expect(markers[0]?.marker.shape).toBe("arrowUp");
    expect(markers[0]?.marker.text).toBeUndefined();
  });

});
