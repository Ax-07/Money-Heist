"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { DecisionIndicatorSummary } from "@/components/chart/decision-indicator-summary";
import { TradeTerminalBar } from "@/components/chart/trade-terminal-bar";
import { EquityChart } from "@/components/chart/equity-chart";
import { TradingChart } from "@/components/chart/trading-chart";
import { StatusBadge } from "@/components/ui/badge";
import { DecisionIntelligenceInspector } from "@/components/inspector/decision-intelligence-inspector";
import { ResearchExplorer } from "@/components/research/research-explorer";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  cancelBacktest,
  campaignConfigurationQuery,
  campaignProgressQuery,
  campaignQuery,
  decisionChartQuery,
  replayQuery,
} from "@/lib/api/queries";
import type {
  BacktestReplay,
  CampaignConfiguration,
  CampaignProgress,
  CampaignSummary,
} from "@/lib/api/schemas";
import type { ResearchEvidenceItem } from "@/lib/api/research-schemas";
import { useAnalyticsOverlays } from "@/lib/hooks/use-analytics-overlays";
import { evidenceToOverlaySelection } from "@/lib/research-navigation";
import { selectedTradeFromContext, selectionForTrade, tradePlanForOpportunity, type DecisionChartDisplayMode, type ReplayTrade } from "@/lib/trade-terminal";
import { useUiStore } from "@/lib/ui-store";
import { formatDateTime } from "@/lib/utils";
import { isTerminalCampaignStatus, shouldPollCampaignProgress } from "./campaign-progress";
import { ReplayControls } from "./replay-controls";
import type { ReplaySpeed } from "./replay-state";
import { BacktestSummaryView } from "./backtest-summary-view";

const roles = ["DESIGN", "VALIDATION", "OOS"] as const;
const formatDuration = (ms: number) => ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;

