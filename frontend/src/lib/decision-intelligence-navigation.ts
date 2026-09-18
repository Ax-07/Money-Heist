import type {
  FrontendAnalyticsOverlays,
  PatternOverlay,
  ScannerOverlay,
} from "@/lib/api/analytics-overlay-schemas";
import {
  overlayFiltersActive,
  type OverlayFilters,
  type OverlaySelection,
  type PatternCausalStatus,
} from "@/lib/analytics-overlay-state";

export type FilteredNavigationItem = {
  id: string;
  type: string;
  timestamp: string;
  label: string;
  opportunityId: string | null;
  selection: OverlaySelection;
  facets: NavigationFacets;
};

type NavigationFacets = {
  scannerClassification: string | null;
  scannerTriggers: string[];
  scannerScore: number | null;
  professorFinal: string | null;
  palermoVerdict: string | null;
  riskStatus: string | null;
  technicalEventFamilies: string[];
  technicalEventTypes: string[];
  technicalEventDirections: string[];
  patternTypes: string[];
  patternStatuses: PatternCausalStatus[];
  patternDirections: string[];
  patternPivotSources: string[];
};

type FrontendFunnelStage = FrontendAnalyticsOverlays["funnel_stages"][number];

type OpportunityContext = {
  scanner: ScannerOverlay | null;
  professorFinal: string | null;
  palermoVerdict: string | null;
  riskStatus: string | null;
};

export type DecisionIntelligenceFilterFacets = {
  scannerClassifications: string[];
  scannerTriggers: string[];
  professorFinal: string[];
  palermoVerdicts: string[];
  riskStatuses: string[];
  technicalEventFamilies: string[];
  technicalEventTypes: string[];
  technicalEventDirections: string[];
  patternTypes: string[];
  patternStatuses: PatternCausalStatus[];
  patternDirections: string[];
  patternPivotSources: string[];
};

const TYPE_ORDER: Record<string, number> = {
  ScannerEvaluation: 10,
  CandidateOpportunity: 11,
  ProfessorPlan: 20,
  SpecialistAnalysis: 21,
  PalermoReview: 30,
  ProfessorFinal: 40,
  RiskDecision: 50,
  DecisionFunnelStage: 55,
  TechnicalEventObservation: 60,
  MarketStructure: 70,
  CausalZigZagPivot: 80,
  PatternOccurrence: 90,
};

function epoch(value: string): number {
  return new Date(value).getTime();
}

function unique(values: Iterable<string>): string[] {
  return Array.from(new Set(values)).sort();
}

function intersects(left: string[], right: string[]): boolean {
  if (right.length === 0) return true;
  const set = new Set(left);
  return right.some(value => set.has(value));
}

function latestPatternTransition(pattern: PatternOverlay, atMs: number) {
  return pattern.transitions
    .filter(transition => epoch(transition.available_at) <= atMs)
    .sort((left, right) => epoch(left.available_at) - epoch(right.available_at))
    .at(-1) ?? null;
}

export function patternStatusAtTimestamp(
  pattern: PatternOverlay,
  timestamp: string | number | null,
): PatternCausalStatus | null {
  if (timestamp === null) return null;
  const atMs = typeof timestamp === "number" ? timestamp * 1000 : epoch(timestamp);
  const transition = latestPatternTransition(pattern, atMs);
  return transition?.status ?? null;
}

function opportunityContextAt(
  overlays: FrontendAnalyticsOverlays,
  opportunityId: string | null,
  atMs: number,
): OpportunityContext | null {
  if (!opportunityId) return null;
  const scanner = overlays.scanner.find(
    item => item.candidate_opportunity_id === opportunityId && epoch(item.observed_at) <= atMs,
  ) ?? null;
  const context: OpportunityContext = {
    scanner,
    professorFinal: null,
    palermoVerdict: null,
    riskStatus: null,
  };
  const knownStages = overlays.funnel_stages
    .filter(stage => stage.opportunity_id === opportunityId && stage.reached)
    .filter(stage => epoch(stage.operational_at ?? stage.market_as_of) <= atMs)
    .sort((left, right) => {
      const byTime = epoch(left.operational_at ?? left.market_as_of) - epoch(right.operational_at ?? right.market_as_of);
      if (byTime !== 0) return byTime;
      const byOrder = left.stage_order - right.stage_order;
      if (byOrder !== 0) return byOrder;
      return left.record_id.localeCompare(right.record_id);
    });
  for (const stage of knownStages) {
    const name = stage.stage.toUpperCase();
    const result = (stage.stage_result ?? stage.stage_status ?? "").toUpperCase() || null;
    if (!result) continue;
    if (name === "FINAL" || name.endsWith("_FINAL")) context.professorFinal = result;
    if (name.includes("PALERMO")) context.palermoVerdict = result;
    if (name === "RISK" || name.includes("RISK")) context.riskStatus = result;
  }
  return context;
}

