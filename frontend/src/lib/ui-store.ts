import { create } from "zustand";
import { persist } from "zustand/middleware";

type UiState = {
  sidebarCollapsed: boolean; inspectorOpen: boolean; settingsOpen: boolean; mobileSidebarOpen: boolean;
  setSidebarCollapsed(value: boolean): void; setInspectorOpen(value: boolean): void; setSettingsOpen(value: boolean): void; setMobileSidebarOpen(value:boolean):void;
};
export const useUiStore = create<UiState>()(persist((set) => ({
  sidebarCollapsed: false, inspectorOpen: true, settingsOpen: false, mobileSidebarOpen: false,
  setSidebarCollapsed: value => set({sidebarCollapsed: value}), setInspectorOpen: value => set({inspectorOpen: value}), setSettingsOpen: value => set({settingsOpen: value}), setMobileSidebarOpen:value=>set({mobileSidebarOpen:value})
}), {name: "money-heist-ui-v2", partialize: state => ({sidebarCollapsed: state.sidebarCollapsed})}));