export function BacktestDetail({ campaignId }: { campaignId: string }) {
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => cancelBacktest(campaignId),
    onSuccess: data => queryClient.setQueryData(["campaign-progress", campaignId], data),
  });
  const progress = useQuery({
    queryKey: ["campaign-progress", campaignId],
    queryFn: () => campaignProgressQuery(campaignId),
    refetchInterval: query => shouldPollCampaignProgress(query.state.data) ? 1000 : false,
    retry: false,
  });
  const campaign = useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: () => campaignQuery(campaignId),
    enabled: progress.data?.result_available === true || progress.isError,
    retry: false,
  });
  const configuration = useQuery({
    queryKey: ["campaign-configuration", campaignId],
    queryFn: () => campaignConfigurationQuery(campaignId),
    enabled: campaign.isSuccess,
    retry: false,
  });
  const [view, setView] = useState<"SUMMARY" | "ADVANCED">("SUMMARY");
  const [role, setRole] = useState<(typeof roles)[number]>("OOS");
  const advancedEnabled = campaign.isSuccess && view === "ADVANCED";
  const replay = useQuery({
    queryKey: ["replay", campaignId, role],
    queryFn: () => replayQuery(campaignId, role),
    enabled: advancedEnabled,
    retry: false,
  });
  const decisionChart = useQuery({
    queryKey: ["decision-chart", campaignId, role],
    queryFn: () => decisionChartQuery(campaignId, role),
    enabled: advancedEnabled,
    retry: false,
  });
  const overlays = useAnalyticsOverlays(campaignId, role, advancedEnabled);
  const setSelectedAnalyticsObject = useUiStore(state => state.setSelectedAnalyticsObject);
  const selectedOpportunityId = useUiStore(state => state.selectedOpportunityId);
  const selectedAnalyticsObject = useUiStore(state => state.selectedAnalyticsObject);
  const clearAnalyticsSelection = useUiStore(state => state.clearAnalyticsSelection);
  const clearResearchSelection = useUiStore(state => state.clearResearchSelection);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(1);
  const [decisionDisplayMode, setDecisionDisplayMode] = useState<DecisionChartDisplayMode>("MIXED");
  const chartCandles = decisionChart.data?.candles;
  const cursorTime = chartCandles?.[index]?.time ?? null;
  const replayAtDecisionTimeframe: BacktestReplay | null = replay.data && decisionChart.data
    ? { ...replay.data, timeframe: decisionChart.data.decision_timeframe, candles: decisionChart.data.candles }
    : null;
  const summary = campaign.data;
  const selectedTrade = useMemo(
    () => replay.data
      ? selectedTradeFromContext(replay.data, selectedOpportunityId, selectedAnalyticsObject)
      : undefined,
    [replay.data, selectedAnalyticsObject, selectedOpportunityId],
  );
  const selectedTradePlan = useMemo(
    () => replay.data ? tradePlanForOpportunity(replay.data.traces, selectedOpportunityId) : null,
    [replay.data, selectedOpportunityId],
  );

  useEffect(() => {
    clearAnalyticsSelection();
    clearResearchSelection();
  }, [campaignId, clearAnalyticsSelection, clearResearchSelection]);

  const setReplayIndex = useCallback((nextIndex: number) => {
    setIndex(nextIndex);
  }, []);

  const seekTo = useCallback((time: number) => {
    if (!chartCandles || chartCandles.length === 0) return;
    const target = chartCandles.findIndex(candle => candle.time >= time);
    const nextIndex = target < 0 ? chartCandles.length - 1 : target;
    setIndex(nextIndex);
    setPlaying(false);
  }, [chartCandles]);

  const selectTrade = useCallback((trade: ReplayTrade) => {
    if (!replay.data) return;
    setSelectedAnalyticsObject(selectionForTrade(trade, replay.data.traces));
    seekTo(Math.floor(new Date(trade.opened_at).getTime() / 1000));
  }, [replay.data, seekTo, setSelectedAnalyticsObject]);

  const navigateToResearchEvidence = useCallback((item: ResearchEvidenceItem) => {
    const selection = evidenceToOverlaySelection(item);
    seekTo(Math.floor(new Date(item.navigation_at).getTime() / 1000));
    setSelectedAnalyticsObject(selection);
  }, [seekTo, setSelectedAnalyticsObject]);

  if (progress.data && !progress.data.result_available && !campaign.data) {
    return <ProgressView progress={progress.data} cancelling={cancel.isPending} onCancel={() => cancel.mutate()} />;
  }

  return (
    <div className="space-y-4">
      <div className="panel flex flex-wrap items-center gap-3 p-4">
        <div className="min-w-0">
          <p className="panel-title">Backtest</p>
          <h1 className="mt-1 text-lg font-semibold text-slate-100">
            {summary ? `${summary.dataset.symbol} · ${summary.dataset.timeframe}` : "Campagne historique"}
          </h1>
          <p className="mt-1 truncate font-mono text-[10px] text-slate-600">{campaignId}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge value={summary?.status ?? progress.data?.status ?? "UNKNOWN"} />
          {summary && <StatusBadge value={summary.ai_mode} />}
          {configuration.data && <StatusBadge value={configuration.data.market.positioning_mode} />}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant={view === "SUMMARY" ? "secondary" : "ghost"} onClick={() => setView("SUMMARY")}>Résumé</Button>
          <Button size="sm" variant={view === "ADVANCED" ? "secondary" : "ghost"} onClick={() => setView("ADVANCED")}>Analyse avancée</Button>
        </div>
        {summary && <span className="w-full text-right text-[10px] text-slate-600">{formatDateTime(summary.created_at)}</span>}
      </div>

      {!summary ? (
        <div className="panel p-8 text-sm text-slate-500">Chargement des résultats de campagne…</div>
      ) : view === "SUMMARY" ? (
        <BacktestSummaryView campaign={summary} configuration={configuration.data} onAdvanced={() => setView("ADVANCED")} />
      ) : (
        <>
          <PerformancePanel campaign={summary} />
          {configuration.data && <ConfigurationPanel configuration={configuration.data} />}
          <Tabs
            value={role}
            onValueChange={value => {
              setRole(value as typeof role);
              setIndex(0);
              setPlaying(false);
              clearAnalyticsSelection();
              clearResearchSelection();
            }}
          >
            <TabsList className="w-fit">
              {roles.map(value => <TabsTrigger key={value} value={value}>{value}{value === "OOS" ? " · OUT-OF-SAMPLE" : ""}</TabsTrigger>)}
            </TabsList>
          </Tabs>
          {replay.isError || decisionChart.isError ? (
            <div className="panel p-6">
              <p className="text-sm text-amber-200">Decision Chart indisponible pour cette campagne.</p>
              <p className="mt-2 text-xs leading-5 text-slate-500">Le backend refuse d’afficher des indicateurs qui ne peuvent pas être rattachés au timeframe et aux FeatureSnapshot du replay. Le reste des résultats de campagne reste inchangé.</p>
            </div>
          ) : replay.isLoading || decisionChart.isLoading ? (
            <div className="panel p-8 text-sm text-slate-500">Chargement du Decision Chart…</div>
          ) : replay.data && decisionChart.data && replayAtDecisionTimeframe && (
            <>
              <div className="grid min-h-[600px] gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
                <section className="panel overflow-hidden">
                  <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 px-4 py-3">
                    <StatusBadge value="DECISION CHART" />
                    <span className="text-xs text-slate-300">{decisionChart.data.symbol} · décision {decisionChart.data.decision_timeframe}</span>
                    <span className="text-[10px] text-slate-600">source {decisionChart.data.source_timeframe}</span>
                    <span className="ml-auto text-[10px] text-slate-600">EMA 12/26 · range 20 · marqueurs Professor FINAL sans libellé</span>
                  </div>
                  <div className="border-b border-slate-800 bg-slate-950/70 px-4 py-2 text-[10px] text-slate-500">
                    Cliquez un marqueur de décision pour ouvrir le détail Scanner → agents → Professor → Risk/PAPER dans l’Inspector.
                  </div>
                  <TradeTerminalBar
                    replay={replayAtDecisionTimeframe}
                    mode={decisionDisplayMode}
                    selectedTradeId={selectedTrade?.trade_id ?? null}
                    onModeChange={setDecisionDisplayMode}
                    onSelectTrade={selectTrade}
                  />
                  <div className="h-[520px]">
                    <TradingChart
                      mode="BACKTEST"
                      symbol={decisionChart.data.symbol}
                      timeframe={decisionChart.data.decision_timeframe}
                      candles={decisionChart.data.candles}
                      analyticsOverlays={overlays.data}
                      cursorTime={cursorTime}
                      decisionOnly
                      decisionIndicators={decisionChart.data.indicators}
                      trades={replay.data.trades}
                      decisionDisplayMode={decisionDisplayMode}
                      selectedTradeId={selectedTrade?.trade_id ?? null}
                      selectedOpportunityId={selectedOpportunityId}
                      selectedTradePlan={selectedTradePlan}
                      onOverlaySelect={selection => {
                        const tradeId = selection.details.trade_id
                          ?? ((selection.objectType === "ClosedTrade" || selection.objectType === "ClosedTradeEntry") ? selection.objectId : undefined);
                        const trade = tradeId ? replay.data.trades.find(item => item.trade_id === tradeId) : undefined;
                        setSelectedAnalyticsObject(trade ? selectionForTrade(trade, replay.data.traces) : selection);
                        seekTo(Math.floor(new Date(selection.timestamp).getTime() / 1000));
                      }}
                    />
                  </div>
                  <DecisionIndicatorSummary
                    points={decisionChart.data.indicators}
                    cursorTime={cursorTime}
                    thresholds={decisionChart.data.scanner_thresholds}
                  />
                  <ReplayControls
                    replay={replayAtDecisionTimeframe}
                    index={index}
                    setIndex={setReplayIndex}
                    playing={playing}
                    setPlaying={setPlaying}
                    speed={speed}
                    setSpeed={setSpeed}
                  />
                </section>
                <DecisionIntelligenceInspector
                  campaignId={campaignId}
                  role={role}
                  overlays={overlays.data}
                  trades={replay.data.trades}
                  onSelectTradeId={tradeId => {
                    const trade = replay.data.trades.find(item => item.trade_id === tradeId);
                    if (trade) selectTrade(trade);
                  }}
                />
              </div>
              <ResearchExplorer
                campaignId={campaignId}
                role={role}
                enabled={advancedEnabled}
                onEvidenceSelect={navigateToResearchEvidence}
              />
              <TradeAndEvents replay={replay.data} setIndex={time => seekTo(time)} />
              <section className="panel p-4"><p className="panel-title mb-3">Equity · {role}</p><EquityChart points={replay.data.equity} /></section>
            </>
          )}
        </>
      )}
    </div>
  );
}

