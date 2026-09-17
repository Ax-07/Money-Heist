import { describe, expect, it } from "vitest";

import {
  frontendAnalyticsProjectionSchema,
  frontendFunnelStageSchema,
  frontendScannerAnalyticsProjectionSchema,
} from "../decision-intelligence-schemas";

const base = { campaign_id: "campaign-1", role: "OOS" as const };

describe("Decision Intelligence frontend contracts", () => {
  it("parses an old run without Analytics", () => {
    const parsed = frontendAnalyticsProjectionSchema.parse({
      schema_version: "money-heist.frontend-analytics-projection.v1",
      ...base,
      analytics_available: false,
      unavailable_reason: "PRECOMPUTED_ANALYTICS_UNAVAILABLE",
      run: null,
      snapshots: [],
      opportunity_count: 0,
      scanner_evaluation_count: 0,
      decision_record_count: 0,
      funnel_stage_count: 0,
    });
    expect(parsed.analytics_available).toBe(false);
  });

  it("parses optional Scanner Analytics", () => {
    const parsed = frontendScannerAnalyticsProjectionSchema.parse({
      schema_version: "money-heist.frontend-scanner-analytics.v1",
      ...base,
      analytics_available: false,
      unavailable_reason: "PRECOMPUTED_ANALYTICS_UNAVAILABLE",
      total_scanner_evaluations: 0,
      matched_analytics: 0,
      unmatched_analytics: 0,
      no_trigger_count: 0,
      below_threshold_count: 0,
      candidate_count: 0,
      records: [],
    });
    expect(parsed.records).toHaveLength(0);
  });

  it("preserves market and operational timestamps as distinct fields", () => {
    const parsed = frontendFunnelStageSchema.parse({
      record_id: "stage-1",
      record_fingerprint: "a".repeat(64),
      decision_intelligence_record_id: "decision-1",
      opportunity_id: "opp-1",
      stage: "RISK",
      stage_order: 70,
      reached: true,
      stage_status: "COMPLETED",
      stage_result: "RESIZED",
      reason_codes: [],
      selected_agents: [],
      market_as_of: "2026-09-17T12:00:00Z",
      operational_at: "2026-09-17T12:00:06Z",
      source_projection_fingerprint: "b".repeat(64),
      analytics: {
        status: "MATCHED",
        analytics_run_id: "analytics-1",
        analytics_snapshot_id: "snapshot-1",
        analytics_snapshot_fingerprint: "c".repeat(64),
        analytics_as_of: "2026-09-17T12:00:00Z",
        source_cursor_fingerprint: "d".repeat(64),
        diagnostics: [],
      },
    });
    expect(parsed.market_as_of).toBe("2026-09-17T12:00:00Z");
    expect(parsed.operational_at).toBe("2026-09-17T12:00:06Z");
  });
});
