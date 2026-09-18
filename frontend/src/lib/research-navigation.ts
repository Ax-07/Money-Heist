import type { OverlaySelection } from "./analytics-overlay-state";
import type {
  FunnelDecisionQualityReport,
  ResearchEvidenceItem,
  ScannerFilteringReport,
} from "./api/research-schemas";
import type {
  ResearchCohortSelector,
  ResearchContrastSelection,
} from "./research-state";

export function evidenceToOverlaySelection(
  item: ResearchEvidenceItem,
): OverlaySelection {
  return {
    objectType: item.object_type,
    objectId: item.object_id,
    opportunityId: item.opportunity_id ?? null,
    timestamp: item.observed_at,
    navigationTimestamp: item.navigation_at,
    label: item.label,
    details: { ...item.details },
  };
}

export function scannerContrastSelection(
  contrast: ScannerFilteringReport["contrasts"][number],
): ResearchContrastSelection {
  const left: ResearchCohortSelector = {
    reportType: "SCANNER_FILTERING",
    dimension: "CLASSIFICATION",
    key: contrast.left_classification,
    stage: null,
  };
  const right: ResearchCohortSelector = {
    reportType: "SCANNER_FILTERING",
    dimension: "CLASSIFICATION",
    key: contrast.right_classification,
    stage: null,
  };
  return {
    reportType: "SCANNER_FILTERING",
    kind: contrast.kind,
    left,
    right,
  };
}

export function funnelContrastSelection(
  contrast: FunnelDecisionQualityReport["contrasts"][number],
): ResearchContrastSelection {
  const left: ResearchCohortSelector = {
    reportType: "FUNNEL_DECISION_QUALITY",
    dimension: "STAGE_RESULT",
    key: contrast.left_key,
    stage: contrast.stage,
  };
  const right: ResearchCohortSelector = {
    reportType: "FUNNEL_DECISION_QUALITY",
    dimension: "STAGE_RESULT",
    key: contrast.right_key,
    stage: contrast.stage,
  };
  return {
    reportType: "FUNNEL_DECISION_QUALITY",
    kind: contrast.kind,
    left,
    right,
  };
}
