"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { campaignsQuery } from "@/lib/api/queries";
import { StatusBadge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/utils";

export function BacktestList(){
 const campaigns=useQuery({queryKey:["backtest-campaigns"],queryFn:campaignsQuery,refetchInterval:5000});
 return <section className="panel overflow-hidden"><div className="border-b border-slate-800 p-4"><p className="panel-title">Campagnes</p><h2 className="mt-1 text-lg font-semibold">Historique récent</h2></div>{campaigns.isLoading?<Empty text="Chargement…"/>:campaigns.isError?<Empty text="Impossible de charger les campagnes."/>:campaigns.data?.length===0?<Empty text="Aucune campagne V2 persistée pour le moment."/>:<div className="overflow-x-auto"><table className="w-full min-w-[900px] text-left text-xs"><thead className="bg-slate-900/50 text-[10px] uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-3">Campaign</th><th>Dataset</th><th>Symbol</th><th>TF</th><th>AI</th><th>DESIGN</th><th>VALIDATION</th><th>OOS</th><th>Créée</th></tr></thead><tbody>{campaigns.data?.map(c=><tr key={c.campaign_id} className="border-t border-slate-900 hover:bg-slate-900/50"><td className="px-4 py-3"><Link className="font-mono text-violet-300 hover:text-violet-200" href={`/backtests/${c.campaign_id}`}>{c.campaign_id.slice(0,12)}</Link></td><td className="font-mono">{c.dataset.dataset_id}</td><td>{c.dataset.symbol}</td><td>{c.dataset.timeframe}</td><td><StatusBadge value={c.ai_mode}/></td><td>{c.design.closed_trades} trades</td><td>{c.validation.closed_trades} trades</td><td className="font-semibold">{c.oos.closed_trades} trades</td><td>{formatDateTime(c.created_at)}</td></tr>)}</tbody></table></div>}</section>
}
function Empty({text}:{text:string}){return <div className="p-8 text-sm text-slate-500">{text}</div>}
