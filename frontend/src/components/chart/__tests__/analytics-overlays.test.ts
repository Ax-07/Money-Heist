import { describe, expect, it } from "vitest";
import { DEFAULT_OVERLAY_FILTERS } from "@/lib/analytics-overlay-state";
import type { FrontendAnalyticsOverlays } from "@/lib/api/analytics-overlay-schemas";
import {
  DEFAULT_OVERLAY_VISIBILITY,
  buildChartOverlayModel,
  isoToChartTime,
  patternStatusAt,
  selectionAtTime,
} from "../analytics-overlays";

const t = (hour: number) => `2026-01-01T${String(hour).padStart(2, "0")}:00:00Z`;

function baseOverlays(): FrontendAnalyticsOverlays {
  return {
    schema_version: "money-heist.frontend-analytics-overlays.v1",
    campaign_id: "campaign-1",
    role: "OOS",
    analytics_available: true,
    source_backtest_run_id: "run-1",
    analytics_run_id: "analytics-1",
    scanner: [],
    funnel_stages: [],
    technical_events: [],
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
      pivot_fingerprint: "a".repeat(64),
    }],
    patterns: [{
      pattern_id: "pattern-1",
      pattern_type: "DOUBLE_TOP",
      family: "REVERSAL",
      direction: "BEARISH",
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
      points: [],
      segments: [{ role: "neckline", start_at: t(8), start_price: "95", end_at: t(15), end_price: "95", slope_per_bar: "0" }],
      breakout_level: "95",
      metrics: {},
      diagnostic_flags: [],
      transitions: [
        { status: "FORMING", occurred_at: t(15), available_at: t(15), reason: "forming", evidence: {}, fingerprint: "b".repeat(64) },
        { status: "CONFIRMED", occurred_at: t(18), available_at: t(18), reason: "confirmed", evidence: {}, fingerprint: "c".repeat(64) },
        { status: "FAILED", occurred_at: t(20), available_at: t(20), reason: "failed", evidence: {}, fingerprint: "d".repeat(64) },
      ],
      pattern_fingerprint: "e".repeat(64),
    }],
  };
}

describe("analytics overlay causal mapping", () => {
  it("uses pivot_at for geometry but hides a pivot until confirmed_at", () => {
    const overlays = baseOverlays();
    const before = buildChartOverlayModel(overlays, DEFAULT_OVERLAY_VISIBILITY, DEFAULT_OVERLAY_FILTERS, Number(isoToChartTime(t(10))));
    expect(before.zigzag).toEqual([]);

    const after = buildChartOverlayModel(overlays, DEFAULT_OVERLAY_VISIBILITY, DEFAULT_OVERLAY_FILTERS, Number(isoToChartTime(t(14))));
    expect(after.zigzag).toEqual([{ time: isoToChartTime(t(8)), value: 100 }]);
    const pivot = after.markers.find(item => item.selection.objectType === "CausalZigZagPivot");
    expect(pivot?.selection.timestamp).toBe(t(8));
    expect(pivot?.selection.navigationTimestamp).toBe(t(14));
  });

  it("does not back-propagate a future FAILED pattern status", () => {
    const pattern = baseOverlays().patterns[0]!;
    expect(patternStatusAt(pattern, Number(isoToChartTime(t(19))))).toBe("CONFIRMED");
    expect(patternStatusAt(pattern, Number(isoToChartTime(t(20))))).toBe("FAILED");

    const at19 = buildChartOverlayModel(baseOverlays(), DEFAULT_OVERLAY_VISIBILITY, DEFAULT_OVERLAY_FILTERS, Number(isoToChartTime(t(19))));
    expect(at19.patternSegments[0]?.status).toBe("CONFIRMED");
    const selected = at19.markers.find(item => item.selection.objectType === "PatternOccurrence")?.selection;
    expect(selected?.navigationTimestamp).toBe(t(18));
  });

  it("keeps NO_TRIGGER hidden by default and selects CandidateOpportunity by stable id", () => {
    const overlays = baseOverlays();
    const analytics = { status: "MATCHED", analytics_run_id: "analytics-1", diagnostics: [] };
    overlays.scanner = [
      {
        record_id: "scan-record-1",
        scanner_evaluation_id: "scan-1",
        observed_at: t(16),
        symbol: "BTC/EUR",
        decision_timeframe: "1h",
        classification: "NO_TRIGGER",
        score: 10,
        priority_score: 10,
        candidate_threshold: 60,
        score_margin: -50,
        triggers: [],
        market_regime: null,
        candidate_opportunity_id: null,
        analytics,
      },
      {
        record_id: "scan-record-2",
        scanner_evaluation_id: "scan-2",
        observed_at: t(17),
        symbol: "BTC/EUR",
        decision_timeframe: "1h",
        classification: "CANDIDATE_OPPORTUNITY",
        score: 82,
        priority_score: 82,
        candidate_threshold: 60,
        score_margin: 22,
        triggers: ["breakout"],
        market_regime: "TREND",
        candidate_opportunity_id: "opp-1",
        analytics,
      },
    ];

    const model = buildChartOverlayModel(overlays, DEFAULT_OVERLAY_VISIBILITY, DEFAULT_OVERLAY_FILTERS, Number(isoToChartTime(t(18))));
    expect(model.markers.some(item => item.selection.objectType === "ScannerEvaluation")).toBe(false);
    const selected = selectionAtTime(model.markers, isoToChartTime(t(17)));
    expect(selected?.objectType).toBe("CandidateOpportunity");
    expect(selected?.opportunityId).toBe("opp-1");
    expect(selected?.navigationTimestamp).toBe(t(17));
  });
});

