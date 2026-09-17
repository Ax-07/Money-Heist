import { describe, expect, it } from "vitest";
import { frontendAnalyticsOverlaysSchema } from "../analytics-overlay-schemas";

describe("frontendAnalyticsOverlaysSchema", () => {
  it("accepts an explicit unavailable old-run payload", () => {
    const parsed = frontendAnalyticsOverlaysSchema.parse({
      schema_version: "money-heist.frontend-analytics-overlays.v1",
      campaign_id: "old-run",
      role: "OOS",
      analytics_available: false,
      unavailable_reason: "PRECOMPUTED_ANALYTICS_UNAVAILABLE",
      source_backtest_run_id: null,
      analytics_run_id: null,
      scanner: [],
      funnel_stages: [],
      technical_events: [],
      structure: [],
      zigzag_pivots: [],
      patterns: [],
    });
    expect(parsed.analytics_available).toBe(false);
  });

  it("preserves distinct geometric and knowledge timestamps", () => {
    const parsed = frontendAnalyticsOverlaysSchema.parse({
      schema_version: "money-heist.frontend-analytics-overlays.v1",
      campaign_id: "run",
      role: "OOS",
      analytics_available: true,
      source_backtest_run_id: "backtest-1",
      analytics_run_id: "analytics-1",
      scanner: [],
      funnel_stages: [],
      technical_events: [],
      structure: [],
      zigzag_pivots: [{
        pivot_id: "p1", kind: "HIGH", symbol: "BTC/EUR", timeframe: "1h",
        pivot_at: "2026-01-01T08:00:00Z", confirmed_at: "2026-01-01T14:00:00Z",
        price: "100", atr_at_pivot: "2", reversal_multiple: "2", reversal_threshold: "4",
        amplitude_pct: null, amplitude_atr: null, bars_from_previous: null, pivot_fingerprint: "a".repeat(64),
      }],
      patterns: [],
    });
    expect(parsed.zigzag_pivots[0]?.pivot_at).not.toBe(parsed.zigzag_pivots[0]?.confirmed_at);
  });
});
