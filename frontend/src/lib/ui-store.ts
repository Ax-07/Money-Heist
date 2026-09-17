import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  DEFAULT_OVERLAY_FILTERS,
  DEFAULT_OVERLAY_VISIBILITY,
  type OverlayFilters,
  type OverlaySelection,
  type OverlayVisibility,
} from "@/lib/analytics-overlay-state";

type UiState = {
  sidebarCollapsed: boolean;
  inspectorOpen: boolean;
  settingsOpen: boolean;
  mobileSidebarOpen: boolean;
  overlayVisibility: OverlayVisibility;
  overlayFilters: OverlayFilters;
  selectedOpportunityId: string | null;
  selectedAnalyticsObject: OverlaySelection | null;
  setSidebarCollapsed(value: boolean): void;
  setInspectorOpen(value: boolean): void;
  setSettingsOpen(value: boolean): void;
  setMobileSidebarOpen(value: boolean): void;
  setOverlayVisibility(value: Partial<OverlayVisibility>): void;
  setOverlayFilters(value: Partial<OverlayFilters>): void;
  setSelectedAnalyticsObject(value: OverlaySelection | null): void;
  clearAnalyticsSelection(): void;
};

export const useUiStore = create<UiState>()(persist((set) => ({
  sidebarCollapsed: false,
  inspectorOpen: true,
  settingsOpen: false,
  mobileSidebarOpen: false,
  overlayVisibility: DEFAULT_OVERLAY_VISIBILITY,
  overlayFilters: DEFAULT_OVERLAY_FILTERS,
  selectedOpportunityId: null,
  selectedAnalyticsObject: null,
  setSidebarCollapsed: value => set({ sidebarCollapsed: value }),
  setInspectorOpen: value => set({ inspectorOpen: value }),
  setSettingsOpen: value => set({ settingsOpen: value }),
  setMobileSidebarOpen: value => set({ mobileSidebarOpen: value }),
  setOverlayVisibility: value => set(state => ({
    overlayVisibility: { ...state.overlayVisibility, ...value },
  })),
  setOverlayFilters: value => set(state => ({
    overlayFilters: { ...state.overlayFilters, ...value },
  })),
  setSelectedAnalyticsObject: value => set({
    selectedAnalyticsObject: value,
    selectedOpportunityId: value?.opportunityId ?? null,
  }),
  clearAnalyticsSelection: () => set({ selectedAnalyticsObject: null, selectedOpportunityId: null }),
}), {
  name: "money-heist-ui-v2",
  partialize: state => ({
    sidebarCollapsed: state.sidebarCollapsed,
    overlayVisibility: state.overlayVisibility,
    overlayFilters: state.overlayFilters,
  }),
}));
