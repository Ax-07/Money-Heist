import { describe, expect, expectTypeOf, it } from "vitest";
import { marketCandlesQuery } from "./queries";
import {
  dashboardSnapshotSchema,
  frontendCapabilitiesSchema,
  marketCandlesSchema,
  riskDecisionSchema,
  type DashboardSnapshot,
  type MarketCandles,
} from "./schemas";

describe("critical API contracts", () => {
  it("fails closed on an unexpected realtime transport", () => {
    expect(() =>
      frontendCapabilitiesSchema.parse({
        schema_version: "v",
        runtime_mode: "PAPER",
        app_env: "test",
        default_system_id: "balanced_v1",
        market_symbols: [],
        market_timeframes: [],
        realtime_transport: "WEBSOCKET",
        live_environment: "disabled",
        live_system_id: null,
        live_timeframes: null,
        live_operational_state: "UNAVAILABLE",
        live_controls_exposed: false,
        chart_provider: "LIGHTWEIGHT_CHARTS",
        chart_data_source: "BACKEND",
        backtest_paper_only: true,
      }),
    ).toThrow();
  });

  it("preserves RiskDecision reason codes and authorized sizing", () => {
    const value = riskDecisionSchema.parse({
      risk_decision_id: "r",
      proposal_id: "p",
      status: "RESIZED",
      reason_codes: ["MAX_RISK_PER_TRADE"],
      approved_quantity: "0.00156",
      approved_risk_amount: "0.73",
      approved_notional: "99.49",
      created_at: "2026-09-12T12:00:00Z",
    });
    expect(value.status).toBe("RESIZED");
    expect(value.reason_codes).toEqual(["MAX_RISK_PER_TRADE"]);
    expect(value.approved_quantity).toBe("0.00156");
  });

  it("normalizes numeric decimals and applies array defaults", () => {
    const candles = marketCandlesSchema.parse({
      symbol: "BTC/EUR",
      timeframe: "1h",
      source: "fixture",
      candles: [
        {
          time: 1,
          open_time: "2026-09-13T00:00:00Z",
          close_time: "2026-09-13T01:00:00Z",
          open: 100,
          high: 101,
          low: 99,
          close: 100.5,
          volume: 2,
          is_closed: true,
        },
      ],
    });
    expect(candles.candles[0]?.open).toBe("100");

    const dashboard = dashboardSnapshotSchema.parse({
      schema_version: "v",
      generated_at: "2026-09-13T01:00:00Z",
      read_only: true,
      live_execution: false,
      execution_scope: "PAPER",
      system_state: "READY",
      systems: [],
      comparison: null,
    });
    expect(dashboard.opportunities).toEqual([]);
    expect(dashboard.decisions).toEqual([]);
    expect(dashboard.events).toEqual([]);
  });

  it("exposes parsed API output types to query consumers", () => {
    expectTypeOf<MarketCandles["candles"][number]["open"]>().toEqualTypeOf<string>();
    expectTypeOf<DashboardSnapshot["events"]>().toBeArray();
    expectTypeOf<Awaited<ReturnType<typeof marketCandlesQuery>>>().toEqualTypeOf<MarketCandles>();
  });
});