function eventsAt(overlays: FrontendAnalyticsOverlays, atMs: number) {
  return overlays.technical_events.filter(event => epoch(event.available_at) === atMs);
}

function patternFacetsAt(overlays: FrontendAnalyticsOverlays, atMs: number) {
  const visible = overlays.patterns.flatMap(pattern => {
    const transition = latestPatternTransition(pattern, atMs);
    if (!transition) return [];
    return [{ pattern, transition }];
  });
  return {
    types: unique(visible.map(item => item.pattern.pattern_type)),
    statuses: unique(visible.map(item => item.transition.status)) as PatternCausalStatus[],
    directions: unique(visible.map(item => item.pattern.direction)),
    pivotSources: unique(visible.map(item => item.pattern.pivot_source)),
  };
}

function facetsFor(
  overlays: FrontendAnalyticsOverlays,
  timestamp: string,
  opportunityId: string | null,
  scanner: ScannerOverlay | null,
  analyticsTimestamp = timestamp,
): NavigationFacets {
  const atMs = epoch(timestamp);
  const analyticsAtMs = epoch(analyticsTimestamp);
  const context = opportunityContextAt(overlays, opportunityId, atMs);
  const eventSet = eventsAt(overlays, analyticsAtMs);
  const patternSet = patternFacetsAt(overlays, analyticsAtMs);
  return {
    scannerClassification: scanner?.classification ?? null,
    scannerTriggers: scanner?.triggers ?? [],
    scannerScore: scanner?.score ?? scanner?.priority_score ?? null,
    professorFinal: context?.professorFinal ?? null,
    palermoVerdict: context?.palermoVerdict ?? null,
    riskStatus: context?.riskStatus ?? null,
    technicalEventFamilies: unique(eventSet.map(event => event.family)),
    technicalEventTypes: unique(eventSet.map(event => event.event_type)),
    technicalEventDirections: unique(eventSet.map(event => event.direction)),
    patternTypes: patternSet.types,
    patternStatuses: patternSet.statuses,
    patternDirections: patternSet.directions,
    patternPivotSources: patternSet.pivotSources,
  };
}

function selectionKey(selection: OverlaySelection): string {
  return `${selection.objectType}|${selection.objectId}|${selection.navigationTimestamp}`;
}

export function overlaySelectionKey(selection: OverlaySelection): string {
  return selectionKey(selection);
}

function stageObjectType(stage: FrontendFunnelStage): string {
  const name = stage.stage.toUpperCase();
  if (name === "FINAL" || name.endsWith("_FINAL")) return "ProfessorFinal";
  if (name.includes("PALERMO")) return "PalermoReview";
  if (name === "RISK" || name.includes("RISK")) return "RiskDecision";
  if (name.includes("PLAN")) return "ProfessorPlan";
  if (name.includes("SPECIALIST") || name.includes("ANALYSIS")) return "SpecialistAnalysis";
  return "DecisionFunnelStage";
}

function stageItem(
  overlays: FrontendAnalyticsOverlays,
  stage: FrontendFunnelStage,
): FilteredNavigationItem | null {
  if (!stage.reached) return null;
  const navigationTimestamp = stage.operational_at ?? stage.market_as_of;
  const result = (stage.stage_result ?? stage.stage_status ?? "REACHED").toUpperCase();
  const type = stageObjectType(stage);
  const label = type === "ProfessorFinal"
    ? `FINAL · ${result}`
    : type === "PalermoReview"
      ? `Palermo · ${result}`
      : type === "RiskDecision"
        ? `Risk · ${result}`
        : `${stage.stage} · ${result}`;
  const contextScanner = opportunityContextAt(overlays, stage.opportunity_id, epoch(navigationTimestamp))?.scanner ?? null;
  const selection: OverlaySelection = {
    objectType: type,
    objectId: stage.record_id,
    opportunityId: stage.opportunity_id,
    timestamp: stage.market_as_of,
    navigationTimestamp,
    label,
    details: {
      result,
      market_as_of: stage.market_as_of,
      operational_at: stage.operational_at ?? "—",
      reasons: stage.reason_codes.join(", ") || "—",
      known_at: navigationTimestamp,
    },
  };
  const facets = facetsFor(
    overlays,
    navigationTimestamp,
    stage.opportunity_id,
    contextScanner,
    stage.analytics.analytics_as_of ?? navigationTimestamp,
  );
  // Keep the stage's own decision dimension authoritative even when multiple
  // funnel records share an operational timestamp.
  if (type === "ProfessorFinal") facets.professorFinal = result;
  if (type === "PalermoReview") facets.palermoVerdict = result;
  if (type === "RiskDecision") facets.riskStatus = result;
  return {
    id: selectionKey(selection),
    type,
    timestamp: navigationTimestamp,
    label,
    opportunityId: stage.opportunity_id,
    selection,
    facets,
  };
}

