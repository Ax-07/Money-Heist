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
import {
  buildFilteredNavigationItems,
  overlaySelectionKey,
  patternStatusAtTimestamp,
} from "@/lib/decision-intelligence-navigation";

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
  allowed: Set<string>,
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
    const selection: OverlaySelection = {
      objectType: candidate ? "CandidateOpportunity" : "ScannerEvaluation",
      objectId: item.candidate_opportunity_id ?? item.scanner_evaluation_id,
      opportunityId: item.candidate_opportunity_id ?? null,
      timestamp: item.observed_at,
      navigationTimestamp: item.observed_at,
      label,
      details: {
        classification: item.classification,
        score: String(item.score),
        priority_score: String(item.priority_score),
        candidate_threshold: String(item.candidate_threshold),
        score_margin: String(item.score_margin),
        triggers: item.triggers.join(", ") || "—",
        market_regime: item.market_regime ?? "—",
      },
    };
    if (!allowed.has(overlaySelectionKey(selection))) return [];
    return [{
      marker: marker(
        item.observed_at,
        candidate ? "belowBar" : "aboveBar",
        candidate ? "arrowUp" : "circle",
        candidate ? "#8b5cf6" : "#64748b",
        label,
      ),
      priority: candidate ? 100 : below ? 20 : 1,
      selection,
    }];
  });
}

function stageMarkers(
  overlays: FrontendAnalyticsOverlays,
  visibility: OverlayVisibility,
  cursorTime: number | null,
  allowed: Set<string>,
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
      navigationTimestamp: knowledgeAt,
    };
    if (name === "FINAL" || name.endsWith("_FINAL")) {
      if (!visibility.decisions || (result === "NO_TRADE" && !visibility.noTradeDecisions)) return [];
      const direction = result || "FINAL";
      const selection: OverlaySelection = {
        ...base,
        objectType: "ProfessorFinal",
        label: `FINAL ${direction}`,
        details: {
          result: direction,
          confidence: stage.confidence === null || stage.confidence === undefined ? "—" : String(stage.confidence),
          market_as_of: stage.market_as_of,
          operational_at: stage.operational_at ?? "—",
          known_at: knowledgeAt,
        },
      };
      if (!allowed.has(overlaySelectionKey(selection))) return [];
      return [{
        marker: marker(stage.market_as_of, direction === "SHORT" ? "aboveBar" : "belowBar", direction === "LONG" ? "arrowUp" : direction === "SHORT" ? "arrowDown" : "circle", "#a78bfa", direction),
        priority: 90,
        selection,
      }];
    }
    if (name.includes("PALERMO")) {
      if (!visibility.palermo) return [];
      const selection: OverlaySelection = {
        ...base,
        objectType: "PalermoReview",
        label: `Palermo ${result || "—"}`,
        details: {
          verdict: result || "—",
          severity: stage.severity === null || stage.severity === undefined ? "—" : String(stage.severity),
          reasons: stage.reason_codes.join(", ") || "—",
          market_as_of: stage.market_as_of,
          operational_at: stage.operational_at ?? "—",
          known_at: knowledgeAt,
        },
      };
      if (!allowed.has(overlaySelectionKey(selection))) return [];
      return [{
        marker: marker(stage.market_as_of, "aboveBar", "square", "#94a3b8", `PAL ${result || "—"}`),
        priority: 50,
        selection,
      }];
    }
    if (name === "RISK" || name.includes("RISK")) {
      if (!visibility.risk) return [];
      const selection: OverlaySelection = {
        ...base,
        objectType: "RiskDecision",
        label: `Risk ${result || "—"}`,
        details: {
          status: result || "—",
          reasons: stage.reason_codes.join(", ") || "—",
          market_as_of: stage.market_as_of,
          operational_at: stage.operational_at ?? "—",
          known_at: knowledgeAt,
        },
      };
      if (!allowed.has(overlaySelectionKey(selection))) return [];
      return [{
        marker: marker(stage.market_as_of, "aboveBar", "square", "#fb923c", `RISK ${result || "—"}`),
        priority: 80,
        selection,
      }];
    }
    return [];
  });
}

