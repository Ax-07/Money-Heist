import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  DEFAULT_OVERLAY_FILTERS,
  DEFAULT_OVERLAY_VISIBILITY,
  normalizeOverlayFilters,
  type OverlayFilters,
  type OverlaySelection,
  type OverlayVisibility,
} from "@/lib/analytics-overlay-state";
import type {
  ResearchCohortSelector,
  ResearchContrastSelection,
} from "@/lib/research-state";

export const UI_STORE_NAME = "money-heist-ui-v2";
export const UI_STORE_VERSION = 2;

type UiState = {
  sidebarCollapsed: boolean;
  inspectorOpen: boolean;
  settingsOpen: boolean;
  mobileSidebarOpen: boolean;
  overlayVisibility: OverlayVisibility;
  overlayFilters: OverlayFilters;
  selectedOpportunityId: string | null;
  selectedAnalyticsObject: OverlaySelection | null;
  selectedResearchCohort: ResearchCohortSelector | null;
  selectedResearchContrast: ResearchContrastSelection | null;
  setSidebarCollapsed(value: boolean): void;
  setInspectorOpen(value: boolean): void;
  setSettingsOpen(value: boolean): void;
  setMobileSidebarOpen(value: boolean): void;
  setOverlayVisibility(value: Partial<OverlayVisibility>): void;
  setOverlayFilters(value: Partial<OverlayFilters>): void;
  clearOverlayFilters(): void;
  setSelectedOpportunityId(value: string | null): void;
  setSelectedAnalyticsObject(value: OverlaySelection | null): void;
  clearAnalyticsSelection(): void;
  setSelectedResearchCohort(value: ResearchCohortSelector | null): void;
  setSelectedResearchContrast(value: ResearchContrastSelection | null): void;
  clearResearchSelection(): void;
};

type PersistedUiState = Pick<UiState, "sidebarCollapsed" | "overlayVisibility" | "overlayFilters">;

export function mergePersistedUiPreferences(
  persisted: unknown,
  current: UiState,
): UiState {
  const record = persisted && typeof persisted === "object" ? persisted as Record<string, unknown> : {};
  const persistedVisibility = record.overlayVisibility && typeof record.overlayVisibility === "object"
    ? record.overlayVisibility as Partial<OverlayVisibility>
    : {};
  return {
    ...current,
    sidebarCollapsed: typeof record.sidebarCollapsed === "boolean"
      ? record.sidebarCollapsed
      : current.sidebarCollapsed,
    overlayVisibility: {
      ...DEFAULT_OVERLAY_VISIBILITY,
      ...persistedVisibility,
    },
    overlayFilters: normalizeOverlayFilters(record.overlayFilters),
    // Run-specific selections intentionally always come from the fresh current state.
    selectedOpportunityId: current.selectedOpportunityId,
    selectedAnalyticsObject: current.selectedAnalyticsObject,
    inspectorOpen: current.inspectorOpen,
    selectedResearchCohort: current.selectedResearchCohort,
    selectedResearchContrast: current.selectedResearchContrast,
  };
}

export const useUiStore = create<UiState>()(persist((set) => ({
  sidebarCollapsed: false,
  inspectorOpen: true,
  settingsOpen: false,
  mobileSidebarOpen: false,
  overlayVisibility: DEFAULT_OVERLAY_VISIBILITY,
  overlayFilters: DEFAULT_OVERLAY_FILTERS,
  selectedOpportunityId: null,
  selectedAnalyticsObject: null,
  selectedResearchCohort: null,
  selectedResearchContrast: null,
  setSidebarCollapsed: value => set({ sidebarCollapsed: value }),
  setInspectorOpen: value => set({ inspectorOpen: value }),
  setSettingsOpen: value => set({ settingsOpen: value }),
  setMobileSidebarOpen: value => set({ mobileSidebarOpen: value }),
  setOverlayVisibility: value => set(state => ({
    overlayVisibility: { ...state.overlayVisibility, ...value },
  })),
  setOverlayFilters: value => set(state => ({
    overlayFilters: normalizeOverlayFilters({ ...state.overlayFilters, ...value }),
  })),
  clearOverlayFilters: () => set({ overlayFilters: { ...DEFAULT_OVERLAY_FILTERS } }),
  setSelectedOpportunityId: value => set({
    selectedOpportunityId: value,
    inspectorOpen: value !== null,
  }),
  setSelectedAnalyticsObject: value => set({
    selectedAnalyticsObject: value,
    selectedOpportunityId: value?.opportunityId ?? null,
    inspectorOpen: value !== null,
  }),
  clearAnalyticsSelection: () => set({ selectedAnalyticsObject: null, selectedOpportunityId: null }),
  setSelectedResearchCohort: value => set({
    selectedResearchCohort: value,
    selectedResearchContrast: null,
  }),
  setSelectedResearchContrast: value => set({
    selectedResearchContrast: value,
    selectedResearchCohort: null,
  }),
  clearResearchSelection: () => set({
    selectedResearchCohort: null,
    selectedResearchContrast: null,
  }),
}), {
  name: UI_STORE_NAME,
  version: UI_STORE_VERSION,
  migrate: persisted => persisted as PersistedUiState,
  partialize: state => ({
    sidebarCollapsed: state.sidebarCollapsed,
    overlayVisibility: state.overlayVisibility,
    overlayFilters: state.overlayFilters,
  }) as PersistedUiState,
  merge: (persisted, current) => mergePersistedUiPreferences(persisted, current),
}));
