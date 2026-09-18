"use client";

import { X } from "lucide-react";

import { StatusBadge } from "@/components/ui/badge";
import type { FrontendAnalyticsOverlays } from "@/lib/api/analytics-overlay-schemas";
import type {
  BacktestPeriodRole,
  FrontendDecisionIntelligenceDetail,
} from "@/lib/api/decision-intelligence-schemas";
import type { OverlaySelection } from "@/lib/analytics-overlay-state";
import { useDecisionIntelligence } from "@/lib/hooks/use-decision-intelligence";
import { useUiStore } from "@/lib/ui-store";
import { formatDateTime } from "@/lib/utils";

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

function text(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function texts(value: unknown): string[] {
  return Array.isArray(value) ? value.map(item => String(item)) : [];
}

function fmtDecimal(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("fr-FR", { maximumFractionDigits: 8 }) : String(value);
}

function pct(value: unknown): string {
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(1)}%` : "—";
}

function causalLabel(selection: OverlaySelection | null): string {
  if (!selection) return "Aucune sélection";
  if (selection.objectType === "CausalZigZagPivot") return "Pivot visible après confirmation";
  if (selection.objectType === "TechnicalEventObservation") return "Événement visible après available_at";
  if (selection.objectType === "PatternOccurrence") return "Pattern visible selon transition disponible";
  if (selection.objectType === "RiskDecision" || selection.objectType === "ProfessorFinal") {
    return "Étape visible après operational_at";
  }
  return "Observation visible au curseur";
}

export function DecisionIntelligenceInspector({
  campaignId,
  role,
  overlays,
}: {
  campaignId: string;
  role: BacktestPeriodRole;
  overlays?: FrontendAnalyticsOverlays | null;
}) {
  const inspectorOpen = useUiStore(state => state.inspectorOpen);
  const setInspectorOpen = useUiStore(state => state.setInspectorOpen);
  const selectedOpportunityId = useUiStore(state => state.selectedOpportunityId);
  const selected = useUiStore(state => state.selectedAnalyticsObject);

  const detail = useDecisionIntelligence(campaignId, selectedOpportunityId, role);

  if (!inspectorOpen) return null;

  const body = (
    <div className="space-y-5 p-4">
      <InspectorHeader
        role={role}
        selection={selected}
        opportunityId={selectedOpportunityId}
        onClose={() => setInspectorOpen(false)}
      />
      {!selected ? (
        <EmptyState />
      ) : selectedOpportunityId ? (
        <OpportunityBody
          detail={detail.data}
          isLoading={detail.isLoading}
          isError={detail.isError}
          selection={selected}
          overlays={overlays}
        />
      ) : (
        <AnalyticsObjectBody selection={selected} overlays={overlays} />
      )}
    </div>
  );

  return (
    <>
      <aside
        aria-label="Decision Intelligence Inspector"
        className="panel hidden min-w-[320px] max-w-[560px] resize-x overflow-auto xl:block"
      >
        {body}
      </aside>
      <div className="fixed inset-x-2 bottom-2 z-40 max-h-[76vh] overflow-auto rounded-xl border border-slate-700 bg-slate-950 shadow-2xl xl:hidden">
        {body}
      </div>
    </>
  );
}

function InspectorHeader({
  role,
  selection,
  opportunityId,
  onClose,
}: {
  role: BacktestPeriodRole;
  selection: OverlaySelection | null;
  opportunityId: string | null;
  onClose: () => void;
}) {
  return (
    <header className="sticky top-0 z-10 -mx-4 -mt-4 border-b border-slate-800 bg-slate-950/95 px-4 py-4 backdrop-blur">
      <div className="flex items-start gap-3">
        <div className="min-w-0">
          <p className="panel-title">Decision Intelligence</p>
          <h2 className="mt-1 truncate text-base font-semibold text-slate-100">
            {selection?.label ?? "Inspector"}
          </h2>
          <div className="mt-2 flex flex-wrap gap-2">
            <StatusBadge value={role} />
            {selection && <StatusBadge value={selection.objectType} />}
          </div>
        </div>
        <button
          type="button"
          aria-label="Fermer l'Inspector"
          onClick={onClose}
          className="ml-auto rounded p-2 text-slate-500 hover:bg-slate-900 hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      {opportunityId && (
        <p className="mt-3 break-all font-mono text-[10px] text-slate-600">
          opportunity_id: {opportunityId}
        </p>
      )}
    </header>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-slate-800 p-5 text-sm text-slate-500">
      Sélectionnez une opportunité, une décision ou un objet Analytics sur le chart pour inspecter
      la chaîne causale persistée.
    </div>
  );
}

function OpportunityBody({
  detail,
  isLoading,
  isError,
  selection,
  overlays,
}: {
  detail?: FrontendDecisionIntelligenceDetail;
  isLoading: boolean;
  isError: boolean;
  selection: OverlaySelection;
  overlays?: FrontendAnalyticsOverlays | null;
}) {
  if (isLoading) {
    return <div className="text-sm text-slate-500">Chargement de la Decision Intelligence…</div>;
  }
  if (isError || !detail) {
    return (
      <Unavailable
        title="Decision Intelligence indisponible"
        message="Le run sélectionné ne possède pas de détail 24C.1 exploitable pour cette opportunité."
      />
    );
  }
  if (!detail.decision_intelligence_available || !detail.record) {
    return (
      <Unavailable
        title="Analytics non disponible"
        message={detail.unavailable_reason ?? "Artefacts pré-calculés absents pour ce run."}
      />
    );
  }

  const record = detail.record;
  const decision = object(record.decision);
  return (
    <>
      <ScannerSection scanner={record.scanner} />
      <AgentsSection decision={decision} />
      <FunnelSection stages={detail.funnel_stages} />
      <RiskExecutionSection decision={decision} />
      <AnalyticsSection
        detail={detail}
        selection={selection}
        overlays={overlays}
      />
    </>
  );
}

function ScannerSection({
  scanner,
}: {
  scanner: NonNullable<FrontendDecisionIntelligenceDetail["record"]>["scanner"];
}) {
  return (
    <Section title="Scanner">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge value={text(scanner.classification)} />
        <span className="font-mono text-xs text-slate-400">
          score {scanner.score} · priorité {scanner.priority_score}
        </span>
      </div>
      <KeyValues
        values={[
          ["Seuil candidat", scanner.candidate_threshold],
          ["Marge", scanner.score_margin],
          ["Régime", scanner.market_regime],
          ["Observé", formatDateTime(scanner.observed_at)],
        ]}
      />
      <ChipList label="Triggers" values={scanner.triggers ?? []} />
    </Section>
  );
}

function AgentsSection({ decision }: { decision: JsonObject }) {
  const plan = object(decision.professor_plan);
  const specialists = object(decision.specialists);
  const runs = Array.isArray(specialists.runs) ? specialists.runs.map(object) : [];
  const palermo = object(decision.palermo);
  const final = object(decision.professor_final);

  return (
    <Section title="Agents">
      <Subsection title="Professor · PLAN">
        <KeyValues
          values={[
            ["Statut", plan.stage_status],
            ["Décision", plan.decision],
            ["Analyse supplémentaire", plan.request_more_analysis],
          ]}
        />
        <ChipList label="Agents sélectionnés" values={texts(plan.selected_agents)} />
        <TextList label="Rationale" values={texts(plan.rationale)} />
      </Subsection>

      <Subsection title="Spécialistes">
        {runs.length === 0 ? (
          <Muted>Aucun spécialiste matérialisé.</Muted>
        ) : (
          <div className="space-y-2">
            {runs.map((run, index) => {
              const analysis = object(run.analysis);
              return (
                <details key={text(run.request_id, String(index))} className="rounded border border-slate-800 p-2">
                  <summary className="cursor-pointer text-xs font-medium text-slate-300">
                    {text(run.agent_id)} · {text(analysis.stance)} · {pct(analysis.confidence)}
                  </summary>
                  <div className="mt-2">
                    <TextList label="Risques" values={texts(analysis.risks)} />
                    <TextList label="Invalidation" values={texts(analysis.invalidation)} />
                    <TextList label="Data gaps" values={texts(analysis.data_gaps)} />
                  </div>
                </details>
              );
            })}
          </div>
        )}
      </Subsection>

      <Subsection title="Palermo">
        <KeyValues
          values={[
            ["Statut", palermo.stage_status],
            ["Verdict", palermo.verdict],
            ["Sévérité", palermo.severity === undefined ? null : pct(palermo.severity)],
          ]}
        />
        <TextList label="Objections critiques" values={texts(palermo.critical_objections)} />
        <TextList label="Checks manquants" values={texts(palermo.missing_checks)} />
      </Subsection>

      <Subsection title="Professor · FINAL">
        <div className="flex flex-wrap gap-2">
          <StatusBadge value={text(final.direction, "NON_ATTEINT")} />
          {final.confidence !== undefined && final.confidence !== null && (
            <span className="text-xs text-slate-400">confiance {pct(final.confidence)}</span>
          )}
        </div>
        <TextList label="Thèse" values={texts(final.thesis)} />
        <TextList label="Contre-évidence" values={texts(final.counter_evidence)} />
        <TextList label="Invalidation" values={texts(final.invalidation)} />
      </Subsection>
    </Section>
  );
}

function FunnelSection({ stages }: { stages: FrontendDecisionIntelligenceDetail["funnel_stages"] }) {
  const ordered = [...stages].sort(
    (left, right) =>
      left.stage_order - right.stage_order
      || (left.stage_instance_order ?? -1) - (right.stage_instance_order ?? -1),
  );
  return (
    <Section title="Decision Funnel">
      {ordered.length === 0 ? (
        <Muted>Aucune attribution de funnel persistée.</Muted>
      ) : (
        <ol className="space-y-2">
          {ordered.map(stage => (
            <li key={stage.record_id} className="rounded border border-slate-800 p-2">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-slate-600">{stage.stage_order}</span>
                <span className="text-xs font-semibold text-slate-300">{stage.stage}</span>
                <StatusBadge value={stage.reached ? (stage.stage_result ?? stage.stage_status ?? "REACHED") : "NOT_REACHED"} />
              </div>
              <div className="mt-1 text-[10px] text-slate-600">
                marché {formatDateTime(stage.market_as_of)}
                {stage.operational_at ? ` · opérationnel ${formatDateTime(stage.operational_at)}` : ""}
              </div>
              {stage.reason_codes.length > 0 && (
                <p className="mt-1 text-xs text-slate-500">{stage.reason_codes.join(" · ")}</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </Section>
  );
}

function RiskExecutionSection({ decision }: { decision: JsonObject }) {
  const risk = object(decision.risk);
  const execution = object(decision.execution);
  const intent = object(execution.order_intent);
  const order = object(execution.order);
  const fill = object(execution.fill);

  return (
    <Section title="Risk & Execution">
      <Subsection title="Risk Engine">
        <div className="flex flex-wrap gap-2">
          <StatusBadge value={text(risk.status, risk.reached ? "REACHED" : "NOT_REACHED")} />
          <span className="text-xs text-slate-500">{texts(risk.reason_codes).join(" · ") || "Aucun reason code"}</span>
        </div>
        <KeyValues
          values={[
            ["Quantité approuvée", fmtDecimal(risk.approved_quantity)],
            ["Risque approuvé", fmtDecimal(risk.approved_risk_amount)],
            ["Notionnel approuvé", fmtDecimal(risk.approved_notional)],
          ]}
        />
      </Subsection>
      <Subsection title="PAPER">
        {!execution.reached ? (
          <Muted>Étape d’exécution non atteinte.</Muted>
        ) : (
          <KeyValues
            values={[
              ["Side", intent.side],
              ["Quantité demandée", fmtDecimal(intent.quantity)],
              ["Order status", order.status],
              ["Fill price", fmtDecimal(fill.price)],
              ["Fill quantity", fmtDecimal(fill.quantity)],
            ]}
          />
        )}
      </Subsection>
    </Section>
  );
}

function AnalyticsSection({
  detail,
  selection,
  overlays,
}: {
  detail: FrontendDecisionIntelligenceDetail;
  selection: OverlaySelection;
  overlays?: FrontendAnalyticsOverlays | null;
}) {
  const record = detail.record!;
  const analytics = record.analytics;
  const matched = String(analytics.status).toUpperCase() === "MATCHED";
  return (
    <Section title="Analytics causal">
      <div className="flex flex-wrap gap-2">
        <StatusBadge value={text(analytics.status)} />
        <StatusBadge value={causalLabel(selection)} />
      </div>
      <KeyValues
        values={[
          ["Analytics run", analytics.analytics_run_id ?? overlays?.analytics_run_id],
          ["Snapshot", analytics.analytics_snapshot_id],
          ["Snapshot as_of", formatDateTime(analytics.analytics_as_of)],
          ["Objet", `${selection.objectType} · ${selection.objectId}`],
          ["Horodatage objet", formatDateTime(selection.timestamp)],
        ]}
      />
      <Fingerprint label="Source cursor" value={analytics.source_cursor_fingerprint} />
      <Fingerprint
        label="Snapshot cursor"
        value={analytics.analytics_snapshot_source_cursor_fingerprint}
      />
      {selection.details.available_at && (
        <CausalityRow label="available_at" value={selection.details.available_at} />
      )}
      {selection.details.confirmed_at && (
        <CausalityRow label="confirmed_at" value={selection.details.confirmed_at} />
      )}
      {selection.details.operational_at && (
        <CausalityRow label="operational_at" value={selection.details.operational_at} />
      )}
      {!matched && (
        <div className="rounded border border-amber-900/60 bg-amber-950/20 p-3 text-xs leading-5 text-amber-200">
          Attribution Analytics non exacte : {analytics.diagnostics.join(" · ") || analytics.status}
        </div>
      )}
    </Section>
  );
}

function AnalyticsObjectBody({
  selection,
  overlays,
}: {
  selection: OverlaySelection;
  overlays?: FrontendAnalyticsOverlays | null;
}) {
  return (
    <>
      <Section title="Objet Analytics">
        <div className="flex flex-wrap gap-2">
          <StatusBadge value={selection.objectType} />
          <StatusBadge value={causalLabel(selection)} />
        </div>
        <KeyValues
          values={[
            ["ID", selection.objectId],
            ["Horodatage", formatDateTime(selection.timestamp)],
            ["Analytics run", overlays?.analytics_run_id],
            ["Source BacktestRun", overlays?.source_backtest_run_id],
          ]}
        />
        <div className="mt-3 space-y-1">
          {Object.entries(selection.details).map(([key, value]) => (
            <div key={key} className="grid grid-cols-[120px_1fr] gap-2 text-xs">
              <span className="text-slate-600">{key}</span>
              <span className="break-all text-slate-300">{value}</span>
            </div>
          ))}
        </div>
      </Section>
      <Unavailable
        title="Aucune opportunité associée"
        message="Cet objet Analytics est inspectable causalement, mais il ne possède pas d’opportunity_id permettant de charger une chaîne Decision Intelligence 24C.1."
      />
    </>
  );
}

function CausalityRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="mt-2 rounded border border-slate-800 bg-slate-900/40 px-3 py-2 text-xs">
      <span className="text-slate-500">{label}</span>
      <span className="ml-2 font-mono text-slate-300">{formatDateTime(value)}</span>
    </div>
  );
}

function Fingerprint({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="mt-2">
      <p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p>
      <p className="mt-1 break-all font-mono text-[10px] leading-4 text-slate-500">{value}</p>
    </div>
  );
}

function Unavailable({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-lg border border-amber-900/50 bg-amber-950/20 p-4">
      <p className="text-xs font-semibold text-amber-200">{title}</p>
      <p className="mt-2 text-xs leading-5 text-amber-100/70">{message}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-slate-800 pt-4 first:border-t-0 first:pt-0">
      <p className="text-[10px] font-semibold uppercase tracking-[.16em] text-slate-600">{title}</p>
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

function Subsection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold text-slate-400">{title}</p>
      <div className="mt-2 space-y-2">{children}</div>
    </div>
  );
}

function KeyValues({ values }: { values: Array<[string, unknown]> }) {
  return (
    <dl className="mt-2 space-y-1">
      {values.map(([label, value]) => (
        <div key={label} className="grid grid-cols-[130px_1fr] gap-2 text-xs">
          <dt className="text-slate-600">{label}</dt>
          <dd className="break-words text-slate-300">{text(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function ChipList({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) return null;
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p>
      <div className="mt-1 flex flex-wrap gap-1">
        {values.map(value => <StatusBadge key={value} value={value} />)}
      </div>
    </div>
  );
}

function TextList({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) return null;
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p>
      <ul className="mt-1 space-y-1 text-xs leading-5 text-slate-400">
        {values.map((value, index) => <li key={index}>• {value}</li>)}
      </ul>
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-slate-500">{children}</p>;
}
