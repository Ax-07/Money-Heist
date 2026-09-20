"use client";

import { ChevronLeft, ChevronRight, X } from "lucide-react";

import { StatusBadge } from "@/components/ui/badge";
import type { FrontendAnalyticsOverlays } from "@/lib/api/analytics-overlay-schemas";
import type { BacktestReplay } from "@/lib/api/schemas";
import { netTradeReturnPct, tradeResultKind } from "@/lib/trade-result";
import { formatTradeDurationLabel, grossMovePct, realizedRMultiple } from "@/lib/trade-story";
import { riskReasonLabel, tradeDurationLabel } from "@/lib/trade-terminal";
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
  trades,
  onSelectTradeId,
}: {
  campaignId: string;
  role: BacktestPeriodRole;
  overlays?: FrontendAnalyticsOverlays | null;
  trades?: BacktestReplay["trades"];
  onSelectTradeId?: (tradeId: string) => void;
}) {
  const inspectorOpen = useUiStore(state => state.inspectorOpen);
  const setInspectorOpen = useUiStore(state => state.setInspectorOpen);
  const selectedOpportunityId = useUiStore(state => state.selectedOpportunityId);
  const selected = useUiStore(state => state.selectedAnalyticsObject);

  const detail = useDecisionIntelligence(campaignId, selectedOpportunityId, role);
  const headerDecision = detail.data?.record ? object(detail.data.record.decision) : {};
  const headerClosedTrade = detail.data?.record
    ? findClosedTradeForDecision(headerDecision, trades ?? [])
    : undefined;
  const headerResultPct = headerClosedTrade ? netTradeReturnPct(headerClosedTrade) : null;
  const headerResultKind = headerClosedTrade ? tradeResultKind(headerClosedTrade.net_pnl) : null;
  const headerRisk = object(headerDecision.risk);
  const approvedRiskAmount = Number(headerRisk.approved_risk_amount);
  const headerNetPnl = headerClosedTrade ? Number(headerClosedTrade.net_pnl) : Number.NaN;
  const headerR = Number.isFinite(headerNetPnl) && Number.isFinite(approvedRiskAmount) && approvedRiskAmount > 0
    ? headerNetPnl / approvedRiskAmount
    : null;
  const orderedTrades = [...(trades ?? [])].sort((left, right) => Date.parse(left.opened_at) - Date.parse(right.opened_at));
  const headerTradeIndex = headerClosedTrade
    ? orderedTrades.findIndex(trade => trade.trade_id === headerClosedTrade.trade_id)
    : -1;
  const previousTradeId = headerTradeIndex > 0 ? orderedTrades[headerTradeIndex - 1]?.trade_id ?? null : null;
  const nextTradeId = headerTradeIndex >= 0 && headerTradeIndex < orderedTrades.length - 1
    ? orderedTrades[headerTradeIndex + 1]?.trade_id ?? null
    : null;
  const headerTradeResult = headerClosedTrade && headerResultPct !== null && headerResultKind
    ? {
        kind: headerResultKind,
        pct: headerResultPct,
        netPnl: headerClosedTrade.net_pnl,
        duration: tradeDurationLabel(headerClosedTrade.opened_at, headerClosedTrade.closed_at),
        rMultiple: headerR,
      }
    : null;

  if (!inspectorOpen) return null;

  const body = (
    <div className="space-y-5 p-4">
      <InspectorHeader
        role={role}
        selection={selected}
        opportunityId={selectedOpportunityId}
        tradeResult={headerTradeResult}
        previousTradeId={previousTradeId}
        nextTradeId={nextTradeId}
        onSelectTradeId={onSelectTradeId}
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
          trades={trades}
        />
      ) : selected.objectType === "ClosedTrade" || selected.objectType === "ClosedTradeEntry" ? (
        <TradeExitBody selection={selected} />
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

type HeaderTradeResult = {
  kind: "WIN" | "LOSS" | "FLAT";
  pct: number;
  netPnl: string;
  duration: string;
  rMultiple: number | null;
};

function InspectorHeader({
  role,
  selection,
  opportunityId,
  tradeResult,
  previousTradeId,
  nextTradeId,
  onSelectTradeId,
  onClose,
}: {
  role: BacktestPeriodRole;
  selection: OverlaySelection | null;
  opportunityId: string | null;
  tradeResult: HeaderTradeResult | null;
  previousTradeId: string | null;
  nextTradeId: string | null;
  onSelectTradeId?: (tradeId: string) => void;
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
        <div className="ml-auto flex shrink-0 items-start gap-2">
          {tradeResult && (
            <div className="flex flex-col items-end gap-1 pt-0.5">
              <div className="flex items-center gap-2">
                <span className={`font-mono text-lg font-bold leading-none ${tradeResult.kind === "WIN" ? "text-emerald-300" : tradeResult.kind === "LOSS" ? "text-rose-300" : "text-slate-300"}`}>
                  {tradeResult.pct > 0 ? "+" : ""}{tradeResult.pct.toFixed(2)}%
                </span>
                <span className={`rounded-full border px-2 py-0.5 text-[9px] font-bold ${tradeResult.kind === "WIN" ? "border-emerald-700/70 bg-emerald-950/50 text-emerald-300" : tradeResult.kind === "LOSS" ? "border-rose-700/70 bg-rose-950/50 text-rose-300" : "border-slate-700 text-slate-400"}`}>
                  {tradeResult.kind}
                </span>
              </div>
              <span className="font-mono text-[10px] text-slate-500">
                PnL {fmtDecimal(tradeResult.netPnl)} · {tradeResult.duration}{tradeResult.rMultiple === null ? "" : ` · ${tradeResult.rMultiple.toFixed(2)}R`}
              </span>
              <div className="flex items-center gap-1">
                <button type="button" aria-label="Trade précédent" disabled={!previousTradeId || !onSelectTradeId} onClick={() => previousTradeId && onSelectTradeId?.(previousTradeId)} className="rounded border border-slate-800 p-1 text-slate-500 disabled:opacity-25">
                  <ChevronLeft className="h-3 w-3" />
                </button>
                <button type="button" aria-label="Trade suivant" disabled={!nextTradeId || !onSelectTradeId} onClick={() => nextTradeId && onSelectTradeId?.(nextTradeId)} className="rounded border border-slate-800 p-1 text-slate-500 disabled:opacity-25">
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>
            </div>
          )}
          <button type="button" aria-label="Fermer l'Inspector" onClick={onClose} className="rounded p-2 text-slate-500 hover:bg-slate-900 hover:text-slate-200">
            <X className="h-4 w-4" />
          </button>
        </div>
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
  trades,
}: {
  detail?: FrontendDecisionIntelligenceDetail;
  isLoading: boolean;
  isError: boolean;
  selection: OverlaySelection;
  overlays?: FrontendAnalyticsOverlays | null;
  trades?: BacktestReplay["trades"];
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
      <TradeStoryPanel decision={decision} trades={trades} />
        <DecisionSummary scanner={record.scanner} decision={decision} trades={trades} />
      <details className="rounded-lg border border-slate-800 bg-slate-950/30 p-3">
        <summary className="cursor-pointer select-none text-xs font-semibold text-slate-400">
          Détails techniques
        </summary>
        <div className="mt-4 space-y-5">
          <ScannerSection scanner={record.scanner} />
          <AgentsSection decision={decision} />
          <FunnelSection stages={detail.funnel_stages} />
          <RiskExecutionSection decision={decision} />
          <AnalyticsSection detail={detail} selection={selection} overlays={overlays} />
        </div>
      </details>
    </>
  );
}

type ReplayTrade = BacktestReplay["trades"][number];

function closeEnough(left: number, right: number): boolean {
  if (!Number.isFinite(left) || !Number.isFinite(right)) return false;
  const scale = Math.max(1, Math.abs(left), Math.abs(right));
  return Math.abs(left - right) <= scale * 1e-9;
}

function findClosedTradeForDecision(
  decision: JsonObject,
  trades: readonly ReplayTrade[],
): ReplayTrade | undefined {
  const execution = object(decision.execution);
  const fill = object(execution.fill);
  const final = object(decision.professor_final);
  const filledAt = typeof fill.filled_at === "string" ? Date.parse(fill.filled_at) : Number.NaN;
  const fillPrice = Number(fill.price);
  const direction = text(final.direction, "").toUpperCase();
  if (!Number.isFinite(filledAt)) return undefined;
  const candidates = trades.filter(trade => {
    const openedAt = Date.parse(trade.opened_at);
    return Number.isFinite(openedAt)
      && Math.abs(openedAt - filledAt) <= 2000
      && (!direction || trade.side.toUpperCase() === direction);
  });
  if (Number.isFinite(fillPrice)) {
    const exact = candidates.filter(trade => closeEnough(Number(trade.entry_price), fillPrice));
    if (exact.length === 1) return exact[0];
  }
  return candidates.length === 1 ? candidates[0] : undefined;
}

function StoryMetric({
  label,
  value,
  accent = "text-slate-200",
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="rounded-md border border-slate-800/80 bg-slate-950/55 px-2 py-1.5">
      <p className="text-[9px] uppercase tracking-[.18em] text-slate-600">{label}</p>
      <p className={`mt-1 font-mono text-xs font-semibold ${accent}`}>{value}</p>
    </div>
  );
}

function TimelineStep({
  label,
  state,
  accent,
}: {
  label: string;
  state: string;
  accent: string;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${accent}`} />
      <div className="min-w-0">
        <p className="text-[9px] uppercase tracking-[.14em] text-slate-600">{label}</p>
        <p className="truncate text-[11px] text-slate-300">{state}</p>
      </div>
    </div>
  );
}

function TradeStoryPanel({
  decision,
  trades = [],
}: {
  decision: JsonObject;
  trades?: readonly ReplayTrade[];
}) {
  const final = object(decision.professor_final);
  const proposal = object(decision.trade_proposal);
  const risk = object(decision.risk);
  const execution = object(decision.execution);

  const direction = text(final.direction, "NO_TRADE");
  const confidenceValue = Number(final.confidence);
  const confidenceLabel = Number.isFinite(confidenceValue) ? pct(confidenceValue) : "—";
  const riskStatus = text(risk.status, "NOT_REACHED");
  const riskReasons = texts(risk.reason_codes);
  const riskPrimaryReason = riskReasons[0] ? riskReasonLabel(riskReasons[0]) : "—";
  const paperReached = Boolean(execution.reached) || text(execution.status, "").toUpperCase() === "REACHED";

  const plannedEntry = text(proposal.entry_price);
  const plannedStop = text(proposal.stop_price);
  const plannedTargets = texts(proposal.targets);
  const expectedRr = text(proposal.expected_rr);

  const closedTrade = findClosedTradeForDecision(decision, trades);
  const resultPct = closedTrade ? netTradeReturnPct(closedTrade) : null;
  const resultKind = closedTrade ? tradeResultKind(closedTrade.net_pnl) : null;
  const durationLabel = closedTrade ? formatTradeDurationLabel(closedTrade.opened_at, closedTrade.closed_at) : null;
  const realizedR = closedTrade
    ? realizedRMultiple({
        side: closedTrade.side,
        entryPrice: closedTrade.entry_price,
        exitPrice: closedTrade.exit_price,
        stopPrice: plannedStop,
      })
    : null;
  const grossPct = closedTrade
    ? grossMovePct({
        side: closedTrade.side,
        entryPrice: closedTrade.entry_price,
        exitPrice: closedTrade.exit_price,
      })
    : null;

  const resultAccent =
    resultKind === "WIN"
      ? "text-emerald-300"
      : resultKind === "LOSS"
        ? "text-rose-300"
        : "text-slate-300";
  const resultBadgeClass =
    resultKind === "WIN"
      ? "border-emerald-800/70 bg-emerald-950/40 text-emerald-300"
      : resultKind === "LOSS"
        ? "border-rose-800/70 bg-rose-950/40 text-rose-300"
        : "border-slate-700 bg-slate-900 text-slate-300";

  const professorState =
    direction === "NO_TRADE"
      ? "NO_TRADE"
      : `${direction} · confiance ${confidenceLabel}`;

  const riskState =
    riskStatus === "APPROVED"
      ? "APPROVED"
      : riskStatus === "REJECTED"
        ? `REJECTED · ${riskPrimaryReason}`
        : riskStatus;

  const entryState = closedTrade
    ? `ENTRY ${closedTrade.side} @ ${fmtDecimal(closedTrade.entry_price)}`
    : paperReached
      ? "PAPER reached"
      : "No entry";
  const exitState = closedTrade
    ? `EXIT @ ${fmtDecimal(closedTrade.exit_price)}`
    : "Open / none";

  return (
    <section className="rounded-lg border border-slate-800/90 bg-slate-950/70 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[.16em] text-slate-500">Trade story</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusBadge value={direction} />
            <span className="rounded-full border border-slate-800 px-2 py-0.5 text-[10px] text-slate-300">
              Professor {confidenceLabel}
            </span>
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] ${
                riskStatus === "APPROVED"
                  ? "border-emerald-800/70 bg-emerald-950/30 text-emerald-300"
                  : riskStatus === "REJECTED"
                    ? "border-rose-800/70 bg-rose-950/30 text-rose-300"
                    : "border-slate-800 text-slate-400"
              }`}
            >
              {riskStatus === "APPROVED" ? "RISK APPROVED" : riskStatus === "REJECTED" ? "RISK REJECTED" : "RISK —"}
            </span>
          </div>
        </div>

        <div className="min-w-[180px] text-right">
          {resultKind && resultPct !== null ? (
            <>
              <div className={`font-mono text-lg font-semibold ${resultAccent}`}>
                {resultPct > 0 ? "+" : ""}{resultPct.toFixed(2)}%
              </div>
              <div className="mt-1 flex flex-wrap justify-end gap-1">
                <span className={`rounded-full border px-2 py-0.5 text-[9px] font-bold tracking-wide ${resultBadgeClass}`}>
                  {resultKind}
                </span>
                {durationLabel && (
                  <span className="rounded-full border border-slate-800 px-2 py-0.5 text-[9px] text-slate-300">
                    {durationLabel}
                  </span>
                )}
                {realizedR !== null && Number.isFinite(realizedR) && (
                  <span className="rounded-full border border-violet-800/70 bg-violet-950/30 px-2 py-0.5 text-[9px] text-violet-200">
                    {realizedR > 0 ? "+" : ""}{realizedR.toFixed(2)}R
                  </span>
                )}
              </div>
            </>
          ) : (
            <div className="rounded-md border border-slate-800/90 bg-slate-950/60 px-3 py-2 text-[11px] text-slate-500">
              Résultat non disponible
            </div>
          )}
        </div>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-[1.2fr,1fr]">
        <div className="rounded-lg border border-slate-800/80 bg-slate-950/55 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[.16em] text-slate-500">Timeline</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <TimelineStep label="Professor" state={professorState} accent="bg-violet-400" />
            <TimelineStep
              label="Risk"
              state={riskState}
              accent={riskStatus === "REJECTED" ? "bg-rose-400" : riskStatus === "APPROVED" ? "bg-emerald-400" : "bg-slate-500"}
            />
            <TimelineStep label="Entry" state={entryState} accent={closedTrade ? "bg-emerald-400" : "bg-slate-500"} />
            <TimelineStep label="Exit" state={exitState} accent={closedTrade ? "bg-cyan-400" : "bg-slate-500"} />
          </div>
        </div>

        <div className="rounded-lg border border-slate-800/80 bg-slate-950/55 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[.16em] text-slate-500">Prévu vs réel</p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <StoryMetric label="Entry prévu" value={plannedEntry || "—"} />
            <StoryMetric label="Entry réel" value={closedTrade ? fmtDecimal(closedTrade.entry_price) : "—"} />
            <StoryMetric label="Stop" value={plannedStop || "—"} accent="text-rose-300" />
            <StoryMetric label="Exit réel" value={closedTrade ? fmtDecimal(closedTrade.exit_price) : "—"} accent="text-cyan-300" />
            <StoryMetric label="Target(s)" value={plannedTargets.length > 0 ? plannedTargets.join(" · ") : "—"} accent="text-emerald-300" />
            <StoryMetric label="RR attendu" value={expectedRr || "—"} accent="text-violet-200" />
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-lg border border-slate-800/80 bg-slate-950/55 p-3">
        <p className="text-[10px] font-semibold uppercase tracking-[.16em] text-slate-500">Pourquoi ce résultat ?</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <StoryMetric
            label="Mouvement brut"
            value={grossPct === null ? "—" : `${grossPct > 0 ? "+" : ""}${grossPct.toFixed(2)}%`}
            accent={grossPct !== null && grossPct < 0 ? "text-rose-300" : "text-emerald-300"}
          />
          <StoryMetric label="PnL brut exécution" value={closedTrade ? fmtDecimal(Number(closedTrade.net_pnl) + Number(closedTrade.fees)) : "—"} />
          <StoryMetric label="Frais + slippage" value={closedTrade ? `${fmtDecimal(closedTrade.fees)} / ${closedTrade.slippage_cost ? fmtDecimal(closedTrade.slippage_cost) : "—"}` : "—"} />
          <StoryMetric
            label="PnL net"
            value={closedTrade ? fmtDecimal(closedTrade.net_pnl) : "—"}
            accent={closedTrade && Number(closedTrade.net_pnl) < 0 ? "text-rose-300" : "text-emerald-300"}
          />
        </div>
      </div>
    </section>
  );
}

function DecisionSummary({
  scanner,
  decision,
  trades = [],
}: {
  scanner: NonNullable<FrontendDecisionIntelligenceDetail["record"]>["scanner"];
  decision: JsonObject;
  trades?: BacktestReplay["trades"];
}) {
  const final = object(decision.professor_final);
  const risk = object(decision.risk);
  const execution = object(decision.execution);
  const order = object(execution.order);
  const fill = object(execution.fill);
  const riskReasons = texts(risk.reason_codes);
  const closedTrade = findClosedTradeForDecision(decision, trades);

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950/55 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[.16em] text-slate-600">Décision</p>
        <StatusBadge value={text(final.direction, "NON_ATTEINT")} />
        {final.confidence !== undefined && final.confidence !== null && (
          <span className="text-xs text-slate-400">confiance {pct(final.confidence)}</span>
        )}
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <div className="rounded border border-slate-800/80 px-3 py-2">
          <p className="text-[9px] uppercase tracking-wider text-slate-600">Scanner</p>
          <p className="mt-1 text-xs text-slate-300">
            {text(scanner.classification)} · score {scanner.score}
          </p>
        </div>
        <div className="rounded border border-slate-800/80 px-3 py-2">
          <p className="text-[9px] uppercase tracking-wider text-slate-600">Régime</p>
          <p className="mt-1 text-xs text-slate-300">{text(scanner.market_regime)}</p>
        </div>
      </div>

      <ChipList label="Déclencheurs" values={scanner.triggers ?? []} />
      <TextList label="Pourquoi" values={texts(final.thesis)} />
      <TextList label="Contre-évidence" values={texts(final.counter_evidence)} />
      <TextList label="Invalidation" values={texts(final.invalidation)} />

      <div className="mt-3 border-t border-slate-800 pt-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-slate-600">Risk</span>
          <StatusBadge value={text(risk.status, risk.reached ? "REACHED" : "NOT_REACHED")} />
          {riskReasons.length > 0 && (
            <span className="text-xs text-slate-500">{riskReasons.map(riskReasonLabel).join(" · ")}</span>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-slate-600">PAPER</span>
          <StatusBadge value={execution.reached ? text(order.status, "REACHED") : "NOT_REACHED"} />
          {Boolean(execution.reached) && fill.price !== undefined && fill.price !== null && (
            <span className="text-xs text-slate-500">fill {fmtDecimal(fill.price)}</span>
          )}
        </div>
      </div>


      {closedTrade && (
        <div className="mt-3 rounded border border-slate-800/80 bg-slate-900/25 px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[9px] uppercase tracking-wider text-slate-600">Trade PAPER fermé</span>
            <StatusBadge value="CLOSED" />
            <span className="text-xs text-slate-500">{tradeDurationLabel(closedTrade.opened_at, closedTrade.closed_at)}</span>
          </div>
          <KeyValues
            values={[
              ["PnL avant frais", fmtDecimal(Number(closedTrade.net_pnl) + Number(closedTrade.fees))],
              ["Frais", fmtDecimal(closedTrade.fees)],
              ["Slippage mesuré", fmtDecimal(closedTrade.slippage_cost)],
              ["PnL net", fmtDecimal(closedTrade.net_pnl)],
              ["Prix de sortie", fmtDecimal(closedTrade.exit_price)],
            ]}
          />
          <p className="mt-2 text-[9px] leading-4 text-slate-600">
            La cause exacte de sortie (STOP/TARGET/autre) n&apos;est pas exportée par closed-trades ; aucun motif n&apos;est inféré côté frontend.
          </p>
        </div>
      )}
    </section>
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

function TradeExitBody({ selection }: { selection: OverlaySelection }) {
  const details = selection.details;
  const entryView = selection.objectType === "ClosedTradeEntry";
  const pnl = Number(details.net_pnl);
  const pnlLabel = Number.isFinite(pnl) ? pnl.toLocaleString("fr-FR", { maximumFractionDigits: 8 }) : text(details.net_pnl);
  const resultPct = netTradeReturnPct({
    quantity: details.quantity,
    entry_price: details.entry_price,
    net_pnl: details.net_pnl,
  });
  const resultKind = tradeResultKind(details.net_pnl);
  return (
    <Section title={entryView ? "Entrée PAPER" : "Sortie PAPER"}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge value={details.side ?? "CLOSED"} />
        {resultKind && (
          <span className={`rounded-full border px-2 py-0.5 text-[9px] font-bold ${resultKind === "WIN" ? "border-emerald-800/70 bg-emerald-950/40 text-emerald-300" : resultKind === "LOSS" ? "border-rose-800/70 bg-rose-950/40 text-rose-300" : "border-slate-700 text-slate-400"}`}>
            {resultKind}
          </span>
        )}
        {resultPct !== null && (
          <span className={resultPct < 0 ? "text-xs font-semibold font-mono text-rose-300" : resultPct > 0 ? "text-xs font-semibold font-mono text-emerald-300" : "text-xs font-semibold font-mono text-slate-300"}>
            {resultPct > 0 ? "+" : ""}{resultPct.toFixed(2)}%
          </span>
        )}
        <span className={Number.isFinite(pnl) && pnl < 0 ? "text-xs font-mono text-rose-300" : "text-xs font-mono text-emerald-300"}>
          PnL {pnlLabel}
        </span>
      </div>
      <KeyValues
        values={[
          ["Trade", details.trade_id],
          ["Quantité", details.quantity],
          ["Entrée", details.entry_price],
          ["Sortie", details.exit_price],
          ["Ouvert", formatDateTime(details.opened_at)],
          ["Fermé", formatDateTime(details.closed_at)],
          ["Durée", tradeDurationLabel(details.opened_at ?? "", details.closed_at ?? "")],
          ["Frais", details.fees],
          ["Slippage", details.slippage_cost],
        ]}
      />
      <p className="text-[10px] leading-4 text-slate-600">
        Marqueur issu du trade PAPER réellement clôturé. Sur le Decision Chart, sa géométrie est alignée sur la bougie du timeframe de décision contenant closed_at.
      </p>
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
