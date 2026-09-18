"use client";

import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { BacktestPeriodRole } from "@/lib/api/decision-intelligence-schemas";
import type {
  FunnelDecisionQualityReport,
  ResearchEvidenceItem,
  ScannerFilteringReport,
} from "@/lib/api/research-schemas";
import { useDecisionQualityResearch, useResearchEvidence } from "@/lib/hooks/use-research";
import {
  funnelContrastSelection,
  scannerContrastSelection,
} from "@/lib/research-navigation";
import type { ResearchCohortSelector } from "@/lib/research-state";
import { useUiStore } from "@/lib/ui-store";
import { formatDateTime } from "@/lib/utils";

type Workspace = "SCANNER_FILTERING" | "FUNNEL_DECISION_QUALITY";
type View = "COHORTS" | "CONTRASTS" | "COVERAGE";

const HORIZONS = [1, 3, 5, 10, 20] as const;

function decimal(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(3) : String(value);
}

function selectorKey(selector: ResearchCohortSelector | null): string {
  if (!selector) return "";
  return [selector.reportType, selector.stage ?? "", selector.dimension, selector.key].join("|");
}

export function ResearchExplorer({
  campaignId,
  role,
  enabled,
  onEvidenceSelect,
}: {
  campaignId: string;
  role: BacktestPeriodRole;
  enabled: boolean;
  onEvidenceSelect: (item: ResearchEvidenceItem) => void;
}) {
  const research = useDecisionQualityResearch(campaignId, role, enabled);
  const selectedCohort = useUiStore(state => state.selectedResearchCohort);
  const selectedContrast = useUiStore(state => state.selectedResearchContrast);
  const setSelectedCohort = useUiStore(state => state.setSelectedResearchCohort);
  const setSelectedContrast = useUiStore(state => state.setSelectedResearchContrast);
  const clearResearchSelection = useUiStore(state => state.clearResearchSelection);
  const [workspace, setWorkspace] = useState<Workspace>("SCANNER_FILTERING");
  const [view, setView] = useState<View>("COHORTS");

  useEffect(() => {
    clearResearchSelection();
  }, [campaignId, role, clearResearchSelection]);

  if (research.isLoading) {
    return <section className="panel p-5 text-sm text-slate-500">Chargement de la recherche descriptive…</section>;
  }
  if (research.isError || !research.data) {
    return (
      <section className="panel p-5">
        <p className="text-sm text-rose-200">Research Explorer indisponible.</p>
        <p className="mt-2 text-xs text-slate-500">Les sidecars 24D.4 n’ont pas pu être lus.</p>
      </section>
    );
  }
  if (!research.data.research_available || !research.data.scanner_filtering || !research.data.funnel_decision_quality) {
    return (
      <section className="panel p-5">
        <p className="text-sm font-medium text-amber-200">Recherche 24D non disponible pour ce run.</p>
        <p className="mt-2 text-xs leading-5 text-slate-500">
          {research.data.unavailable_reason ?? "Ce run historique ne possède pas les sidecars Research 24D.4 pré-calculés."}
        </p>
      </section>
    );
  }

  const scanner = research.data.scanner_filtering;
  const funnel = research.data.funnel_decision_quality;

  return (
    <section className="panel overflow-hidden">
      <div className="border-b border-slate-800 p-4">
        <div className="flex flex-wrap items-start gap-3">
          <div>
            <p className="panel-title">Research Explorer · Decision Quality</p>
            <p className="mt-1 text-xs text-slate-500">
              Descriptif post-hoc · {role} · aucune recommandation de tuning
            </p>
          </div>
          <div className="ml-auto flex gap-2">
            <StatusBadge value={role} />
            <StatusBadge value="READ_ONLY" />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <Tabs value={workspace} onValueChange={value => {
            setWorkspace(value as Workspace);
            clearResearchSelection();
          }}>
            <TabsList>
              <TabsTrigger value="SCANNER_FILTERING">Scanner Filtering Quality</TabsTrigger>
              <TabsTrigger value="FUNNEL_DECISION_QUALITY">Funnel Decision Quality</TabsTrigger>
            </TabsList>
          </Tabs>
          <Tabs value={view} onValueChange={value => setView(value as View)}>
            <TabsList>
              <TabsTrigger value="COHORTS">Cohorts</TabsTrigger>
              <TabsTrigger value="CONTRASTS">Contrasts</TabsTrigger>
              <TabsTrigger value="COVERAGE">Coverage</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </div>

      <div className="grid min-h-[420px] gap-0 xl:grid-cols-[minmax(0,1fr)_minmax(360px,460px)]">
        <div className="min-w-0 overflow-auto p-4">
          {workspace === "SCANNER_FILTERING" ? (
            <ScannerWorkspace
              report={scanner}
              view={view}
              selected={selectedCohort}
              onCohort={setSelectedCohort}
              onContrast={selection => setSelectedContrast(selection)}
            />
          ) : (
            <FunnelWorkspace
              report={funnel}
              view={view}
              selected={selectedCohort}
              onCohort={setSelectedCohort}
              onContrast={selection => setSelectedContrast(selection)}
            />
          )}
        </div>
        <aside className="border-t border-slate-800 p-4 xl:border-l xl:border-t-0">
          <p className="panel-title mb-3">Evidence</p>
          {selectedContrast ? (
            <div className="space-y-4">
              <p className="text-xs text-slate-500">
                Contrast <span className="font-mono text-slate-300">{selectedContrast.kind}</span> — chaque côté réutilise son cohort selector exact.
              </p>
              <EvidencePane
                title="Left"
                campaignId={campaignId}
                role={role}
                selector={selectedContrast.left}
                onOpen={onEvidenceSelect}
              />
              <EvidencePane
                title="Right"
                campaignId={campaignId}
                role={role}
                selector={selectedContrast.right}
                onOpen={onEvidenceSelect}
              />
            </div>
          ) : selectedCohort ? (
            <EvidencePane
              title="Selected cohort"
              campaignId={campaignId}
              role={role}
              selector={selectedCohort}
              onOpen={onEvidenceSelect}
            />
          ) : (
            <p className="text-xs leading-5 text-slate-500">
              Sélectionnez une cohort ou un contrast. L’evidence est chargée à la demande et paginée côté backend.
            </p>
          )}
        </aside>
      </div>
    </section>
  );
}