function eventMarkers(
  overlays: FrontendAnalyticsOverlays,
  visibility: OverlayVisibility,
  cursorTime: number | null,
  allowed: Set<string>,
): OverlayMarker[] {
  if (!visibility.technicalEvents) return [];
  return overlays.technical_events.flatMap((event) => {
    if (!isKnownAt(event.available_at, cursorTime)) return [];
    const selection: OverlaySelection = {
      objectType: "TechnicalEventObservation",
      objectId: event.event_id,
      opportunityId: null,
      timestamp: event.event_at,
      navigationTimestamp: event.available_at,
      label: event.event_type,
      details: {
        family: event.family,
        direction: event.direction,
        event_at: event.event_at,
        available_at: event.available_at,
      },
    };
    if (!allowed.has(overlaySelectionKey(selection))) return [];
    return [{
      marker: marker(event.event_at, "aboveBar", "circle", "#38bdf8", event.event_type),
      priority: 30,
      selection,
    }];
  });
}

function structureMarkers(
  structure: StructureOverlay[],
  visibility: OverlayVisibility,
  cursorTime: number | null,
  allowed: Set<string>,
): OverlayMarker[] {
  if (!visibility.structure) return [];
  return structure.flatMap((observation) => {
    if (!isKnownAt(observation.as_of, cursorTime)) return [];
    return observation.timeframes.flatMap((item) => {
      const breakout = item.breakout_state.toUpperCase();
      if (breakout === "INSIDE_RANGE" || breakout === "UNKNOWN") return [];
      const selection: OverlaySelection = {
        objectType: "MarketStructure",
        objectId: `${observation.structure_id}:${item.timeframe}`,
        opportunityId: null,
        timestamp: observation.as_of,
        navigationTimestamp: observation.as_of,
        label: `${item.timeframe} ${breakout}`,
        details: {
          timeframe: item.timeframe,
          swing_structure: item.swing_structure,
          prior_range_high: item.prior_range_high ?? "—",
          prior_range_low: item.prior_range_low ?? "—",
          range_location: item.range_location,
          breakout_state: item.breakout_state,
        },
      };
      if (!allowed.has(overlaySelectionKey(selection))) return [];
      return [{
        marker: marker(observation.as_of, breakout.includes("DOWN") ? "aboveBar" : "belowBar", "circle", "#cbd5e1", breakout),
        priority: 25,
        selection,
      }];
    });
  });
}

function pivotMarkers(
  overlays: FrontendAnalyticsOverlays,
  visibility: OverlayVisibility,
  cursorTime: number | null,
  allowed: Set<string>,
): OverlayMarker[] {
  if (!visibility.zigzag) return [];
  return overlays.zigzag_pivots.flatMap((pivot) => {
    if (!isKnownAt(pivot.confirmed_at, cursorTime)) return [];
    const high = pivot.kind.toUpperCase() === "HIGH";
    const selection: OverlaySelection = {
      objectType: "CausalZigZagPivot",
      objectId: pivot.pivot_id,
      opportunityId: null,
      timestamp: pivot.pivot_at,
      navigationTimestamp: pivot.confirmed_at,
      label: `ZigZag ${pivot.kind}`,
      details: {
        kind: pivot.kind,
        timeframe: pivot.timeframe,
        price: pivot.price,
        pivot_at: pivot.pivot_at,
        confirmed_at: pivot.confirmed_at,
        atr_at_pivot: pivot.atr_at_pivot,
        reversal_threshold: pivot.reversal_threshold,
        amplitude_pct: pivot.amplitude_pct ?? "—",
        amplitude_atr: pivot.amplitude_atr ?? "—",
      },
    };
    if (!allowed.has(overlaySelectionKey(selection))) return [];
    return [{
      marker: marker(
        pivot.pivot_at,
        high ? "aboveBar" : "belowBar",
        "circle",
        "#a78bfa",
        high ? "ZZ H" : "ZZ L",
      ),
      priority: 35,
      selection,
    }];
  });
}

