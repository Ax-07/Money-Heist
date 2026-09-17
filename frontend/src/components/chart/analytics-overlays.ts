import type { SeriesMarker, Time } from "lightweight-charts";
import type {
  FrontendAnalyticsOverlays,
  PatternOverlay,
  StructureOverlay,
} from "@/lib/api/analytics-overlay-schemas";

import {
  DEFAULT_OVERLAY_VISIBILITY,
  type OverlayFilters,
  type OverlaySelection,
  type OverlayVisibility,
} from "@/lib/analytics-overlay-state";

export { DEFAULT_OVERLAY_VISIBILITY };
export type { OverlayFilters, OverlaySelection, OverlayVisibility };

export type OverlayMarker = {
  marker: SeriesMarker<Time>;
  selection: OverlaySelection;
  priority: number;
};

export type PatternSegmentModel = {
  id: string;
  status: string;
  points: Array<{ time: Time; value: number }>;
};

export type ChartOverlayModel = {
  markers: OverlayMarker[];
  zigzag: Array<{ time: Time; value: number }>;
  patternSegments: PatternSegmentModel[];
};

export function isoToChartTime(value: string): Time {
  return Math.floor(new Date(value).getTime() / 1000) as Time;
}

function isKnownAt(availableAt: string, cursorTime: number | null): boolean {
  return cursorTime === null || Number(isoToChartTime(availableAt)) <= cursorTime;
}

function marker(
  time: string,
  position: SeriesMarker<Time>["position"],
  shape: SeriesMarker<Time>["shape"],
  color: string,
  text: string,
): SeriesMarker<Time> {
  return { time: isoToChartTime(time), position, shape, color, text };
}

function scannerMarkers(
  overlays: FrontendAnalyticsOverlays,
  visibility: OverlayVisibility,
  cursorTime: number | null,
): OverlayMarker[] {
  return overlays.scanner.flatMap((item) => {
    if (!isKnownAt(item.observed_at, cursorTime)) return [];
    const classification = item.classification.toUpperCase();
    const candidate = classification === "CANDIDATE_OPPORTUNITY" || item.candidate_opportunity_id !== null;
    const below = classification === "TRIGGER_BELOW_CANDIDATE_THRESHOLD";
    const noTrigger = classification === "NO_TRIGGER";
    if (candidate && !visibility.scannerCandidates) return [];
    if (below && !visibility.scannerBelowThreshold) return [];
    if (noTrigger && !visibility.scannerNoTrigger) return [];
    if (!candidate && !below && !noTrigger) return [];
    const label = candidate ? `OPP ${item.priority_score}` : below ? `SCAN ${item.priority_score}` : "NO_TRIGGER";
    return [{
      marker: marker(
        item.observed_at,
        candidate ? "belowBar" : "aboveBar",
        candidate ? "arrowUp" : "circle",
        candidate ? "#8b5cf6" : "#64748b",
        label,
      ),
      priority: candidate ? 100 : below ? 20 : 1,
      selection: {
        objectType: candidate ? "CandidateOpportunity" : "ScannerEvaluation",
        objectId: item.candidate_opportunity_id ?? item.scanner_evaluation_id,
        opportunityId: item.candidate_opportunity_id ?? null,
        timestamp: item.observed_at,
        label,
        details: {
          classification: item.classification,
          priority_score: String(item.priority_score),
          candidate_threshold: String(item.candidate_threshold),
          score_margin: String(item.score_margin),
          triggers: item.triggers.join(", ") || "—",
          market_regime: item.market_regime ?? "—",
        },
      },
    }];
  });
}

