import { describe, expect, expectTypeOf, it } from "vitest";
import { marketCandlesQuery } from "./queries";
import {
  dashboardSnapshotSchema,
  decisionFunnelReportSchema,
  frontendCapabilitiesSchema,
  marketCandlesSchema,
  openAiModelCatalogSchema,
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

  it("preserves the canonical Decision Funnel in period summaries", () => {
    const report = decisionFunnelReportSchema.parse({
      schema_version: "money-heist.decision-funnel.v1",
      run_id: "run-1",
      dataset_id: "dataset-1",
      dataset_version: "v1",
      system_id: "balanced_v1",
      period_start: "2026-09-01T00:00:00Z",
      period_end: "2026-09-02T00:00:00Z",
      observation_counts: {
        pre_scanner_warmup_skipped: 35,
        pre_scanner_not_decision_close_skipped: 0,
      },
      counts: {
        candles_evaluated: 179,
        scanner_evaluations: 144,
        scanner_no_trigger: 72,
        scanner_triggered: 72,
        candidate_opportunities: 27,
        compute_gate_allowed: 27,
        compute_gate_blocked: 0,
        ai_orchestrations_triggered: 27,
        professor_plan_no_analysis: 0,
        orchestration_failed: 0,
        professor_no_trade: 17,
        trade_proposals_created: 10,
        risk_rejected: 7,
        risk_resized: 3,
        risk_approved: 0,
        paper_pipeline_failed: 0,
        duplicate_execution_blocked: 0,
        orders_submitted: 3,
        fills: 3,
      },
      reason_counts: [],
      post_hoc: {closed_trades: 2, broker_orders_total: 3, broker_fills_total: 3},
    });
    expect(report.counts.professor_no_trade).toBe(17);
    expect(report.counts.risk_resized).toBe(3);
    expect(report.post_hoc.closed_trades).toBe(2);
  });

  it("parses the verified OpenAI USD pricing catalog", () => {
    const catalog = openAiModelCatalogSchema.parse({
      schema_version: "money-heist.openai-model-catalog.v1",
      provider: "openai",
      pricing_currency: "USD",
      pricing_snapshot_at: "2026-09-13",
      models: [{
        model_id: "gpt-5.6-terra",
        display_name: "GPT-5.6 Terra",
        input_per_million_usd: "2.00",
        cached_input_per_million_usd: "0.20",
        output_per_million_usd: "12.00",
        reasoning_efforts: ["none", "low", "medium", "high", "xhigh", "max"],
        default_reasoning_effort: "medium",
        recommended: true,
        pricing_currency: "USD",
        pricing_tier: "STANDARD",
        pricing_source: "OPENAI_OFFICIAL",
        pricing_snapshot_at: "2026-09-13",
        pricing_valid_until: null,
        standard_context_max_tokens: 272000,
        source_url: "https://openai.com/api/pricing/",
        notes: [],
      }],
    });
    expect(catalog.models[0]?.input_per_million_usd).toBe("2.00");
    expect(catalog.models[0]?.pricing_currency).toBe("USD");
  });
});
