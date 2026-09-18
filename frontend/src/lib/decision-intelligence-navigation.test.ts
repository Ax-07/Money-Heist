import { describe, expect, it } from "vitest";
import { DEFAULT_OVERLAY_FILTERS } from "./analytics-overlay-state";
import type { FrontendAnalyticsOverlays } from "./api/analytics-overlay-schemas";
import {
  applyDecisionIntelligenceFilters,
  buildFilteredNavigationItems,
  buildNavigationItems,
  navigationNeighbors,
  patternStatusAtTimestamp,
} from "./decision-intelligence-navigation";

const t = (hour: number, seconds = 0) => `2026-01-01T${String(hour).padStart(2, "0")}:00:${String(seconds).padStart(2, "0")}Z`;
const seconds = (value: string) => Math.floor(new Date(value).getTime() / 1000);

const analytics = { status: "MATCHED", analytics_run_id: "analytics-1", diagnostics: [] };

function stage(
  recordId: string,
  opportunityId: string,
  name: string,
  result: string,
  marketAsOf: string,
  operationalAt: string,
  order: number,
) {
  return {
    record_id: recordId,
    record_fingerprint: "a".repeat(64),
    decision_intelligence_record_id: `decision-${opportunityId}`,
    opportunity_id: opportunityId,
    stage: name,
    stage_order: order,
    stage_instance_id: null,
    stage_instance_order: null,
    agent_id: null,
    agent_request_id: null,
    agent_prompt_version: null,
    agent_route_id: null,
    agent_model_id: null,
    reached: true,
    stage_status: result,
    stage_result: result,
    reason_codes: [],
    selected_agents: [],
    confidence: null,
    severity: null,
    failure_code: null,
    failure_stage: null,
    failure_agent_id: null,
    market_as_of: marketAsOf,
    operational_at: operationalAt,
    source_artifact_ref: null,
    source_artifact_fingerprint: null,
    source_projection_fingerprint: "b".repeat(64),
    analytics,
  };
}