describe("overlay visibility and filters", () => {
  it("removes and restores ZigZag without changing causal geometry", () => {
    const overlays = baseOverlays();
    const hidden = buildChartOverlayModel(
      overlays,
      { ...DEFAULT_OVERLAY_VISIBILITY, zigzag: false },
      DEFAULT_OVERLAY_FILTERS,
      Number(isoToChartTime(t(18))),
    );
    expect(hidden.zigzag).toEqual([]);
    expect(hidden.markers.some(item => item.selection.objectType === "CausalZigZagPivot")).toBe(false);

    const visible = buildChartOverlayModel(
      overlays,
      DEFAULT_OVERLAY_VISIBILITY,
      DEFAULT_OVERLAY_FILTERS,
      Number(isoToChartTime(t(18))),
    );
    expect(visible.zigzag[0]?.time).toBe(isoToChartTime(t(8)));
    expect(visible.markers.some(item => item.selection.objectType === "CausalZigZagPivot")).toBe(true);
  });

  it("filters Technical Events through the canonical navigation filter semantics", () => {
    const overlays = baseOverlays();
    overlays.technical_events = [
      {
        event_id: "event-rsi",
        event_type: "RSI_CROSS_50_UP",
        family: "MOMENTUM",
        direction: "BULLISH",
        symbol: "BTC/EUR",
        timeframe: "1h",
        event_at: t(12),
        available_at: t(13),
        event_fingerprint: "f".repeat(64),
        evidence: {},
      },
      {
        event_id: "event-volume",
        event_type: "VOLUME_SPIKE_20",
        family: "VOLUME",
        direction: "NEUTRAL",
        symbol: "BTC/EUR",
        timeframe: "1h",
        event_at: t(13),
        available_at: t(13),
        event_fingerprint: "1".repeat(64),
        evidence: {},
      },
    ];
    const model = buildChartOverlayModel(
      overlays,
      { ...DEFAULT_OVERLAY_VISIBILITY, technicalEvents: true },
      {
        ...DEFAULT_OVERLAY_FILTERS,
        technicalEventFamilies: ["MOMENTUM"],
        technicalEventTypes: ["RSI_CROSS_50_UP"],
      },
      Number(isoToChartTime(t(18))),
    );
    const events = model.markers.filter(item => item.selection.objectType === "TechnicalEventObservation");
    expect(events).toHaveLength(1);
    expect(events[0]?.selection.objectId).toBe("event-rsi");
    expect(events[0]?.selection.details.available_at).toBe(t(13));
    expect(events[0]?.selection.navigationTimestamp).toBe(t(13));
  });
});

describe("decision timestamp causality", () => {
  it("uses operational_at for knowledge/navigation without moving market geometry", () => {
    const overlays = baseOverlays();
    overlays.funnel_stages = [{
      record_id: "stage-1",
      record_fingerprint: "a".repeat(64),
      decision_intelligence_record_id: "decision-1",
      opportunity_id: "opp-1",
      stage: "FINAL",
      stage_order: 4,
      stage_instance_id: null,
      stage_instance_order: null,
      agent_id: "professor",
      agent_request_id: null,
      agent_prompt_version: null,
      agent_route_id: null,
      agent_model_id: null,
      reached: true,
      stage_status: "LONG",
      stage_result: "LONG",
      reason_codes: [],
      selected_agents: [],
      confidence: 0.8,
      severity: null,
      failure_code: null,
      failure_stage: null,
      failure_agent_id: null,
      market_as_of: t(18),
      operational_at: t(19),
      source_artifact_ref: null,
      source_artifact_fingerprint: null,
      source_projection_fingerprint: "b".repeat(64),
      analytics: { status: "MATCHED", analytics_run_id: "analytics-1", diagnostics: [] },
    }];
    const before = buildChartOverlayModel(
      overlays,
      DEFAULT_OVERLAY_VISIBILITY,
      DEFAULT_OVERLAY_FILTERS,
      Number(isoToChartTime(t(18))),
    );
    expect(before.markers.some(item => item.selection.objectType === "ProfessorFinal")).toBe(false);
    const after = buildChartOverlayModel(
      overlays,
      DEFAULT_OVERLAY_VISIBILITY,
      DEFAULT_OVERLAY_FILTERS,
      Number(isoToChartTime(t(19))),
    );
    const final = after.markers.find(item => item.selection.objectType === "ProfessorFinal");
    expect(final?.marker.time).toBe(isoToChartTime(t(18)));
    expect(final?.selection.details.known_at).toBe(t(19));
    expect(final?.selection.navigationTimestamp).toBe(t(19));
  });
});