function stageMarkers(
  overlays: FrontendAnalyticsOverlays,
  visibility: OverlayVisibility,
  cursorTime: number | null,
): OverlayMarker[] {
  return overlays.funnel_stages.flatMap<OverlayMarker>((stage): OverlayMarker[] => {
    const knowledgeAt = stage.operational_at ?? stage.market_as_of;
    if (!stage.reached || !isKnownAt(knowledgeAt, cursorTime)) return [];
    const name = stage.stage.toUpperCase();
    const result = (stage.stage_result ?? stage.stage_status ?? "").toUpperCase();
    const base = {
      objectId: stage.record_id,
      opportunityId: stage.opportunity_id,
      timestamp: stage.market_as_of,
    };
    if (name === "FINAL" || name.endsWith("_FINAL")) {
      if (!visibility.decisions || (result === "NO_TRADE" && !visibility.noTradeDecisions)) return [];
      const direction = result || "FINAL";
      return [{
        marker: marker(stage.market_as_of, direction === "SHORT" ? "aboveBar" : "belowBar", direction === "LONG" ? "arrowUp" : direction === "SHORT" ? "arrowDown" : "circle", "#a78bfa", direction),
        priority: 90,
        selection: {
          ...base,
          objectType: "ProfessorFinal",
          label: `FINAL ${direction}`,
          details: {
            result: direction,
            confidence: stage.confidence === null || stage.confidence === undefined ? "—" : String(stage.confidence),
            operational_at: stage.operational_at ?? "—",
            known_at: knowledgeAt,
          },
        },
      }];
    }
    if (name.includes("PALERMO")) {
      if (!visibility.palermo) return [];
      return [{
        marker: marker(stage.market_as_of, "aboveBar", "square", "#94a3b8", `PAL ${result || "—"}`),
        priority: 50,
        selection: {
          ...base,
          objectType: "PalermoReview",
          label: `Palermo ${result || "—"}`,
          details: {
            verdict: result || "—",
            severity: stage.severity === null || stage.severity === undefined ? "—" : String(stage.severity),
            reasons: stage.reason_codes.join(", ") || "—",
            operational_at: stage.operational_at ?? "—",
            known_at: knowledgeAt,
          },
        },
      }];
    }
    if (name === "RISK" || name.includes("RISK")) {
      if (!visibility.risk) return [];
      return [{
        marker: marker(stage.market_as_of, "aboveBar", "square", "#fb923c", `RISK ${result || "—"}`),
        priority: 80,
        selection: {
          ...base,
          objectType: "RiskDecision",
          label: `Risk ${result || "—"}`,
          details: {
            status: result || "—",
            reasons: stage.reason_codes.join(", ") || "—",
            operational_at: stage.operational_at ?? "—",
            known_at: knowledgeAt,
          },
        },
      }];
    }
    return [];
  });
}

function eventMarkers(
  overlays: FrontendAnalyticsOverlays,
  visibility: OverlayVisibility,
  filters: OverlayFilters,
  cursorTime: number | null,
): OverlayMarker[] {
  if (!visibility.technicalEvents) return [];
  return overlays.technical_events.flatMap((event) => {
    if (!isKnownAt(event.available_at, cursorTime)) return [];
    if (filters.technicalEventFamily && event.family !== filters.technicalEventFamily) return [];
    if (filters.technicalEventType && event.event_type !== filters.technicalEventType) return [];
    return [{
      marker: marker(event.event_at, "aboveBar", "circle", "#38bdf8", event.event_type),
      priority: 30,
      selection: {
        objectType: "TechnicalEventObservation",
        objectId: event.event_id,
        opportunityId: null,
        timestamp: event.event_at,
        label: event.event_type,
        details: {
          family: event.family,
          direction: event.direction,
          event_at: event.event_at,
          available_at: event.available_at,
        },
      },
    }];
  });
}

function structureMarkers(
  structure: StructureOverlay[],
  visibility: OverlayVisibility,
  cursorTime: number | null,
): OverlayMarker[] {
  if (!visibility.structure) return [];
  return structure.flatMap((observation) => {
    if (!isKnownAt(observation.as_of, cursorTime)) return [];
    return observation.timeframes.flatMap((item) => {
      const breakout = item.breakout_state.toUpperCase();
      if (breakout === "INSIDE_RANGE" || breakout === "UNKNOWN") return [];
      return [{
        marker: marker(observation.as_of, breakout.includes("DOWN") ? "aboveBar" : "belowBar", "circle", "#cbd5e1", breakout),
        priority: 25,
        selection: {
          objectType: "MarketStructure",
          objectId: `${observation.structure_id}:${item.timeframe}`,
          opportunityId: null,
          timestamp: observation.as_of,
          label: `${item.timeframe} ${breakout}`,
          details: {
            swing_structure: item.swing_structure,
            prior_range_high: item.prior_range_high ?? "—",
            prior_range_low: item.prior_range_low ?? "—",
            range_location: item.range_location,
          },
        },
      }];
    });
  });
}


function pivotMarkers(
  overlays: FrontendAnalyticsOverlays,
  visibility: OverlayVisibility,
  cursorTime: number | null,
): OverlayMarker[] {
  if (!visibility.zigzag) return [];
  return overlays.zigzag_pivots.flatMap((pivot) => {
    if (!isKnownAt(pivot.confirmed_at, cursorTime)) return [];
    const high = pivot.kind.toUpperCase() === "HIGH";
    return [{
      marker: marker(
        pivot.pivot_at,
        high ? "aboveBar" : "belowBar",
        "circle",
        "#a78bfa",
        high ? "ZZ H" : "ZZ L",
      ),
      priority: 35,
      selection: {
        objectType: "CausalZigZagPivot",
        objectId: pivot.pivot_id,
        opportunityId: null,
        timestamp: pivot.pivot_at,
        label: `ZigZag ${pivot.kind}`,
        details: {
          price: pivot.price,
          pivot_at: pivot.pivot_at,
          confirmed_at: pivot.confirmed_at,
          atr_at_pivot: pivot.atr_at_pivot,
          reversal_threshold: pivot.reversal_threshold,
          amplitude_pct: pivot.amplitude_pct ?? "—",
          amplitude_atr: pivot.amplitude_atr ?? "—",
        },
      },
    }];
  });
}