function ScannerWorkspace({
  report,
  view,
  selected,
  onCohort,
  onContrast,
}: {
  report: ScannerFilteringReport;
  view: View;
  selected: ResearchCohortSelector | null;
  onCohort: (selector: ResearchCohortSelector) => void;
  onContrast: (selection: ReturnType<typeof scannerContrastSelection>) => void;
}) {
  const dimensions = useMemo(
    () => Array.from(new Set(report.cohorts.map(item => item.dimension))),
    [report.cohorts],
  );
  const [dimension, setDimension] = useState("CLASSIFICATION");
  const cohorts = report.cohorts.filter(item => item.dimension === dimension);

  if (view === "COVERAGE") {
    const summary = report.classification_summary;
    return (
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Metric label="Scanner observations" value={report.scanner_count} />
        <Metric label="Candidate" value={summary.candidate_count} />
        <Metric label="Below threshold" value={summary.below_threshold_count} />
        <Metric label="No trigger" value={summary.no_trigger_count} />
        <Metric label="With Forward Outcome" value={report.coverage.with_future_outcome} />
        <Metric label="Missing Forward Outcome" value={report.coverage.without_future_outcome} />
        <Metric label="With Analytics" value={report.coverage.with_analytics} />
        <Metric label="Missing Analytics" value={report.coverage.without_analytics} />
      </div>
    );
  }

  if (view === "CONTRASTS") {
    return (
      <div className="space-y-2">
        {report.contrasts.map(contrast => (
          <button
            key={contrast.kind}
            type="button"
            className="w-full rounded-lg border border-slate-800 p-3 text-left hover:bg-slate-900/60"
            onClick={() => onContrast(scannerContrastSelection(contrast))}
          >
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge value={contrast.kind} />
              <span className="text-xs text-slate-400">{contrast.left_classification} vs {contrast.right_classification}</span>
            </div>
            <div className="mt-3 grid grid-cols-5 gap-2">
              {contrast.horizons.map(item => (
                <HorizonCell
                  key={item.horizon_bars}
                  bars={item.horizon_bars}
                  primary={decimal(item.median_raw_return_delta_pct)}
                  secondary={"N " + item.left_complete_count + "/" + item.right_complete_count}
                />
              ))}
            </div>
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-xs text-slate-500">
        Dimension
        <select
          value={dimension}
          onChange={event => setDimension(event.target.value)}
          className="rounded border border-slate-800 bg-slate-950 px-2 py-1 text-slate-300"
        >
          {dimensions.map(value => <option key={value}>{value}</option>)}
        </select>
      </label>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-xs">
          <thead className="text-left text-[10px] uppercase tracking-wider text-slate-600">
            <tr><th className="pb-2">Cohort</th><th>N</th>{HORIZONS.map(h => <th key={h}>H{h}</th>)}</tr>
          </thead>
          <tbody>
            {cohorts.map(cohort => {
              const selector: ResearchCohortSelector = {
                reportType: "SCANNER_FILTERING",
                dimension: cohort.dimension,
                key: cohort.key,
                stage: null,
              };
              const active = selectorKey(selected) === selectorKey(selector);
              return (
                <tr
                  key={cohort.cohort_fingerprint}
                  className={active ? "bg-violet-950/30" : "border-t border-slate-900 hover:bg-slate-900/40"}
                >
                  <td className="py-2 pr-3">
                    <button type="button" className="font-mono text-left text-slate-300 hover:text-white" onClick={() => onCohort(selector)}>
                      {cohort.key}
                    </button>
                  </td>
                  <td className="pr-3 text-slate-400">{cohort.scanner_count}</td>
                  {cohort.horizons.map(item => <td key={item.horizon_bars} className="pr-3 text-slate-400">{decimal(item.raw_return_median_pct)}</td>)}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-slate-600">Valeurs H*: médiane raw return %, descriptive uniquement.</p>
    </div>
  );
}

function FunnelWorkspace({
  report,
  view,
  selected,
  onCohort,
  onContrast,
}: {
  report: FunnelDecisionQualityReport;
  view: View;
  selected: ResearchCohortSelector | null;
  onCohort: (selector: ResearchCohortSelector) => void;
  onContrast: (selection: ReturnType<typeof funnelContrastSelection>) => void;
}) {
  const stages = useMemo(() => Array.from(new Set(report.cohorts.map(item => item.stage))), [report.cohorts]);
  const [stage, setStage] = useState(stages[0] ?? "PROFESSOR_FINAL");
  const dimensions = useMemo(
    () => Array.from(new Set(report.cohorts.filter(item => item.stage === stage).map(item => item.dimension))),
    [report.cohorts, stage],
  );
  const [dimension, setDimension] = useState("STAGE_RESULT");
  useEffect(() => {
    if (!dimensions.includes(dimension)) setDimension(dimensions[0] ?? "STAGE_RESULT");
  }, [dimensions, dimension]);
  const cohorts = report.cohorts.filter(item => item.stage === stage && item.dimension === dimension);

  if (view === "COVERAGE") {
    return (
      <div className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Metric label="Candidates" value={report.coverage.candidate_count} />
          <Metric label="With Forward Outcome" value={report.coverage.candidates_with_future_outcome} />
          <Metric label="Missing Forward Outcome" value={report.coverage.candidates_without_future_outcome} />
          <Metric label="With Analytics" value={report.coverage.candidates_with_analytics} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-[10px] uppercase tracking-wider text-slate-600">
              <tr><th>Stage</th><th>Records</th><th>Reached</th><th>Not reached</th><th>Failures</th></tr>
            </thead>
            <tbody>
              {report.coverage.stages.map(item => (
                <tr key={item.stage} className="border-t border-slate-900">
                  <td className="py-2 font-mono text-slate-300">{item.stage}</td>
                  <td>{item.record_count}</td><td>{item.reached_count}</td><td>{item.not_reached_count}</td><td>{item.failure_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (view === "CONTRASTS") {
    return (
      <div className="space-y-2">
        {report.contrasts.map(contrast => (
          <button
            key={contrast.kind}
            type="button"
            className="w-full rounded-lg border border-slate-800 p-3 text-left hover:bg-slate-900/60"
            onClick={() => onContrast(funnelContrastSelection(contrast))}
          >
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge value={contrast.stage} />
              <StatusBadge value={contrast.kind} />
              <span className="text-xs text-slate-400">{contrast.left_key} vs {contrast.right_key}</span>
            </div>
            <div className="mt-3 grid grid-cols-5 gap-2">
              {contrast.horizons.map(item => (
                <HorizonCell
                  key={item.horizon_bars}
                  bars={item.horizon_bars}
                  primary={decimal(item.median_directional_return_delta_pct ?? item.median_raw_return_delta_pct)}
                  secondary={"N " + item.left_complete_count + "/" + item.right_complete_count}
                />
              ))}
            </div>
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3 text-xs text-slate-500">
        <label>Stage <select value={stage} onChange={event => setStage(event.target.value)} className="ml-2 rounded border border-slate-800 bg-slate-950 px-2 py-1 text-slate-300">{stages.map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Dimension <select value={dimension} onChange={event => setDimension(event.target.value)} className="ml-2 rounded border border-slate-800 bg-slate-950 px-2 py-1 text-slate-300">{dimensions.map(value => <option key={value}>{value}</option>)}</select></label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] text-xs">
          <thead className="text-left text-[10px] uppercase tracking-wider text-slate-600">
            <tr><th className="pb-2">Cohort</th><th>N</th>{HORIZONS.map(h => <th key={h}>H{h}</th>)}</tr>
          </thead>
          <tbody>
            {cohorts.map(cohort => {
              const selector: ResearchCohortSelector = {
                reportType: "FUNNEL_DECISION_QUALITY",
                stage: cohort.stage,
                dimension: cohort.dimension,
                key: cohort.key,
              };
              const active = selectorKey(selected) === selectorKey(selector);
              return (
                <tr key={cohort.cohort_fingerprint} className={active ? "bg-violet-950/30" : "border-t border-slate-900 hover:bg-slate-900/40"}>
                  <td className="py-2 pr-3"><button type="button" className="font-mono text-left text-slate-300 hover:text-white" onClick={() => onCohort(selector)}>{cohort.key}</button></td>
                  <td className="pr-3 text-slate-400">{cohort.observation_count}</td>
                  {HORIZONS.map(horizon => {
                    const directional = cohort.directional_horizons.find(item => item.horizon_bars === horizon);
                    const raw = cohort.horizons.find(item => item.horizon_bars === horizon);
                    return <td key={horizon} className="pr-3 text-slate-400">{decimal(directional?.directional_return_median_pct ?? raw?.raw_return_median_pct)}</td>;
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-slate-600">H*: médiane directionnelle lorsque la direction existe, sinon raw return. Aucune interprétation causale.</p>
    </div>
  );
}

function EvidencePane({
  title,
  campaignId,
  role,
  selector,
  onOpen,
}: {
  title: string;
  campaignId: string;
  role: BacktestPeriodRole;
  selector: ResearchCohortSelector;
  onOpen: (item: ResearchEvidenceItem) => void;
}) {
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [selector.reportType, selector.stage, selector.dimension, selector.key]);
  const evidence = useResearchEvidence(campaignId, role, selector, page);

  return (
    <div className="rounded-lg border border-slate-800 p-3">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-slate-300">{title}</span>
        <StatusBadge value={selector.dimension} />
      </div>
      <p className="mt-1 break-all font-mono text-[10px] text-slate-600">{selector.stage ? selector.stage + " · " : ""}{selector.key}</p>
      {evidence.isLoading ? (
        <p className="mt-3 text-xs text-slate-500">Chargement…</p>
      ) : evidence.isError || !evidence.data ? (
        <p className="mt-3 text-xs text-rose-300">Evidence indisponible.</p>
      ) : (
        <>
          <div className="mt-3 space-y-2">
            {evidence.data.items.length === 0 && <p className="text-xs text-slate-500">Cohort vide.</p>}
            {evidence.data.items.map(item => (
              <button
                type="button"
                key={item.ref_id}
                onClick={() => onOpen(item)}
                className="w-full rounded border border-slate-900 p-2 text-left hover:border-slate-700 hover:bg-slate-900/60"
              >
                <div className="flex items-center gap-2">
                  <StatusBadge value={item.subject_type} />
                  <span className="truncate text-xs text-slate-300">{item.label}</span>
                </div>
                <p className="mt-1 font-mono text-[10px] text-slate-600">{formatDateTime(item.navigation_at)}</p>
                {item.opportunity_id && <p className="mt-1 truncate font-mono text-[10px] text-slate-600">opp {item.opportunity_id}</p>}
              </button>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-2 text-[10px] text-slate-600">
            <span>{evidence.data.total} refs</span>
            <span className="ml-auto">page {evidence.data.page}/{Math.max(evidence.data.page_count, 1)}</span>
            <Button variant="ghost" disabled={page <= 1} onClick={() => setPage(value => Math.max(1, value - 1))}>←</Button>
            <Button variant="ghost" disabled={evidence.data.page_count === 0 || page >= evidence.data.page_count} onClick={() => setPage(value => value + 1)}>→</Button>
          </div>
        </>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return <div className="rounded-lg border border-slate-800 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p><p className="mt-2 font-mono text-sm text-slate-200">{value}</p></div>;
}

function HorizonCell({ bars, primary, secondary }: { bars: number; primary: string; secondary: string }) {
  return <div><p className="text-[10px] text-slate-600">H{bars}</p><p className="font-mono text-xs text-slate-300">{primary}</p><p className="text-[10px] text-slate-600">{secondary}</p></div>;
}
