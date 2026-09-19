"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { campaignsQuery } from "@/lib/api/queries";
import { StatusBadge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/utils";
import { formatFractionPercent, formatSignedNumber, quoteAsset } from "./backtest-summary";
import type { CampaignSummary } from "@/lib/api/schemas";

export function BacktestList(){
 const campaigns=useQuery({queryKey:["backtest-campaigns"],queryFn:campaignsQuery,refetchInterval:5000});
 return <section className="panel overflow-hidden"><div className="border-b border-slate-800 p-4"><p className="panel-title">Campagnes</p><h2 className="mt-1 text-lg font-semibold">Historique récent</h2><p className="mt-1 text-xs text-slate-500">Lecture rapide des résultats ; le détail ouvre sur le Résumé avant l’analyse avancée.</p></div>{campaigns.isLoading?<Empty text="Chargement…"/>:campaigns.isError?<Empty text="Impossible de charger les campagnes."/>:campaigns.data?.length===0?<Empty text="Aucune campagne V2 persistée pour le moment."/>:<div className="overflow-x-auto"><table className="w-full min-w-[1080px] text-left text-xs"><thead className="bg-slate-900/50 text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-3">Campagne</th><th>Marché</th><th>IA</th><th>DESIGN</th><th>VALIDATION</th><th>OOS</th><th>Créée</th></tr></thead><tbody>{campaigns.data?.map(c=><CampaignRow key={c.campaign_id} campaign={c}/>)}</tbody></table></div>}</section>
}

function CampaignRow({campaign}:{campaign:CampaignSummary}){
 const quote=quoteAsset(campaign.dataset.symbol);
 return <tr className="border-t border-slate-900 align-top hover:bg-slate-900/50"><td className="px-4 py-3"><div className="flex items-center gap-2"><Link className="font-mono text-violet-300 hover:text-violet-200" href={`/backtests/${campaign.campaign_id}`}>{campaign.campaign_id.slice(0,12)}</Link><StatusBadge value={campaign.status}/></div><p className="mt-1 max-w-[220px] truncate font-mono text-[10px] text-slate-600">{campaign.dataset.dataset_id}</p></td><td className="py-3"><p className="font-medium text-slate-300">{campaign.dataset.symbol} · {campaign.dataset.timeframe}</p><p className="mt-1 text-[10px] text-slate-600">{campaign.dataset.candle_count.toLocaleString("fr-FR")} bougies</p></td><td className="py-3"><StatusBadge value={campaign.ai_mode}/></td><td className="py-3"><PeriodCell period={campaign.design} quote={quote}/></td><td className="py-3"><PeriodCell period={campaign.validation} quote={quote}/></td><td className="py-3"><PeriodCell period={campaign.oos} quote={quote} oos/></td><td className="py-3 pr-4 text-slate-500">{formatDateTime(campaign.created_at)}</td></tr>;
}

function PeriodCell({period,quote,oos=false}:{period:CampaignSummary["design"];quote:string;oos?:boolean}){
 const pnl=Number(period.trading_net.value??NaN);
 const tone=Number.isFinite(pnl)?pnl>0?"text-emerald-300":pnl<0?"text-rose-300":"text-slate-300":"text-slate-300";
 return <div className={oos?"font-semibold":""}><p className={`font-mono ${tone}`}>{formatSignedNumber(period.trading_net.value)}{quote?` ${quote}`:""}</p><p className="mt-1 text-[10px] text-slate-600">{period.closed_trades} trades · DD {formatFractionPercent(period.max_drawdown_pct.value)}</p></div>;
}

function Empty({text}:{text:string}){return <div className="p-8 text-sm text-slate-500">{text}</div>}