function overlays(): FrontendAnalyticsOverlays {
  return {
    schema_version: "money-heist.frontend-analytics-overlays.v1",
    campaign_id: "campaign-1",
    role: "OOS",
    analytics_available: true,
    source_backtest_run_id: "run-1",
    analytics_run_id: "analytics-1",
    scanner: [
      {
        record_id: "scan-record-0",
        scanner_evaluation_id: "scan-0",
        observed_at: t(9),
        symbol: "BTC/EUR",
        decision_timeframe: "1h",
        classification: "NO_TRIGGER",
        score: 10,
        priority_score: 10,
        candidate_threshold: 60,
        score_margin: -50,
        triggers: [],
        market_regime: "RANGE",
        candidate_opportunity_id: null,
        analytics,
      },
      {
        record_id: "scan-record-below",
        scanner_evaluation_id: "scan-below",
        observed_at: t(10),
        symbol: "BTC/EUR",
        decision_timeframe: "1h",
        classification: "TRIGGER_BELOW_CANDIDATE_THRESHOLD",
        score: 55,
        priority_score: 55,
        candidate_threshold: 60,
        score_margin: -5,
        triggers: ["VOLUME_EXPANSION", "RANGE_BREAK"],
        market_regime: "RANGE",
        candidate_opportunity_id: null,
        analytics,
      },
      {
        record_id: "scan-record-1",
        scanner_evaluation_id: "scan-1",
        observed_at: t(18),
        symbol: "BTC/EUR",
        decision_timeframe: "1h",
        classification: "CANDIDATE_OPPORTUNITY",
        score: 62,
        priority_score: 62,
        candidate_threshold: 60,
        score_margin: 2,
        triggers: ["RANGE_BREAK"],
        market_regime: "TREND",
        candidate_opportunity_id: "opp-1",
        analytics,
      },
      {
        record_id: "scan-record-2",
        scanner_evaluation_id: "scan-2",
        observed_at: t(18, 1),
        symbol: "BTC/EUR",
        decision_timeframe: "1h",
        classification: "CANDIDATE_OPPORTUNITY",
        score: 80,
        priority_score: 80,
        candidate_threshold: 60,
        score_margin: 20,
        triggers: ["MOMENTUM_EXTREME"],
        market_regime: "TREND",
        candidate_opportunity_id: "opp-2",
        analytics,
      },
      {
        record_id: "scan-record-3",
        scanner_evaluation_id: "scan-3",
        observed_at: t(18, 2),
        symbol: "BTC/EUR",
        decision_timeframe: "1h",
        classification: "CANDIDATE_OPPORTUNITY",
        score: 70,
        priority_score: 70,
        candidate_threshold: 60,
        score_margin: 10,
        triggers: ["VOLATILITY_EXPANSION"],
        market_regime: "RANGE",
        candidate_opportunity_id: "opp-3",
        analytics,
      },
    ],
    funnel_stages: [
      stage("pal-1", "opp-1", "PALERMO", "CAUTION", t(18), t(18, 2), 3),
      stage("final-1", "opp-1", "FINAL", "NO_TRADE", t(18), t(18, 3), 4),
      stage("risk-1", "opp-1", "RISK", "REJECTED", t(18), t(18, 5), 5),
      stage("pal-2", "opp-2", "PALERMO", "CLEAR", t(18), t(18, 2), 3),
      stage("final-2", "opp-2", "FINAL", "LONG", t(18), t(18, 3), 4),
      stage("risk-2", "opp-2", "RISK", "RESIZED", t(18), t(18, 5), 5),
      stage("pal-3", "opp-3", "PALERMO", "REJECT", t(18), t(18, 3), 3),
      stage("final-3", "opp-3", "FINAL", "SHORT", t(18), t(18, 4), 4),
      stage("risk-3", "opp-3", "RISK", "APPROVED", t(18), t(18, 6), 5),
    ],
    technical_events: [{
      event_id: "event-1",
      event_type: "RSI_CROSS_50_UP",
      family: "MOMENTUM",
      direction: "BULLISH",
      symbol: "BTC/EUR",
      timeframe: "1h",
      event_at: t(12),
      available_at: t(13),
      event_fingerprint: "c".repeat(64),
      evidence: {},
    }],
    structure: [],
    zigzag_pivots: [{
      pivot_id: "pivot-1",
      kind: "HIGH",
      symbol: "BTC/EUR",
      timeframe: "1h",
      pivot_at: t(8),
      confirmed_at: t(14),
      price: "100",
      atr_at_pivot: "2",
      reversal_multiple: "2",
      reversal_threshold: "4",
      amplitude_pct: null,
      amplitude_atr: null,
      bars_from_previous: null,
      pivot_fingerprint: "d".repeat(64),
    }],
    patterns: [{
      pattern_id: "pattern-1",
      pattern_type: "DOUBLE_BOTTOM",
      family: "REVERSAL",
      direction: "BULLISH",
      symbol: "BTC/EUR",
      timeframe: "1h",
      start_at: t(8),
      detected_at: t(15),
      end_at: t(20),
      confirmed_at: t(18),
      failed_at: t(20),
      invalidated_at: null,
      current_status: "FAILED",
      pivot_source: "CAUSAL_ZIGZAG",
      points: [{ role: "right_low", pivot_id: "pivot-1", kind: "LOW", price: "90", pivot_at: t(8), confirmed_at: t(14) }],
      segments: [],
      breakout_level: "95",
      metrics: {},
      diagnostic_flags: [],
      transitions: [
        { status: "FORMING", occurred_at: t(15), available_at: t(15), reason: "forming", evidence: {}, fingerprint: "e".repeat(64) },
        { status: "CONFIRMED", occurred_at: t(18), available_at: t(18), reason: "confirmed", evidence: {}, fingerprint: "f".repeat(64) },
        { status: "FAILED", occurred_at: t(20), available_at: t(20), reason: "failed", evidence: {}, fingerprint: "1".repeat(64) },
      ],
      pattern_fingerprint: "2".repeat(64),
    }],
  };
}

