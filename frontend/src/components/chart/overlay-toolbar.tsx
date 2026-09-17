"use client";

import type { FrontendAnalyticsOverlays } from "@/lib/api/analytics-overlay-schemas";
import { useUiStore } from "@/lib/ui-store";
import type { OverlayVisibility } from "@/lib/analytics-overlay-state";

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

export function OverlayToolbar({ overlays }: { overlays: FrontendAnalyticsOverlays | null | undefined }) {
  const visibility = useUiStore(state => state.overlayVisibility);
  const setVisibility = useUiStore(state => state.setOverlayVisibility);
  const filters = useUiStore(state => state.overlayFilters);
  const setFilters = useUiStore(state => state.setOverlayFilters);
  const selected = useUiStore(state => state.selectedAnalyticsObject);
  const clearSelection = useUiStore(state => state.clearAnalyticsSelection);
  const available = overlays?.analytics_available === true;
  const eventFamilies = Array.from(new Set(overlays?.technical_events.map(event => event.family) ?? [])).sort();
  const eventTypes = Array.from(new Set(
    (overlays?.technical_events ?? [])
      .filter(event => !filters.technicalEventFamily || event.family === filters.technicalEventFamily)
      .map(event => event.event_type),
  )).sort();

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
        {available && visibility.technicalEvents && (
          <>
            <label className="sr-only" htmlFor="event-family-filter">Famille de Technical Events</label>
            <select
              id="event-family-filter"
              value={filters.technicalEventFamily ?? ""}
              onChange={event => setFilters({
                technicalEventFamily: event.target.value || null,
                technicalEventType: null,
              })}
              className="rounded-md border border-slate-800 bg-slate-950 px-2 py-1 text-[10px] text-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
            >
              <option value="">Toutes familles</option>
              {eventFamilies.map(family => <option key={family} value={family}>{family}</option>)}
            </select>
            <label className="sr-only" htmlFor="event-type-filter">Type de Technical Event</label>
            <select
              id="event-type-filter"
              value={filters.technicalEventType ?? ""}
              onChange={event => setFilters({ technicalEventType: event.target.value || null })}
              className="rounded-md border border-slate-800 bg-slate-950 px-2 py-1 text-[10px] text-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
            >
              <option value="">Tous types</option>
              {eventTypes.map(type => <option key={type} value={type}>{type}</option>)}
            </select>
          </>
        )}
        {!available && (
          <span className="ml-2 text-[10px] text-slate-600">Analytics indisponible pour ce run</span>
        )}
      </div>
      {selected && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-slate-800 bg-slate-950/70 px-2 py-1.5 text-[10px] text-slate-400" aria-live="polite">
          <strong className="text-slate-200">{selected.label}</strong>
          <span>{selected.objectType}</span>
          {selected.opportunityId && <span className="font-mono">opp {selected.opportunityId.slice(0, 12)}</span>}
          {Object.entries(selected.details).slice(0, 4).map(([key, value]) => (
            <span key={key}><span className="text-slate-600">{key}</span> {value}</span>
          ))}
          <button type="button" onClick={clearSelection} className="ml-auto text-slate-500 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400">Fermer</button>
        </div>
      )}
    </div>
  );
}