function scannerItem(
  overlays: FrontendAnalyticsOverlays,
  scanner: ScannerOverlay,
): FilteredNavigationItem {
  const candidate = scanner.classification.toUpperCase() === "CANDIDATE_OPPORTUNITY"
    || scanner.candidate_opportunity_id !== null;
  const type = candidate ? "CandidateOpportunity" : "ScannerEvaluation";
  const label = candidate
    ? `Candidate · score ${scanner.priority_score}`
    : `${scanner.classification} · score ${scanner.priority_score}`;
  const selection: OverlaySelection = {
    objectType: type,
    objectId: scanner.candidate_opportunity_id ?? scanner.scanner_evaluation_id,
    opportunityId: scanner.candidate_opportunity_id ?? null,
    timestamp: scanner.observed_at,
    navigationTimestamp: scanner.observed_at,
    label,
    details: {
      classification: scanner.classification,
      score: String(scanner.score),
      priority_score: String(scanner.priority_score),
      candidate_threshold: String(scanner.candidate_threshold),
      score_margin: String(scanner.score_margin),
      triggers: scanner.triggers.join(", ") || "—",
      market_regime: scanner.market_regime ?? "—",
    },
  };
  return {
    id: selectionKey(selection),
    type,
    timestamp: scanner.observed_at,
    label,
    opportunityId: scanner.candidate_opportunity_id ?? null,
    selection,
    facets: facetsFor(
      overlays,
      scanner.observed_at,
      scanner.candidate_opportunity_id ?? null,
      scanner,
      scanner.analytics.analytics_as_of ?? scanner.observed_at,
    ),
  };
}

