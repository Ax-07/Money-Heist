export type OverlayVisibility = {
  trading: boolean;
  scannerCandidates: boolean;
  scannerBelowThreshold: boolean;
  scannerNoTrigger: boolean;
  decisions: boolean;
  noTradeDecisions: boolean;
  palermo: boolean;
  risk: boolean;
  technicalEvents: boolean;
  structure: boolean;
  zigzag: boolean;
  patterns: boolean;
  formingPatterns: boolean;
};

export const DEFAULT_OVERLAY_VISIBILITY: OverlayVisibility = {
  trading: true,
  scannerCandidates: true,
  scannerBelowThreshold: false,
  scannerNoTrigger: false,
  decisions: true,
  noTradeDecisions: false,
  palermo: false,
  risk: true,
  technicalEvents: false,
  structure: false,
  zigzag: true,
  patterns: true,
  formingPatterns: false,
};

export type OverlaySelection = {
  objectType: string;
  objectId: string;
  opportunityId: string | null;
  /** Timestamp used for chart geometry / visual anchoring. */
  timestamp: string;
  /** Timestamp at which the object is causally available for replay navigation. */
  navigationTimestamp: string;
  label: string;
  details: Record<string, string>;
};

export type PatternCausalStatus = "FORMING" | "CONFIRMED" | "FAILED" | "INVALIDATED";

export type OverlayFilters = {
  scannerClassifications: string[];
  scannerTriggers: string[];
  scannerScoreMin: number | null;
  scannerScoreMax: number | null;
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

export const DEFAULT_OVERLAY_FILTERS: OverlayFilters = {
  scannerClassifications: [],
  scannerTriggers: [],
  scannerScoreMin: null,
  scannerScoreMax: null,
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

function strings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return Array.from(new Set(value.filter((item): item is string => typeof item === "string" && item.length > 0))).sort();
}

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * Merge old persisted filter shapes into the current canonical filter model.
 * 24C.2 persisted technicalEventFamily/technicalEventType as nullable strings.
 */
export function normalizeOverlayFilters(value: unknown): OverlayFilters {
  if (!value || typeof value !== "object") return { ...DEFAULT_OVERLAY_FILTERS };
  const record = value as Record<string, unknown>;
  const legacyFamily = typeof record.technicalEventFamily === "string" ? [record.technicalEventFamily] : [];
  const legacyType = typeof record.technicalEventType === "string" ? [record.technicalEventType] : [];
  const rawStatuses = strings(record.patternStatuses).filter(
    (status): status is PatternCausalStatus => ["FORMING", "CONFIRMED", "FAILED", "INVALIDATED"].includes(status),
  );
  return {
    scannerClassifications: strings(record.scannerClassifications),
    scannerTriggers: strings(record.scannerTriggers),
    scannerScoreMin: nullableNumber(record.scannerScoreMin),
    scannerScoreMax: nullableNumber(record.scannerScoreMax),
    professorFinal: strings(record.professorFinal),
    palermoVerdicts: strings(record.palermoVerdicts),
    riskStatuses: strings(record.riskStatuses),
    technicalEventFamilies: strings(record.technicalEventFamilies).length > 0
      ? strings(record.technicalEventFamilies)
      : legacyFamily,
    technicalEventTypes: strings(record.technicalEventTypes).length > 0
      ? strings(record.technicalEventTypes)
      : legacyType,
    technicalEventDirections: strings(record.technicalEventDirections),
    patternTypes: strings(record.patternTypes),
    patternStatuses: rawStatuses,
    patternDirections: strings(record.patternDirections),
    patternPivotSources: strings(record.patternPivotSources),
  };
}

export function overlayFiltersActive(filters: OverlayFilters): boolean {
  return filters.scannerClassifications.length > 0
    || filters.scannerTriggers.length > 0
    || filters.scannerScoreMin !== null
    || filters.scannerScoreMax !== null
    || filters.professorFinal.length > 0
    || filters.palermoVerdicts.length > 0
    || filters.riskStatuses.length > 0
    || filters.technicalEventFamilies.length > 0
    || filters.technicalEventTypes.length > 0
    || filters.technicalEventDirections.length > 0
    || filters.patternTypes.length > 0
    || filters.patternStatuses.length > 0
    || filters.patternDirections.length > 0
    || filters.patternPivotSources.length > 0;
}
