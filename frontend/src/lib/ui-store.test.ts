import { beforeEach, describe, expect, it } from "vitest";

import { useUiStore } from "./ui-store";

const selection = {
  objectType: "ProfessorFinal",
  objectId: "stage-1",
  opportunityId: "opportunity-1",
  timestamp: "2026-01-01T12:00:00Z",
  label: "FINAL LONG",
  details: { operational_at: "2026-01-01T12:00:01Z" },
};

describe("Decision Intelligence selection state", () => {
  beforeEach(() => {
    useUiStore.setState({
      inspectorOpen: false,
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
});
