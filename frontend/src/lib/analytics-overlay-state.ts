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
  timestamp: string;
  label: string;
  details: Record<string, string>;
};

export type OverlayFilters = {
  technicalEventFamily: string | null;
  technicalEventType: string | null;
};

export const DEFAULT_OVERLAY_FILTERS: OverlayFilters = {
  technicalEventFamily: null,
  technicalEventType: null,
};