function patternMarkers(
  patterns: PatternOverlay[],
  visibility: OverlayVisibility,
  cursorTime: number | null,
  allowed: Set<string>,
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
    const selection: OverlaySelection = {
      objectType: "PatternOccurrence",
      objectId: pattern.pattern_id,
      opportunityId: null,
      timestamp: geometryAt,
      navigationTimestamp: knownTransition.available_at,
      label: `${pattern.pattern_type} · ${status}`,
      details: {
        pattern_type: pattern.pattern_type,
        status,
        direction: pattern.direction,
        pivot_source: pattern.pivot_source,
        detected_at: pattern.detected_at,
        confirmed_at: pattern.confirmed_at ?? "—",
        failed_at: pattern.failed_at ?? "—",
        invalidated_at: pattern.invalidated_at ?? "—",
        known_at: knownTransition.available_at,
        source_pivots: pattern.points.map((point) => point.pivot_id).join(", "),
      },
    };
    if (!allowed.has(overlaySelectionKey(selection))) return [];
    return [{
      marker: marker(geometryAt, "aboveBar", "square", "#c4b5fd", `${pattern.pattern_type} ${status}`),
      priority: 40,
      selection,
    }];
  });
}

export function patternStatusAt(pattern: PatternOverlay, cursorTime: number | null): string | null {
  return patternStatusAtTimestamp(pattern, cursorTime);
}

function patternSegments(
  patterns: PatternOverlay[],
  visibility: OverlayVisibility,
  cursorTime: number | null,
  allowed: Set<string>,
): PatternSegmentModel[] {
  if (!visibility.patterns) return [];
  return patterns.flatMap((pattern) => {
    const status = patternStatusAt(pattern, cursorTime);
    if (status === null || (status === "FORMING" && !visibility.formingPatterns)) return [];
    const transition = pattern.transitions.filter(item => isKnownAt(item.available_at, cursorTime)).at(-1);
    if (!transition) return [];
    const selection: OverlaySelection = {
      objectType: "PatternOccurrence",
      objectId: pattern.pattern_id,
      opportunityId: null,
      timestamp: pattern.points.at(-1)?.pivot_at ?? pattern.points[0]?.pivot_at ?? pattern.detected_at,
      navigationTimestamp: transition.available_at,
      label: `${pattern.pattern_type} · ${status}`,
      details: {},
    };
    if (!allowed.has(overlaySelectionKey(selection))) return [];
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
  const allowed = new Set<string>(
    buildFilteredNavigationItems(overlays, filters, cursorTime).map(item => item.id),
  );
  const markers = [
    ...scannerMarkers(overlays, visibility, cursorTime, allowed),
    ...stageMarkers(overlays, visibility, cursorTime, allowed),
    ...eventMarkers(overlays, visibility, cursorTime, allowed),
    ...structureMarkers(overlays.structure, visibility, cursorTime, allowed),
    ...pivotMarkers(overlays, visibility, cursorTime, allowed),
    ...patternMarkers(overlays.patterns, visibility, cursorTime, allowed),
  ].sort((left, right) => Number(left.marker.time) - Number(right.marker.time) || right.priority - left.priority);
  const zigzag = visibility.zigzag
    ? overlays.zigzag_pivots
        .filter((pivot) => isKnownAt(pivot.confirmed_at, cursorTime))
        .filter((pivot) => {
          const selection: OverlaySelection = {
            objectType: "CausalZigZagPivot",
            objectId: pivot.pivot_id,
            opportunityId: null,
            timestamp: pivot.pivot_at,
            navigationTimestamp: pivot.confirmed_at,
            label: `ZigZag ${pivot.kind}`,
            details: {},
          };
          return allowed.has(overlaySelectionKey(selection));
        })
        .sort((left, right) => Number(isoToChartTime(left.pivot_at)) - Number(isoToChartTime(right.pivot_at)))
        .map((pivot) => ({ time: isoToChartTime(pivot.pivot_at), value: Number(pivot.price) }))
    : [];
  return {
    markers,
    zigzag,
    patternSegments: patternSegments(overlays.patterns, visibility, cursorTime, allowed),
  };
}

export function selectionAtTime(markers: OverlayMarker[], time: Time): OverlaySelection | null {
  return markers
    .filter((item) => Number(item.marker.time) === Number(time))
    .sort((left, right) => right.priority - left.priority)[0]?.selection ?? null;
}