function ProgressView({ progress, cancelling, onCancel }: { progress: CampaignProgress; cancelling: boolean; onCancel: () => void }) {
  const terminal = isTerminalCampaignStatus(progress.status);
  const failed = progress.status.toUpperCase() === "FAILED";
  const cancelled = progress.status.toUpperCase() === "CANCELLED";
  const title = failed ? "Historical Replay échoué" : cancelled ? "Historical Replay annulé" : terminal ? "Historical Replay terminé" : "Historical Replay en cours";
  return <div className="space-y-4"><div className="panel p-6"><div className="flex items-center gap-2"><StatusBadge value={progress.status} /><StatusBadge value={progress.phase} /></div><h1 className="mt-4 text-xl font-semibold">{title}</h1><p className="mt-2 text-sm text-slate-400">{progress.message}</p>{progress.error && <div role="alert" className="mt-4 rounded-lg border border-rose-900/60 bg-rose-950/30 p-4"><p className="text-xs font-semibold uppercase tracking-wider text-rose-300">Cause backend</p><pre className="mt-2 whitespace-pre-wrap break-words font-mono text-xs leading-5 text-rose-100">{progress.error}</pre></div>}<div className="mt-5 h-2 overflow-hidden rounded bg-slate-900"><div className="h-full bg-violet-500" style={{ width: `${progress.percent}%` }} /></div><div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500"><span>{progress.percent.toFixed(1)}%</span><span>{progress.opportunity_count} opportunités</span><span>{progress.executed_order_count} ordres PAPER</span><span>Temps: {formatDuration(progress.elapsed_ms)}</span><span>Appels IA: {progress.ai_call_count} · cumulé {formatDuration(progress.ai_wall_time_ms)}</span><span>Agents: {progress.active_agents.join(", ") || "aucun actif"}</span>{terminal && <span>Polling arrêté</span>}</div>{progress.can_cancel && <div className="mt-4"><Button variant="danger" disabled={cancelling} onClick={onCancel}>{cancelling ? "Annulation…" : "Annuler le backtest"}</Button></div>}</div></div>;
}