export function buildNavigationItems(
  overlays: FrontendAnalyticsOverlays | null | undefined,
  cursorTime: number | null,
): FilteredNavigationItem[] {
  if (!overlays?.analytics_available) return [];
  const causalCeiling = cursorTime === null ? Number.POSITIVE_INFINITY : cursorTime * 1000;
  const items: FilteredNavigationItem[] = [];

  for (const scanner of overlays.scanner) {
    if (epoch(scanner.observed_at) <= causalCeiling) items.push(scannerItem(overlays, scanner));
  }

  for (const stage of overlays.funnel_stages) {
    const item = stageItem(overlays, stage);
    if (item && epoch(item.timestamp) <= causalCeiling) items.push(item);
  }

  for (const event of overlays.technical_events) {
    if (epoch(event.available_at) > causalCeiling) continue;
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
    const facets = facetsFor(overlays, event.available_at, null, null);
    // The event dimensions describe this event, not another event that happened
    // to become available at the same timestamp. Other dimensions can still
    // describe the causal Analytics context for cross-filtering.
    facets.technicalEventFamilies = [event.family];
    facets.technicalEventTypes = [event.event_type];
    facets.technicalEventDirections = [event.direction];
    items.push({
      id: selectionKey(selection),
      type: selection.objectType,
      timestamp: event.available_at,
      label: event.event_type,
      opportunityId: null,
      selection,
      facets,
    });
  }

  for (const observation of overlays.structure) {
    if (epoch(observation.as_of) > causalCeiling) continue;
    for (const timeframe of observation.timeframes) {
      const breakout = timeframe.breakout_state.toUpperCase();
      if (breakout === "INSIDE_RANGE" || breakout === "UNKNOWN") continue;
      const selection: OverlaySelection = {
        objectType: "MarketStructure",
        objectId: `${observation.structure_id}:${timeframe.timeframe}`,
        opportunityId: null,
        timestamp: observation.as_of,
        navigationTimestamp: observation.as_of,
        label: `${timeframe.timeframe} · ${breakout}`,
        details: {
          timeframe: timeframe.timeframe,
          breakout_state: timeframe.breakout_state,
          swing_structure: timeframe.swing_structure,
          range_location: timeframe.range_location,
        },
      };
      items.push({
        id: selectionKey(selection),
        type: selection.objectType,
        timestamp: observation.as_of,
        label: selection.label,
        opportunityId: null,
        selection,
        facets: facetsFor(overlays, observation.as_of, null, null),
      });
    }
  }

  for (const pivot of overlays.zigzag_pivots) {
    if (epoch(pivot.confirmed_at) > causalCeiling) continue;
    const selection: OverlaySelection = {
      objectType: "CausalZigZagPivot",
      objectId: pivot.pivot_id,
      opportunityId: null,
      timestamp: pivot.pivot_at,
      navigationTimestamp: pivot.confirmed_at,
      label: `ZigZag · ${pivot.kind}`,
      details: {
        kind: pivot.kind,
        timeframe: pivot.timeframe,
        price: pivot.price,
        pivot_at: pivot.pivot_at,
        confirmed_at: pivot.confirmed_at,
      },
    };
    items.push({
      id: selectionKey(selection),
      type: selection.objectType,
      timestamp: pivot.confirmed_at,
      label: selection.label,
      opportunityId: null,
      selection,
      facets: facetsFor(overlays, pivot.confirmed_at, null, null),
    });
  }

  for (const pattern of overlays.patterns) {
    const transition = latestPatternTransition(pattern, causalCeiling);
    if (!transition) continue;
    const firstPoint = pattern.points[0];
    const lastPoint = pattern.points.at(-1);
    const geometryAt = lastPoint?.pivot_at ?? firstPoint?.pivot_at ?? pattern.detected_at;
    const selection: OverlaySelection = {
      objectType: "PatternOccurrence",
      objectId: pattern.pattern_id,
      opportunityId: null,
      timestamp: geometryAt,
      navigationTimestamp: transition.available_at,
      label: `${pattern.pattern_type} · ${transition.status}`,
      details: {
        pattern_type: pattern.pattern_type,
        status: transition.status,
        direction: pattern.direction,
        pivot_source: pattern.pivot_source,
        detected_at: pattern.detected_at,
        confirmed_at: pattern.confirmed_at ?? "—",
        failed_at: pattern.failed_at ?? "—",
        invalidated_at: pattern.invalidated_at ?? "—",
        known_at: transition.available_at,
      },
    };
    const facets = facetsFor(overlays, transition.available_at, null, null);
    // Pattern filters apply to the occurrence represented by this item. Do not
    // let a concurrent pattern make this occurrence match the wrong type/status.
    facets.patternTypes = [pattern.pattern_type];
    facets.patternStatuses = [transition.status];
    facets.patternDirections = [pattern.direction];
    facets.patternPivotSources = [pattern.pivot_source];
    items.push({
      id: selectionKey(selection),
      type: selection.objectType,
      timestamp: transition.available_at,
      label: selection.label,
      opportunityId: null,
      selection,
      facets,
    });
  }

  return items.sort((left, right) => {
    const byTime = epoch(left.timestamp) - epoch(right.timestamp);
    if (byTime !== 0) return byTime;
    const byType = (TYPE_ORDER[left.type] ?? 999) - (TYPE_ORDER[right.type] ?? 999);
    if (byType !== 0) return byType;
    return left.id.localeCompare(right.id);
  });
}

function scannerFiltersActive(filters: OverlayFilters): boolean {
  return filters.scannerClassifications.length > 0
    || filters.scannerTriggers.length > 0
    || filters.scannerScoreMin !== null
    || filters.scannerScoreMax !== null;
}

function eventFiltersActive(filters: OverlayFilters): boolean {
  return filters.technicalEventFamilies.length > 0
    || filters.technicalEventTypes.length > 0
    || filters.technicalEventDirections.length > 0;
}

function patternFiltersActive(filters: OverlayFilters): boolean {
  return filters.patternTypes.length > 0
    || filters.patternStatuses.length > 0
    || filters.patternDirections.length > 0
    || filters.patternPivotSources.length > 0;
}

