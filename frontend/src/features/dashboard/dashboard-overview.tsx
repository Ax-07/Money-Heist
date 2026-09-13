"use client";
import { useQuery } from "@tanstack/react-query";
import { dashboardQuery, frontendCapabilitiesQuery } from "@/lib/api/queries";
import { StatusBadge } from "@/components/ui/badge";
import { formatDateTime, formatMoney } from "@/lib/utils";

export function DashboardOverview() {
  const dashboard = useQuery({queryKey:["dashboard"], queryFn:dashboardQuery, refetchInterval:3000});
  const caps = useQuery({queryKey:["frontend-capabilities"], queryFn:frontendCapabilitiesQuery, refetchInterval:5000});
  if (dashboard.isLoading) return <State text="Chargement du cockpit…"/>;
  if (dashboard.isError || !dashboard.data) return <State text="Impossible de charger le Dashboard backend." error/>;
  const d = dashboard.data; const totalPositions = d.systems.reduce((n,s)=>n+s.positions.length,0); const ai = d.systems.reduce((n,s)=>n+Number(s.ai_usage.total_cost_eur ?? 0),0);
  return <div className="space-y-4"><div><h1 className="text-2xl font-semibold">Dashboard</h1><p className="mt-1 text-sm text-slate-500">Vue synthétique de l’état observable — {formatDateTime(d.generated_at)}</p></div>
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">{[["System state",<StatusBadge key="a" value={d.system_state}/>],["Mode",<StatusBadge key="b" value={caps.data?.runtime_mode ?? "UNKNOWN"}/>],["Positions",String(totalPositions)],["Opportunités",String(d.opportunities.length)],["Coût IA",formatMoney(ai)]].map(([l,v])=><div key={String(l)} className="panel p-4"><div className="panel-title">{l}</div><div className="mt-3 metric-value">{v}</div></div>)}</div>
    <div className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]"><section className="panel overflow-hidden"><div className="border-b border-slate-800 p-4"><div className="panel-title">Systèmes</div></div><div className="divide-y divide-slate-800">{d.systems.map(s=><div key={s.system_id} className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-4 p-4 text-sm"><div><div className="font-medium">{s.display_name}</div><div className="text-xs text-slate-500">{s.system_id}</div></div><StatusBadge value={s.mode}/><span className="font-mono text-xs">Eq. {formatMoney(s.account.equity)}</span><span className="font-mono text-xs">AI {formatMoney(s.ai_usage.total_cost_eur)}</span></div>)}</div></section>
      <section className="panel overflow-hidden"><div className="border-b border-slate-800 p-4"><div className="panel-title">Événements récents</div></div><div className="max-h-[360px] divide-y divide-slate-800 overflow-auto">{d.events.slice(-12).reverse().map(e=><div key={e.event_id} className="p-3 text-xs"><div className="flex items-center justify-between"><StatusBadge value={e.severity}/><span className="text-slate-600">{formatDateTime(e.created_at)}</span></div><div className="mt-2 text-slate-300">{e.message ?? e.code ?? e.kind}</div></div>)}</div></section></div>
  </div>;
}
function State({text,error=false}:{text:string;error?:boolean}) { return <div className={`panel p-8 text-sm ${error?"text-rose-300":"text-slate-400"}`}>{text}</div>; }
