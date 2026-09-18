import { beforeEach, describe, expect, it } from "vitest";

import { DEFAULT_OVERLAY_FILTERS } from "./analytics-overlay-state";
import { mergePersistedUiPreferences, useUiStore } from "./ui-store";

const selection = {
  objectType: "ProfessorFinal",
  objectId: "stage-1",
  opportunityId: "opportunity-1",
  timestamp: "2026-01-01T12:00:00Z",
  navigationTimestamp: "2026-01-01T12:00:01Z",
  label: "FINAL LONG",
  details: { operational_at: "2026-01-01T12:00:01Z" },
};

describe("Decision Intelligence selection state", () => {
  beforeEach(() => {
    useUiStore.setState({
      inspectorOpen: false,
      selectedResearchCohort: null,
      selectedResearchContrast: null,
      overlayFilters: { ...DEFAULT_OVERLAY_FILTERS },
      selectedOpportunityId: null,
      selectedAnalyticsObject: null,
    });
  });

  it("opens the inspector and synchronizes opportunity selection from a chart object", () => {
    useUiStore.getState().setSelectedAnalyticsObject(selection);

    const state = useUiStore.getState();
    expect(state.inspectorOpen).toBe(true);
    expect(state.selectedOpportunityId).toBe("opportunity-1");
    expect(state.selectedAnalyticsObject?.objectId).toBe("stage-1");
  });

  it("clears stale opportunity and analytics-object selection together", () => {
    useUiStore.getState().setSelectedAnalyticsObject(selection);
    useUiStore.getState().clearAnalyticsSelection();

    const state = useUiStore.getState();
    expect(state.selectedOpportunityId).toBeNull();
    expect(state.selectedAnalyticsObject).toBeNull();
  });

  it("supports direct opportunity selection without inventing an analytics object", () => {
    useUiStore.getState().setSelectedOpportunityId("opportunity-2");

    const state = useUiStore.getState();
    expect(state.inspectorOpen).toBe(true);
    expect(state.selectedOpportunityId).toBe("opportunity-2");
    expect(state.selectedAnalyticsObject).toBeNull();
  });

  it("persists filter preferences but not run-specific selections", () => {
    const current = useUiStore.getState();
    const merged = mergePersistedUiPreferences({
      sidebarCollapsed: true,
      overlayVisibility: { risk: false },
      overlayFilters: { riskStatuses: ["REJECTED"] },
      selectedOpportunityId: "stale-opportunity",
      selectedAnalyticsObject: selection,
      inspectorOpen: false,
      selectedResearchCohort: {
        reportType: "SCANNER_FILTERING",
        dimension: "CLASSIFICATION",
        key: "CANDIDATE_OPPORTUNITY",
        stage: null,
      },
    }, current);

    expect(merged.sidebarCollapsed).toBe(true);
    expect(merged.overlayVisibility.risk).toBe(false);
    expect(merged.overlayFilters.riskStatuses).toEqual(["REJECTED"]);
    expect(merged.selectedOpportunityId).toBe(current.selectedOpportunityId);
    expect(merged.selectedAnalyticsObject).toBe(current.selectedAnalyticsObject);
    expect(merged.inspectorOpen).toBe(current.inspectorOpen);
    expect(merged.selectedResearchCohort).toBe(current.selectedResearchCohort);
    expect(merged.selectedResearchContrast).toBe(current.selectedResearchContrast);
  });

  it("migrates the legacy 24C.2 technical event filter shape and fills new defaults", () => {
    const current = useUiStore.getState();
    const merged = mergePersistedUiPreferences({
      overlayFilters: {
        technicalEventFamily: "MOMENTUM",
        technicalEventType: "RSI_CROSS_50_UP",
      },
    }, current);

    expect(merged.overlayFilters.technicalEventFamilies).toEqual(["MOMENTUM"]);
    expect(merged.overlayFilters.technicalEventTypes).toEqual(["RSI_CROSS_50_UP"]);
    expect(merged.overlayFilters.scannerClassifications).toEqual([]);
    expect(merged.overlayFilters.patternStatuses).toEqual([]);
  });

  it("keeps research selection UI-only and separate from canonical replay selection", () => {
    useUiStore.getState().setSelectedAnalyticsObject(selection);
    useUiStore.getState().setSelectedResearchCohort({
      reportType: "FUNNEL_DECISION_QUALITY",
      stage: "PROFESSOR_FINAL",
      dimension: "STAGE_RESULT",
      key: "LONG",
    });

    const state = useUiStore.getState();
    expect(state.selectedAnalyticsObject?.objectId).toBe("stage-1");
    expect(state.selectedOpportunityId).toBe("opportunity-1");
    expect(state.selectedResearchCohort?.key).toBe("LONG");

    useUiStore.getState().clearResearchSelection();
    expect(useUiStore.getState().selectedAnalyticsObject?.objectId).toBe("stage-1");
    expect(useUiStore.getState().selectedResearchCohort).toBeNull();
  });
});