function anchorMatches(item: FilteredNavigationItem, filters: OverlayFilters): boolean {
  // Anchor on the latest decision dimension first. This prevents a future Risk/FINAL
  // outcome from making an earlier Candidate appear to match before that outcome existed.
  if (filters.riskStatuses.length > 0) return item.type === "RiskDecision";
  if (filters.professorFinal.length > 0) return item.type === "ProfessorFinal";
  if (filters.palermoVerdicts.length > 0) return item.type === "PalermoReview";
  if (scannerFiltersActive(filters)) {
    return item.type === "CandidateOpportunity" || item.type === "ScannerEvaluation";
  }
  if (eventFiltersActive(filters)) return item.type === "TechnicalEventObservation";
  if (patternFiltersActive(filters)) return item.type === "PatternOccurrence";
  return true;
}

export function navigationItemMatchesFilters(
  item: FilteredNavigationItem,
  filters: OverlayFilters,
): boolean {
  if (!overlayFiltersActive(filters)) return true;
  if (!anchorMatches(item, filters)) return false;
  const facets = item.facets;
  if (filters.scannerClassifications.length > 0
      && (!facets.scannerClassification || !filters.scannerClassifications.includes(facets.scannerClassification))) return false;
  if (!intersects(facets.scannerTriggers, filters.scannerTriggers)) return false;
  if (filters.scannerScoreMin !== null
      && (facets.scannerScore === null || facets.scannerScore < filters.scannerScoreMin)) return false;
  if (filters.scannerScoreMax !== null
      && (facets.scannerScore === null || facets.scannerScore > filters.scannerScoreMax)) return false;
  if (filters.professorFinal.length > 0
      && (!facets.professorFinal || !filters.professorFinal.includes(facets.professorFinal))) return false;
  if (filters.palermoVerdicts.length > 0
      && (!facets.palermoVerdict || !filters.palermoVerdicts.includes(facets.palermoVerdict))) return false;
  if (filters.riskStatuses.length > 0
      && (!facets.riskStatus || !filters.riskStatuses.includes(facets.riskStatus))) return false;
  if (!intersects(facets.technicalEventFamilies, filters.technicalEventFamilies)) return false;
  if (!intersects(facets.technicalEventTypes, filters.technicalEventTypes)) return false;
  if (!intersects(facets.technicalEventDirections, filters.technicalEventDirections)) return false;
  if (!intersects(facets.patternTypes, filters.patternTypes)) return false;
  if (!intersects(facets.patternStatuses, filters.patternStatuses)) return false;
  if (!intersects(facets.patternDirections, filters.patternDirections)) return false;
  if (!intersects(facets.patternPivotSources, filters.patternPivotSources)) return false;
  return true;
}

export function applyDecisionIntelligenceFilters(
  items: FilteredNavigationItem[],
  filters: OverlayFilters,
): FilteredNavigationItem[] {
  return items.filter(item => navigationItemMatchesFilters(item, filters));
}

export function buildFilteredNavigationItems(
  overlays: FrontendAnalyticsOverlays | null | undefined,
  filters: OverlayFilters,
  cursorTime: number | null,
): FilteredNavigationItem[] {
  return applyDecisionIntelligenceFilters(buildNavigationItems(overlays, cursorTime), filters);
}

export function searchNavigationItems(
  items: FilteredNavigationItem[],
  query: string,
): FilteredNavigationItem[] {
  const needle = query.trim().toLocaleLowerCase("fr-FR");
  if (!needle) return items;
  return items.filter(item => {
    const details = Object.entries(item.selection.details)
      .map(([key, value]) => `${key} ${value}`)
      .join(" ");
    return [item.id, item.type, item.label, item.opportunityId ?? "", details]
      .join(" ")
      .toLocaleLowerCase("fr-FR")
      .includes(needle);
  });
}

export function navigationPosition(
  items: FilteredNavigationItem[],
  selection: OverlaySelection | null,
): number {
  if (!selection) return -1;
  const key = selectionKey(selection);
  return items.findIndex(item => item.id === key);
}