describe("Decision Intelligence filtering", () => {
  it("filters Scanner classifications and uses OR inside one dimension", () => {
    const items = buildNavigationItems(overlays(), seconds(t(19)));
    const result = applyDecisionIntelligenceFilters(items, {
      ...DEFAULT_OVERLAY_FILTERS,
      scannerClassifications: ["NO_TRIGGER", "TRIGGER_BELOW_CANDIDATE_THRESHOLD"],
    });
    expect(result.map(item => item.selection.details.classification)).toEqual([
      "NO_TRIGGER",
      "TRIGGER_BELOW_CANDIDATE_THRESHOLD",
    ]);
  });

  it("filters one or several triggers with inclusive score bounds", () => {
    const result = buildFilteredNavigationItems(overlays(), {
      ...DEFAULT_OVERLAY_FILTERS,
      scannerTriggers: ["RANGE_BREAK", "VOLUME_EXPANSION"],
      scannerScoreMin: 55,
      scannerScoreMax: 62,
    }, seconds(t(19)));
    expect(result.map(item => item.selection.objectId)).toEqual(["scan-below", "opp-1"]);
  });

  it("filters every projected FINAL value", () => {
    for (const [value, opportunityId] of [["NO_TRADE", "opp-1"], ["LONG", "opp-2"], ["SHORT", "opp-3"]] as const) {
      const result = buildFilteredNavigationItems(overlays(), {
        ...DEFAULT_OVERLAY_FILTERS,
        professorFinal: [value],
      }, seconds(t(19)));
      expect(result.map(item => item.opportunityId)).toEqual([opportunityId]);
    }
  });

  it("filters every projected Palermo value", () => {
    for (const [value, opportunityId] of [["CAUTION", "opp-1"], ["CLEAR", "opp-2"], ["REJECT", "opp-3"]] as const) {
      const result = buildFilteredNavigationItems(overlays(), {
        ...DEFAULT_OVERLAY_FILTERS,
        palermoVerdicts: [value],
      }, seconds(t(19)));
      expect(result.map(item => item.opportunityId)).toEqual([opportunityId]);
    }
  });

  it("filters every projected Risk value", () => {
    for (const [value, opportunityId] of [["REJECTED", "opp-1"], ["RESIZED", "opp-2"], ["APPROVED", "opp-3"]] as const) {
      const result = buildFilteredNavigationItems(overlays(), {
        ...DEFAULT_OVERLAY_FILTERS,
        riskStatuses: [value],
      }, seconds(t(19)));
      expect(result.map(item => item.opportunityId)).toEqual([opportunityId]);
    }
  });

  it("filters Pattern direction and pivot source", () => {
    const result = buildFilteredNavigationItems(overlays(), {
      ...DEFAULT_OVERLAY_FILTERS,
      patternTypes: ["DOUBLE_BOTTOM"],
      patternStatuses: ["CONFIRMED"],
      patternDirections: ["BULLISH"],
      patternPivotSources: ["CAUSAL_ZIGZAG"],
    }, seconds(t(19)));
    expect(result.map(item => item.selection.objectId)).toEqual(["pattern-1"]);

    const noMatch = buildFilteredNavigationItems(overlays(), {
      ...DEFAULT_OVERLAY_FILTERS,
      patternDirections: ["BEARISH"],
    }, seconds(t(19)));
    expect(noMatch).toEqual([]);
  });

  it("does not expose a future Risk match before the Risk stage is operational", () => {
    const result = buildFilteredNavigationItems(overlays(), {
      ...DEFAULT_OVERLAY_FILTERS,
      scannerClassifications: ["CANDIDATE_OPPORTUNITY"],
      riskStatuses: ["REJECTED"],
    }, seconds(t(18, 4)));
    expect(result).toEqual([]);
  });

  it("applies OR for Risk statuses and AND with Palermo", () => {
    const result = buildFilteredNavigationItems(overlays(), {
      ...DEFAULT_OVERLAY_FILTERS,
      riskStatuses: ["REJECTED", "RESIZED"],
      palermoVerdicts: ["CAUTION"],
    }, seconds(t(19)));
    expect(result).toHaveLength(1);
    expect(result[0]?.type).toBe("RiskDecision");
    expect(result[0]?.opportunityId).toBe("opp-1");
  });

  it("filters Professor FINAL and Pattern status without using the future status", () => {
    const beforeFailure = buildFilteredNavigationItems(overlays(), {
      ...DEFAULT_OVERLAY_FILTERS,
      professorFinal: ["NO_TRADE"],
      patternTypes: ["DOUBLE_BOTTOM"],
      patternStatuses: ["CONFIRMED"],
    }, seconds(t(19)));
    expect(beforeFailure.map(item => item.opportunityId)).toEqual(["opp-1"]);

    const afterFailure = buildFilteredNavigationItems(overlays(), {
      ...DEFAULT_OVERLAY_FILTERS,
      patternTypes: ["DOUBLE_BOTTOM"],
      patternStatuses: ["CONFIRMED"],
    }, seconds(t(20)));
    expect(afterFailure).toEqual([]);
  });

  it("filters Technical Events by family, type and direction", () => {
    const result = buildFilteredNavigationItems(overlays(), {
      ...DEFAULT_OVERLAY_FILTERS,
      technicalEventFamilies: ["MOMENTUM"],
      technicalEventTypes: ["RSI_CROSS_50_UP"],
      technicalEventDirections: ["BULLISH"],
    }, seconds(t(19)));
    expect(result.map(item => item.selection.objectId)).toEqual(["event-1"]);
  });

  it("keeps same-timestamp Technical Event facets object-specific", () => {
    const data = overlays();
    data.technical_events.push({
      ...data.technical_events[0]!,
      event_id: "event-2",
      event_type: "VOLUME_SPIKE",
      family: "VOLUME",
      direction: "NEUTRAL",
      event_fingerprint: "9".repeat(64),
    });
    const result = buildFilteredNavigationItems(data, {
      ...DEFAULT_OVERLAY_FILTERS,
      technicalEventTypes: ["RSI_CROSS_50_UP"],
    }, seconds(t(19)));
    expect(result.map(item => item.selection.objectId)).toEqual(["event-1"]);
  });

  it("keeps same-timestamp Pattern facets occurrence-specific", () => {
    const data = overlays();
    data.patterns.push({
      ...data.patterns[0]!,
      pattern_id: "pattern-2",
      pattern_type: "DOUBLE_TOP",
      direction: "BEARISH",
      pattern_fingerprint: "8".repeat(64),
    });
    const result = buildFilteredNavigationItems(data, {
      ...DEFAULT_OVERLAY_FILTERS,
      patternTypes: ["DOUBLE_BOTTOM"],
    }, seconds(t(19)));
    expect(result.map(item => item.selection.objectId)).toEqual(["pattern-1"]);
  });
});

