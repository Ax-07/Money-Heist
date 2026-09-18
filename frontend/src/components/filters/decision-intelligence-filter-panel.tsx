"use client";

import { useMemo, useState, type ReactNode } from "react";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import type { FrontendAnalyticsOverlays } from "@/lib/api/analytics-overlay-schemas";
import type { PatternCausalStatus } from "@/lib/analytics-overlay-state";
import {
  collectDecisionIntelligenceFilterFacets,
  searchNavigationItems,
  type FilteredNavigationItem,
} from "@/lib/decision-intelligence-navigation";
import { useUiStore } from "@/lib/ui-store";
import { formatDateTime } from "@/lib/utils";

export function DecisionIntelligenceFilterPanel({
  overlays,
  items,
  onNavigate,
}: {
  overlays: FrontendAnalyticsOverlays | null | undefined;
  items: FilteredNavigationItem[];
  onNavigate: (item: FilteredNavigationItem) => void;
}) {
  const filters = useUiStore(state => state.overlayFilters);
  const setFilters = useUiStore(state => state.setOverlayFilters);
  const clearFilters = useUiStore(state => state.clearOverlayFilters);
  const selected = useUiStore(state => state.selectedAnalyticsObject);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const facets = useMemo(() => collectDecisionIntelligenceFilterFacets(overlays), [overlays]);
  const searched = useMemo(() => searchNavigationItems(items, search), [items, search]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          type="button"
          disabled={!overlays?.analytics_available}
          className="rounded-md border border-slate-700 px-2.5 py-1 text-[10px] font-medium text-slate-300 hover:border-slate-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
        >
          Filtres & navigation
        </button>
      </DialogTrigger>
      <DialogContent>
        <div className="border-b border-slate-800 px-5 py-4">
          <DialogTitle className="text-base font-semibold text-slate-100">Filtres & navigation</DialogTitle>
          <p className="mt-1 text-xs text-slate-500">
            OR dans une dimension, AND entre dimensions. Les filtres modifient uniquement l’exploration frontend.
          </p>
        </div>
        <div className="grid max-h-[78vh] overflow-auto lg:grid-cols-[minmax(0,1.1fr)_minmax(300px,.9fr)]">
          <div className="space-y-5 border-b border-slate-800 p-5 lg:border-b-0 lg:border-r">
            <FilterGroup title="Scanner">
              <MultiFilter
                label="Classification"
                options={facets.scannerClassifications}
                selected={filters.scannerClassifications}
                onChange={value => setFilters({ scannerClassifications: value })}
              />
              <MultiFilter
                label="Triggers"
                options={facets.scannerTriggers}
                selected={filters.scannerTriggers}
                onChange={value => setFilters({ scannerTriggers: value })}
              />
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Score</p>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <NumberFilter
                    label="Minimum"
                    value={filters.scannerScoreMin}
                    onChange={value => setFilters({ scannerScoreMin: value })}
                  />
                  <NumberFilter
                    label="Maximum"
                    value={filters.scannerScoreMax}
                    onChange={value => setFilters({ scannerScoreMax: value })}
                  />
                </div>
              </div>
            </FilterGroup>

            <FilterGroup title="Decision Funnel">
              <MultiFilter
                label="Professor FINAL"
                options={facets.professorFinal}
                selected={filters.professorFinal}
                onChange={value => setFilters({ professorFinal: value })}
              />
              <MultiFilter
                label="Palermo"
                options={facets.palermoVerdicts}
                selected={filters.palermoVerdicts}
                onChange={value => setFilters({ palermoVerdicts: value })}
              />
              <MultiFilter
                label="Risk"
                options={facets.riskStatuses}
                selected={filters.riskStatuses}
                onChange={value => setFilters({ riskStatuses: value })}
              />
            </FilterGroup>

            <FilterGroup title="Analytics">
              <MultiFilter
                label="Technical Event · famille"
                options={facets.technicalEventFamilies}
                selected={filters.technicalEventFamilies}
                onChange={value => setFilters({ technicalEventFamilies: value })}
              />
              <MultiFilter
                label="Technical Event · type"
                options={facets.technicalEventTypes}
                selected={filters.technicalEventTypes}
                onChange={value => setFilters({ technicalEventTypes: value })}
              />
              <MultiFilter
                label="Technical Event · direction"
                options={facets.technicalEventDirections}
                selected={filters.technicalEventDirections}
                onChange={value => setFilters({ technicalEventDirections: value })}
              />
              <MultiFilter
                label="Pattern · type"
                options={facets.patternTypes}
                selected={filters.patternTypes}
                onChange={value => setFilters({ patternTypes: value })}
              />
              <MultiFilter<PatternCausalStatus>
                label="Pattern · statut causal"
                options={facets.patternStatuses}
                selected={filters.patternStatuses}
                onChange={value => setFilters({ patternStatuses: value })}
              />
              <MultiFilter
                label="Pattern · direction"
                options={facets.patternDirections}
                selected={filters.patternDirections}
                onChange={value => setFilters({ patternDirections: value })}
              />
              <MultiFilter
                label="Pattern · pivot source"
                options={facets.patternPivotSources}
                selected={filters.patternPivotSources}
                onChange={value => setFilters({ patternPivotSources: value })}
              />
            </FilterGroup>

            <button
              type="button"
              onClick={clearFilters}
              className="rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:border-slate-500 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
            >
              Réinitialiser les filtres
            </button>
          </div>

          <div className="p-5">
            <label htmlFor="decision-navigation-search" className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Recherche ID / label / type</label>
            <input
              id="decision-navigation-search"
              value={search}
              onChange={event => setSearch(event.target.value)}
              placeholder="opportunity_id, object_id, Risk…"
              className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500"
            />
            <p className="mt-3 text-[10px] uppercase tracking-wider text-slate-600">
              {searched.length} résultat{searched.length > 1 ? "s" : ""} dans le scope causal
            </p>
            <div className="mt-2 max-h-[56vh] overflow-auto rounded-lg border border-slate-800">
              {searched.length === 0 ? (
                <p className="p-4 text-xs text-slate-500">0 résultat. Les candles et l’Inspector restent utilisables.</p>
              ) : searched.map(item => {
                const active = selected
                  ? item.selection.objectType === selected.objectType
                    && item.selection.objectId === selected.objectId
                    && item.selection.navigationTimestamp === selected.navigationTimestamp
                  : false;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => { onNavigate(item); setOpen(false); }}
                    aria-current={active ? "true" : undefined}
                    className="flex w-full items-start gap-3 border-t border-slate-900 px-3 py-2.5 text-left first:border-t-0 hover:bg-slate-900/60 aria-[current=true]:bg-violet-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400"
                  >
                    <span className="min-w-[58px] font-mono text-[10px] text-slate-600">
                      {new Date(item.timestamp).toISOString().slice(11, 16)}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-xs font-medium text-slate-300">{item.label}</span>
                      <span className="mt-0.5 block truncate text-[10px] text-slate-600">
                        {item.type} · {formatDateTime(item.timestamp)}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function FilterGroup({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <fieldset className="space-y-4 rounded-lg border border-slate-800 p-4">
      <legend className="px-1 text-xs font-semibold text-slate-300">{title}</legend>
      {children}
    </fieldset>
  );
}

function MultiFilter<T extends string>({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: T[];
  selected: T[];
  onChange: (value: T[]) => void;
}) {
  if (options.length === 0) return null;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">{label}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {options.map(option => {
          const checked = selected.includes(option);
          return (
            <label
              key={option}
              className={`cursor-pointer rounded-md border px-2 py-1 text-[10px] transition ${checked ? "border-violet-500/60 bg-violet-500/10 text-violet-200" : "border-slate-800 text-slate-500 hover:border-slate-700 hover:text-slate-300"}`}
            >
              <input
                type="checkbox"
                className="sr-only"
                checked={checked}
                onChange={() => onChange(checked ? selected.filter(value => value !== option) : [...selected, option].sort())}
              />
              {option}
            </label>
          );
        })}
      </div>
    </div>
  );
}

function NumberFilter({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
}) {
  return (
    <label className="text-[10px] text-slate-500">
      {label}
      <input
        type="number"
        min={0}
        max={100}
        value={value ?? ""}
        onChange={event => {
          if (event.target.value === "") { onChange(null); return; }
          const number = Number(event.target.value);
          onChange(Number.isFinite(number) ? Math.min(100, Math.max(0, number)) : null);
        }}
        className="mt-1 w-full rounded-md border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500"
      />
    </label>
  );
}