function PerformancePanel({ campaign }: { campaign: CampaignSummary }) {
  const periods = [campaign.design, campaign.validation, campaign.oos];
  return <details className="panel p-4"><summary className="cursor-pointer text-sm font-semibold text-slate-200">Diagnostics d’exécution</summary><div className="mt-4 grid gap-3 lg:grid-cols-3">{periods.map(period => { const p = period.performance; return <div key={period.role} className="rounded-lg border border-slate-800 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">{period.role}</p>{!p ? <p className="mt-2 text-xs text-slate-500">Profil indisponible.</p> : <div className="mt-2 space-y-1 font-mono text-xs text-slate-300"><p>Total {formatDuration(p.wall_clock_ms)}</p><p>Replay {formatDuration(p.replay_total_ms)} · pipeline {formatDuration(p.replay_pipeline_ms)}</p><p>MTF/features/scanner {formatDuration(p.replay_mtf_feature_scanner_ms)} · lifecycle {formatDuration(p.replay_lifecycle_ms)}</p><p>Contextes {formatDuration(p.replay_context_build_ms)} · mesure 23A {formatDuration(p.measurement_23a_ms)}</p><p>IA {p.ai_request_count} requêtes · latence cumulée {formatDuration(p.ai_provider_latency_ms)}</p></div>}</div>; })}</div><p className="mt-3 text-[10px] leading-4 text-slate-500">La latence IA est cumulative par requête et peut dépasser le temps mur lorsque plusieurs spécialistes sont appelés en parallèle. Ces mesures sont observationnelles et n’entrent dans aucun fingerprint métier.</p></details>;
}