describe("causal navigation timestamps", () => {
  it("uses available_at, confirmed_at and operational_at rather than geometric timestamps", () => {
    const items = buildNavigationItems(overlays(), seconds(t(19)));
    const event = items.find(item => item.type === "TechnicalEventObservation");
    const pivot = items.find(item => item.type === "CausalZigZagPivot");
    const pattern = items.find(item => item.type === "PatternOccurrence");
    const risk = items.find(item => item.selection.objectId === "risk-1");

    expect(event?.selection.timestamp).toBe(t(12));
    expect(event?.timestamp).toBe(t(13));
    expect(pivot?.selection.timestamp).toBe(t(8));
    expect(pivot?.timestamp).toBe(t(14));
    expect(pattern?.timestamp).toBe(t(18));
    expect(risk?.selection.timestamp).toBe(t(18));
    expect(risk?.timestamp).toBe(t(18, 5));
  });

  it("reports the Pattern status causal to the requested cursor", () => {
    const pattern = overlays().patterns[0]!;
    expect(patternStatusAtTimestamp(pattern, seconds(t(19)))).toBe("CONFIRMED");
    expect(patternStatusAtTimestamp(pattern, seconds(t(20)))).toBe("FAILED");
  });

  it("orders equal timestamps deterministically by canonical type then stable id", () => {
    const items = buildNavigationItems(overlays(), seconds(t(19)));
    const at180005 = items.filter(item => item.timestamp === t(18, 5));
    expect(at180005.map(item => item.selection.objectId)).toEqual(["risk-1", "risk-2"]);
  });

  it("disables navigation at boundaries instead of wrapping", () => {
    const items = buildFilteredNavigationItems(overlays(), {
      ...DEFAULT_OVERLAY_FILTERS,
      riskStatuses: ["REJECTED", "RESIZED"],
    }, seconds(t(19)));
    const first = navigationNeighbors(items, items[0]!.selection, seconds(t(19)));
    const last = navigationNeighbors(items, items.at(-1)!.selection, seconds(t(19)));
    expect(first.previous).toBeNull();
    expect(first.next?.selection.objectId).toBe("risk-2");
    expect(last.next).toBeNull();
    expect(last.previous?.selection.objectId).toBe("risk-1");
  });
});
