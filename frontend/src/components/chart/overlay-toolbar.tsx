"use client";

import { useMemo } from "react";
import type { FrontendAnalyticsOverlays } from "@/lib/api/analytics-overlay-schemas";
import { useUiStore } from "@/lib/ui-store";
import { overlayFiltersActive, type OverlayVisibility } from "@/lib/analytics-overlay-state";
import {
  activeFilterLabels,
  buildFilteredNavigationItems,
  buildNavigationItems,
  navigationNeighbors,
  navigationPosition,
  type FilteredNavigationItem,
} from "@/lib/decision-intelligence-navigation";
import { DecisionIntelligenceFilterPanel } from "@/components/filters/decision-intelligence-filter-panel";

const controls: Array<{ key: keyof OverlayVisibility; label: string; title: string }> = [
  { key: "trading", label: "Trading", title: "Ordres, fills, entrées, sorties et événements PAPER du replay" },
  { key: "scannerCandidates", label: "Candidates", title: "CandidateOpportunity" },
  { key: "scannerBelowThreshold", label: "Scanner", title: "Scanner sous le seuil candidat" },
  { key: "scannerNoTrigger", label: "NO_TRIGGER", title: "Évaluations Scanner NO_TRIGGER (forte densité)" },
  { key: "decisions", label: "Décisions", title: "Professor FINAL LONG / SHORT" },
  { key: "noTradeDecisions", label: "NO_TRADE", title: "Décisions FINAL NO_TRADE" },
  { key: "palermo", label: "Palermo", title: "Revue contradictoire Palermo" },
  { key: "risk", label: "Risk", title: "Décisions du Risk Engine" },
  { key: "technicalEvents", label: "Events", title: "TechnicalEventObservation" },
  { key: "structure", label: "Structure", title: "Market Structure backend" },
  { key: "zigzag", label: "ZigZag", title: "ZigZag causal confirmé" },
  { key: "patterns", label: "Patterns", title: "Patterns causaux" },
  { key: "formingPatterns", label: "FORMING", title: "Patterns encore FORMING" },
];

export function OverlayToolbar({
  overlays,
  cursorTime,
  onNavigate,
}: {
  overlays: FrontendAnalyticsOverlays | null | undefined;
  cursorTime: number | null;
  onNavigate: (item: FilteredNavigationItem) => void;
}) {
  const visibility = useUiStore(state => state.overlayVisibility);
  const setVisibility = useUiStore(state => state.setOverlayVisibility);
  const filters = useUiStore(state => state.overlayFilters);
  const clearFilters = useUiStore(state => state.clearOverlayFilters);
  const selected = useUiStore(state => state.selectedAnalyticsObject);
  const clearSelection = useUiStore(state => state.clearAnalyticsSelection);
  const available = overlays?.analytics_available === true;

  const allItems = useMemo(() => buildNavigationItems(overlays, cursorTime), [overlays, cursorTime]);
  const filteredItems = useMemo(
    () => buildFilteredNavigationItems(overlays, filters, cursorTime),
    [overlays, filters, cursorTime],
  );
  const labels = useMemo(() => activeFilterLabels(filters), [filters]);
  const neighbors = useMemo(
    () => navigationNeighbors(filteredItems, selected, cursorTime),
    [filteredItems, selected, cursorTime],
  );
  const position = useMemo(() => navigationPosition(filteredItems, selected), [filteredItems, selected]);
  const selectionOutsideFilters = selected !== null && position < 0 && overlayFiltersActive(filters);

  return (
    <div className="border-b border-slate-800/90 bg-slate-950/70 px-3 py-2">
      <div className="flex flex-wrap items-center gap-1.5" role="toolbar" aria-label="Overlays du replay">
        <span className="mr-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Overlays</span>
        {controls.map(control => (
          <button
            key={control.key}
            type="button"
            title={control.title}
            aria-pressed={visibility[control.key]}
            disabled={!available}
            onClick={() => setVisibility({ [control.key]: !visibility[control.key] })}
            className="rounded-md border border-slate-800 px-2 py-1 text-[10px] text-slate-400 transition hover:border-slate-700 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-35 aria-pressed:border-violet-500/60 aria-pressed:bg-violet-500/10 aria-pressed:text-violet-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
          >
            {control.label}
          </button>
        ))}
        <span className="mx-1 h-4 w-px bg-slate-800" aria-hidden="true" />
        <DecisionIntelligenceFilterPanel overlays={overlays} items={filteredItems} onNavigate={onNavigate} />
        <span className="rounded-md border border-slate-800 px-2 py-1 font-mono text-[10px] text-slate-400" aria-live="polite">
          {filteredItems.length} / {allItems.length} objets
        </span>
        <button
          type="button"
          disabled={!neighbors.previous}
          onClick={() => neighbors.previous && onNavigate(neighbors.previous)}
          className="rounded-md border border-slate-800 px-2 py-1 text-[10px] text-slate-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
          aria-label="Résultat filtré précédent"
        >
          Previous
        </button>
        <button
          type="button"
          disabled={!neighbors.next}
          onClick={() => neighbors.next && onNavigate(neighbors.next)}
          className="rounded-md border border-slate-800 px-2 py-1 text-[10px] text-slate-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
          aria-label="Résultat filtré suivant"
        >
          Next
        </button>
        <span className="min-w-[42px] text-center font-mono text-[10px] text-slate-600">
          {position >= 0 ? `${position + 1} / ${filteredItems.length}` : `— / ${filteredItems.length}`}
        </span>
        {!available && (
          <span className="ml-2 text-[10px] text-slate-600">Analytics indisponible pour ce run</span>
        )}
      </div>

      {labels.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="Filtres actifs">
          {labels.map(label => (
            <span key={label} className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[10px] text-violet-200">
              {label}
            </span>
          ))}
          <button
            type="button"
            onClick={clearFilters}
            className="ml-1 text-[10px] text-slate-500 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
          >
            Réinitialiser les filtres
          </button>
        </div>
      )}

      {selected && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-slate-800 bg-slate-950/70 px-2 py-1.5 text-[10px] text-slate-400" aria-live="polite">
          <strong className="text-slate-200">{selected.label}</strong>
          <span>{selected.objectType}</span>
          {selected.opportunityId && <span className="font-mono">opp {selected.opportunityId.slice(0, 12)}</span>}
          <span className="font-mono text-slate-600">nav {new Date(selected.navigationTimestamp).toISOString().slice(11, 19)}</span>
          {selectionOutsideFilters && (
            <span className="rounded bg-amber-950/40 px-1.5 py-0.5 text-amber-300">sélection hors filtre</span>
          )}
          <button type="button" onClick={clearSelection} className="ml-auto text-slate-500 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400">Fermer</button>
        </div>
      )}
    </div>
  );
}