export function navigationNeighbors(
  items: FilteredNavigationItem[],
  selection: OverlaySelection | null,
  anchorTime: number | null,
): { previous: FilteredNavigationItem | null; next: FilteredNavigationItem | null; position: number } {
  if (items.length === 0) return { previous: null, next: null, position: -1 };
  const position = navigationPosition(items, selection);
  if (position >= 0) {
    return {
      previous: position > 0 ? items[position - 1]! : null,
      next: position < items.length - 1 ? items[position + 1]! : null,
      position,
    };
  }
  const anchorMs = anchorTime === null ? Number.POSITIVE_INFINITY : anchorTime * 1000;
  const before = items.filter(item => epoch(item.timestamp) <= anchorMs);
  const after = items.filter(item => epoch(item.timestamp) > anchorMs);
  return {
    previous: before.at(-1) ?? null,
    next: after[0] ?? null,
    position: -1,
  };
}

export function collectDecisionIntelligenceFilterFacets(
  overlays: FrontendAnalyticsOverlays | null | undefined,
): DecisionIntelligenceFilterFacets {
  if (!overlays?.analytics_available) {
    return {
      scannerClassifications: [],
      scannerTriggers: [],
      professorFinal: [],
      palermoVerdicts: [],
      riskStatuses: [],
      technicalEventFamilies: [],
      technicalEventTypes: [],
      technicalEventDirections: [],
      patternTypes: [],
      patternStatuses: [],
      patternDirections: [],
      patternPivotSources: [],
    };
  }
  const final: string[] = [];
  const palermo: string[] = [];
  const risk: string[] = [];
  for (const stage of overlays.funnel_stages) {
    if (!stage.reached) continue;
    const name = stage.stage.toUpperCase();
    const result = (stage.stage_result ?? stage.stage_status ?? "").toUpperCase();
    if (!result) continue;
    if (name === "FINAL" || name.endsWith("_FINAL")) final.push(result);
    if (name.includes("PALERMO")) palermo.push(result);
    if (name === "RISK" || name.includes("RISK")) risk.push(result);
  }
  return {
    scannerClassifications: unique(overlays.scanner.map(item => item.classification)),
    scannerTriggers: unique(overlays.scanner.flatMap(item => item.triggers)),
    professorFinal: unique(final),
    palermoVerdicts: unique(palermo),
    riskStatuses: unique(risk),
    technicalEventFamilies: unique(overlays.technical_events.map(item => item.family)),
    technicalEventTypes: unique(overlays.technical_events.map(item => item.event_type)),
    technicalEventDirections: unique(overlays.technical_events.map(item => item.direction)),
    patternTypes: unique(overlays.patterns.map(item => item.pattern_type)),
    patternStatuses: unique(overlays.patterns.flatMap(item => item.transitions.map(transition => transition.status))) as PatternCausalStatus[],
    patternDirections: unique(overlays.patterns.map(item => item.direction)),
    patternPivotSources: unique(overlays.patterns.map(item => item.pivot_source)),
  };
}

export function activeFilterLabels(filters: OverlayFilters): string[] {
  const labels: string[] = [];
  if (filters.scannerClassifications.length) labels.push(`Scanner: ${filters.scannerClassifications.join(" | ")}`);
  if (filters.scannerTriggers.length) labels.push(`Trigger: ${filters.scannerTriggers.join(" | ")}`);
  if (filters.scannerScoreMin !== null || filters.scannerScoreMax !== null) {
    labels.push(`Score: ${filters.scannerScoreMin ?? "−∞"}…${filters.scannerScoreMax ?? "+∞"}`);
  }
  if (filters.professorFinal.length) labels.push(`FINAL: ${filters.professorFinal.join(" | ")}`);
  if (filters.palermoVerdicts.length) labels.push(`Palermo: ${filters.palermoVerdicts.join(" | ")}`);
  if (filters.riskStatuses.length) labels.push(`Risk: ${filters.riskStatuses.join(" | ")}`);
  if (filters.technicalEventFamilies.length) labels.push(`Event family: ${filters.technicalEventFamilies.join(" | ")}`);
  if (filters.technicalEventTypes.length) labels.push(`Event type: ${filters.technicalEventTypes.join(" | ")}`);
  if (filters.technicalEventDirections.length) labels.push(`Event direction: ${filters.technicalEventDirections.join(" | ")}`);
  if (filters.patternTypes.length) labels.push(`Pattern: ${filters.patternTypes.join(" | ")}`);
  if (filters.patternStatuses.length) labels.push(`Pattern status: ${filters.patternStatuses.join(" | ")}`);
  if (filters.patternDirections.length) labels.push(`Pattern direction: ${filters.patternDirections.join(" | ")}`);
  if (filters.patternPivotSources.length) labels.push(`Pivot source: ${filters.patternPivotSources.join(" | ")}`);
  return labels;
}