function Card({ label, value }: { label: string; value: string }) {
  return <div className="panel p-4"><p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p><p className="mt-2 text-sm font-medium text-slate-200">{value}</p></div>;
}

function TradeAndEvents({ replay, setIndex }: { replay: BacktestReplay; setIndex: (time: number) => void }) {
  return <section className="panel overflow-hidden"><div className="grid gap-0 lg:grid-cols-2"><div className="max-h-[300px] overflow-auto border-b border-slate-800 lg:border-b-0 lg:border-r"><p className="panel-title sticky top-0 bg-slate-950 px-4 py-3">Trades</p>{replay.trades.length === 0 ? <p className="p-4 text-xs text-slate-500">Aucun trade fermé sur cette période.</p> : replay.trades.map(trade => <button key={trade.trade_id} className="grid w-full grid-cols-[1fr_80px_90px] border-t border-slate-900 px-4 py-3 text-left text-xs hover:bg-slate-900/60" onClick={() => setIndex(Math.floor(new Date(trade.opened_at).getTime() / 1000))}><span><span className="font-mono">{trade.trade_id.slice(0, 10)}</span><br /><span className="text-slate-500">{trade.side} · {trade.entry_price} → {trade.exit_price}</span></span><span>{trade.quantity}</span><span className={Number(trade.net_pnl) >= 0 ? "text-emerald-300" : "text-rose-300"}>{trade.net_pnl}</span></button>)}</div><div className="max-h-[300px] overflow-auto"><p className="panel-title sticky top-0 bg-slate-950 px-4 py-3">Events / Decision Trace</p>{replay.events.map(event => <button key={event.event_id} className="flex w-full items-center gap-3 border-t border-slate-900 px-4 py-2 text-left text-xs hover:bg-slate-900/60" onClick={() => setIndex(Math.floor(new Date(event.observed_at).getTime() / 1000))}><StatusBadge value={event.event_type} /><span className="truncate text-slate-400">{event.label}</span><span className="ml-auto font-mono text-[10px] text-slate-600">{new Date(event.observed_at).toISOString().slice(11, 19)}</span></button>)}</div></div></section>;
}

function ConfigurationPanel({ configuration }: { configuration: CampaignConfiguration }) {
  return <details className="panel p-4"><summary className="cursor-pointer text-sm font-semibold text-slate-200">Configuration figée du run</summary><div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5"><Card label="System" value={configuration.system_id} /><Card label="Capital" value={configuration.execution.initial_balance} /><Card label="Risk / trade" value={`${(Number(configuration.risk.max_risk_per_trade_pct) * 100).toFixed(2)}%`} /><Card label="AI" value={`${configuration.ai.mode} · ${configuration.ai.model_id}`} /><Card label="Walk-Forward" value={configuration.walk_forward.enabled ? `ON · ${configuration.walk_forward.design_bars}/${configuration.walk_forward.validation_bars}/${configuration.walk_forward.oos_bars}` : "OFF"} /></div><div className="mt-3 grid gap-2 font-mono text-[10px] text-slate-500 md:grid-cols-2"><span>commit: {configuration.execution.code_version}</span><span>execution: {configuration.execution.execution_model_version}</span><span>dataset: {configuration.dataset_id}</span><span>budget IA: {configuration.ai.hard_budget} {configuration.ai.currency}</span></div></details>;
}
