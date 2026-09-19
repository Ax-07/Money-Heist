"use client";

import { EquityChart } from "@/components/chart/equity-chart";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { CampaignConfiguration, CampaignSummary } from "@/lib/api/schemas";
import { formatDateTime } from "@/lib/utils";
import {
  formatFractionPercent,
  formatNumber,
  formatPercentValue,
  formatSignedNumber,
  funnelSnapshot,
  metricValue,
  netReturnPercent,
  quoteAsset,
  type CampaignPeriodSummary,
} from "./backtest-summary";

const periodDefinitions = [
  ["DESIGN", "Conception"],
  ["VALIDATION", "Validation"],
  ["OOS", "Out-of-sample"],
] as const;

export function BacktestSummaryView({
  campaign,
  configuration,
  onAdvanced,
}: {
  campaign: CampaignSummary;
  configuration?: CampaignConfiguration;
  onAdvanced: () => void;
}) {
  const quote = quoteAsset(campaign.dataset.symbol);
  const initialBalance = configuration?.execution.initial_balance ?? null;
  const aiCurrency = "EUR";
  const positioning = configuration?.market.positioning_mode ?? "â€”";
  const periods = {
    DESIGN: campaign.design,
    VALIDATION: campaign.validation,
    OOS: campaign.oos,
  } as const;

  return (
    <div className="space-y-4">
      <section className="panel p-5">
        <div className="flex flex-wrap items-start gap-3">
          <div>
            <p className="panel-title">RÃ©sumÃ© de campagne</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-100">
              {campaign.dataset.symbol} Â· {campaign.dataset.timeframe}
            </h2>
            <p className="mt-2 text-xs text-slate-500">
              {formatDateTime(campaign.dataset.start_at)} â†’ {formatDateTime(campaign.dataset.end_at)}
              {" Â· "}{campaign.dataset.candle_count.toLocaleString("fr-FR")} bougies
              {" Â· "}{campaign.dataset.gap_count} gap{campaign.dataset.gap_count === 1 ? "" : "s"}
            </p>
          </div>
          <div className="ml-auto flex flex-wrap gap-2">
            <StatusBadge value={campaign.status} />
            <StatusBadge value={campaign.ai_mode} />
            <StatusBadge value={positioning} />
            <StatusBadge value="PAPER ONLY" />
          </div>
        </div>
        <div className="mt-4 grid gap-2 border-t border-slate-800 pt-4 text-[11px] text-slate-500 md:grid-cols-2 xl:grid-cols-4">
          <span>Dataset <span className="font-mono text-slate-400">{campaign.dataset.dataset_id}</span></span>
          <span>Source <span className="font-mono text-slate-400">{campaign.dataset.source}</span></span>
          <span>Commit <span className="font-mono text-slate-400">{configuration?.execution.code_version?.slice(0, 12) ?? "â€”"}</span></span>
          <span>CrÃ©Ã©e <span className="text-slate-400">{formatDateTime(campaign.created_at)}</span></span>
        </div>
      </section>

      <section className="panel p-5">
        <div className="mb-4">
          <p className="panel-title">Performance</p>
          <h3 className="mt-1 text-base font-semibold text-slate-100">DESIGN / VALIDATION / OOS</h3>
          <p className="mt-1 text-xs text-slate-500">
            Les trois pÃ©riodes utilisent exactement les mÃªmes mÃ©triques. Le rendement net affichÃ© est un ratio de prÃ©sentation : trading net / capital initial figÃ©.
          </p>
        </div>
        <div className="grid gap-3 xl:grid-cols-3">
          {periodDefinitions.map(([role, subtitle]) => (
            <PeriodResultCard
              key={role}
              role={role}
              subtitle={subtitle}
              period={periods[role]}
              initialBalance={initialBalance}
              quote={quote}
              aiCurrency={aiCurrency}
            />
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <div className="mb-4">
          <p className="panel-title">Funnel dÃ©cisionnel</p>
          <h3 className="mt-1 text-base font-semibold text-slate-100">De lâ€™opportunitÃ© au trade clÃ´turÃ©</h3>
          <p className="mt-1 text-xs text-slate-500">
            Projection du Decision Funnel dÃ©jÃ  produit par le backend. Aucun Scanner, agent, Risk ou replay nâ€™est recalculÃ© dans le navigateur.
          </p>
        </div>
        <div className="grid gap-3 xl:grid-cols-3">
          {periodDefinitions.map(([role]) => (
            <FunnelCard key={role} role={role} period={periods[role]} />
          ))}
        </div>
        {configuration?.market.positioning_mode === "SPOT_LONG_ONLY" && (
          <p className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs leading-5 text-slate-500">
            SPOT_LONG_ONLY interdit lâ€™ouverture nette SHORT. Les stances analytiques bearish des spÃ©cialistes peuvent toujours exister ; seules les directions tradables sont contraintes.
          </p>
        )}
      </section>

      <section className="panel p-5">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <div>
            <p className="panel-title">Equity OOS</p>
            <h3 className="mt-1 text-base font-semibold text-slate-100">Out-of-sample</h3>
          </div>
          <span className="ml-auto text-xs text-slate-500">{campaign.oos_equity.length} points persistÃ©s</span>
        </div>
        {campaign.oos_equity.length > 0 ? (
          <EquityChart points={campaign.oos_equity} />
        ) : (
          <p className="rounded-lg border border-dashed border-slate-800 p-5 text-sm text-slate-500">Courbe OOS indisponible pour cette campagne.</p>
        )}
      </section>

      <div className="flex justify-end">
        <Button variant="secondary" onClick={onAdvanced}>Ouvrir lâ€™analyse avancÃ©e â†’</Button>
      </div>
    </div>
  );
}

function PeriodResultCard({
  role,
  subtitle,
  period,
  initialBalance,
  quote,
  aiCurrency,
}: {
  role: string;
  subtitle: string;
  period: CampaignPeriodSummary;
  initialBalance: string | null;
  quote: string;
  aiCurrency: string;
}) {
  const pnl = Number(period.trading_net.value ?? NaN);
  const pnlClass = Number.isFinite(pnl) ? (pnl > 0 ? "text-emerald-300" : pnl < 0 ? "text-rose-300" : "text-slate-200") : "text-slate-200";
  return (
    <article className={`rounded-xl border p-4 ${role === "OOS" ? "border-violet-700/70 bg-violet-950/10" : "border-slate-800 bg-slate-950/40"}`}>
      <div className="flex items-center gap-2">
        <StatusBadge value={role} />
        <span className="text-xs text-slate-500">{subtitle}</span>
      </div>
      <p className={`mt-4 font-mono text-2xl font-semibold ${pnlClass}`}>
        {formatPercentValue(netReturnPercent(period, initialBalance))}
      </p>
      <p className="mt-1 text-[10px] uppercase tracking-wider text-slate-600">Rendement net</p>
      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
        <Metric label="PnL net" value={`${formatSignedNumber(period.trading_net.value)}${quote ? ` ${quote}` : ""}`} />
        <Metric label="Max DD" value={formatFractionPercent(period.max_drawdown_pct.value)} />
        <Metric label="Trades clÃ´turÃ©s" value={String(period.closed_trades)} />
        <Metric label="Win rate" value={formatFractionPercent(period.win_rate.value)} />
        <Metric label="Profit factor" value={metricValue(period.profit_factor)} />
        <Metric label={`CoÃ»t IA (${aiCurrency})`} value={formatNumber(period.ai_cost_eur, 4)} />
        <Metric label="OpportunitÃ©s" value={String(period.opportunities)} />
        <Metric label="Ordres PAPER" value={String(period.executed_orders)} />
      </div>
    </article>
  );
}

function FunnelCard({ role, period }: { role: string; period: CampaignPeriodSummary }) {
  const funnel = funnelSnapshot(period);
  return (
    <article className={`rounded-xl border p-4 ${role === "OOS" ? "border-violet-700/70" : "border-slate-800"}`}>
      <div className="flex items-center justify-between">
        <StatusBadge value={role} />
        <span className="text-[10px] text-slate-600">{period.processed_candles.toLocaleString("fr-FR")} bougies</span>
      </div>
      <div className="mt-4 space-y-2 text-xs">
        <FunnelRow label="Candidate opportunities" value={funnel.candidates} />
        <FunnelRow label="Professor NO_TRADE" value={funnel.noTrade} />
        <FunnelRow label="Trade proposals" value={funnel.proposals} />
        <FunnelRow label="Risk autorisÃ©" value={funnel.riskAuthorized} />
        <FunnelRow label="Risk rejetÃ©" value={funnel.riskRejected} />
        <FunnelRow label="Ordres soumis" value={funnel.orders} />
        <FunnelRow label="Trades clÃ´turÃ©s" value={funnel.closedTrades} />
      </div>
    </article>
  );
}

function FunnelRow({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex items-center gap-3 border-t border-slate-900 pt-2 first:border-t-0 first:pt-0">
      <span className="text-slate-500">{label}</span>
      <span className="ml-auto font-mono text-slate-200">{value ?? "â€”"}</span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p>
      <p className="mt-1 font-mono text-sm text-slate-200">{value}</p>
    </div>
  );
}