function patternMarkers(
  patterns: PatternOverlay[],
  visibility: OverlayVisibility,
  cursorTime: number | null,
): OverlayMarker[] {
  if (!visibility.patterns) return [];
  return patterns.flatMap((pattern) => {
    const status = patternStatusAt(pattern, cursorTime);
    if (status === null || (status === "FORMING" && !visibility.formingPatterns)) return [];
    const knownTransition = pattern.transitions
      .filter((transition) => isKnownAt(transition.available_at, cursorTime))
      .at(-1);
    if (!knownTransition) return [];
    const firstPoint = pattern.points[0];
    const lastPoint = pattern.points.at(-1);
    const geometryAt = lastPoint?.pivot_at ?? firstPoint?.pivot_at ?? pattern.detected_at;
    return [{
      marker: marker(geometryAt, "aboveBar", "square", "#c4b5fd", `${pattern.pattern_type} ${status}`),
      priority: 40,
      selection: {
        objectType: "PatternOccurrence",
        objectId: pattern.pattern_id,
        opportunityId: null,
        timestamp: geometryAt,
        label: `${pattern.pattern_type} · ${status}`,
        details: {
          status,
          pivot_source: pattern.pivot_source,
          detected_at: pattern.detected_at,
          confirmed_at: pattern.confirmed_at ?? "—",
          failed_at: pattern.failed_at ?? "—",
          invalidated_at: pattern.invalidated_at ?? "—",
          known_at: knownTransition.available_at,
          source_pivots: pattern.points.map((point) => point.pivot_id).join(", "),
        },
      },
    }];
  });
}

export function patternStatusAt(pattern: PatternOverlay, cursorTime: number | null): string | null {
  const visible = pattern.transitions.filter((transition) => isKnownAt(transition.available_at, cursorTime));
  return visible.length === 0 ? null : visible[visible.length - 1]!.status;
}

function patternSegments(
  patterns: PatternOverlay[],
  visibility: OverlayVisibility,
  cursorTime: number | null,
): PatternSegmentModel[] {
  if (!visibility.patterns) return [];
  return patterns.flatMap((pattern) => {
    const status = patternStatusAt(pattern, cursorTime);
    if (status === null || (status === "FORMING" && !visibility.formingPatterns)) return [];
    return pattern.segments.map((segment, index) => ({
      id: `${pattern.pattern_id}:${segment.role}:${index}`,
      status,
      points: [
        { time: isoToChartTime(segment.start_at), value: Number(segment.start_price) },
        { time: isoToChartTime(segment.end_at), value: Number(segment.end_price) },
      ],
    }));
  });
}

export function buildChartOverlayModel(
  overlays: FrontendAnalyticsOverlays | null | undefined,
  visibility: OverlayVisibility,
  filters: OverlayFilters,
  cursorTime: number | null,
): ChartOverlayModel {
  if (!overlays?.analytics_available) return { markers: [], zigzag: [], patternSegments: [] };
  const markers = [
    ...scannerMarkers(overlays, visibility, cursorTime),
    ...stageMarkers(overlays, visibility, cursorTime),
    ...eventMarkers(overlays, visibility, filters, cursorTime),
    ...structureMarkers(overlays.structure, visibility, cursorTime),
    ...pivotMarkers(overlays, visibility, cursorTime),
    ...patternMarkers(overlays.patterns, visibility, cursorTime),
  ].sort((left, right) => Number(left.marker.time) - Number(right.marker.time) || right.priority - left.priority);
  const zigzag = visibility.zigzag
    ? overlays.zigzag_pivots
        .filter((pivot) => isKnownAt(pivot.confirmed_at, cursorTime))
        .sort((left, right) => Number(isoToChartTime(left.pivot_at)) - Number(isoToChartTime(right.pivot_at)))
        .map((pivot) => ({ time: isoToChartTime(pivot.pivot_at), value: Number(pivot.price) }))
    : [];
  return {
    markers,
    zigzag,
    patternSegments: patternSegments(overlays.patterns, visibility, cursorTime),
  };
}

export function selectionAtTime(markers: OverlayMarker[], time: Time): OverlaySelection | null {
  return markers
    .filter((item) => Number(item.marker.time) === Number(time))
    .sort((left, right) => right.priority - left.priority)[0]?.selection ?? null;
}
