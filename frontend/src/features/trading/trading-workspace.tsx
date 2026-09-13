"use client";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { dashboardQuery, frontendCapabilitiesQuery, marketCandlesQuery } from "@/lib/api/queries";
import type { BacktestReplay } from "@/lib/api/schemas";
import { TradingChart } from "@/components/chart/trading-chart";
import { DecisionInspector } from "@/components/inspector/decision-inspector";
import { StatusBadge } from "@/components/ui/badge";

type ChartEvent = BacktestReplay["events"][number];

export function TradingWorkspace(){
 const caps=useQuery({queryKey:["frontend-capabilities"],queryFn:frontendCapabilitiesQuery});
 const dash=useQuery({queryKey:["dashboard"],queryFn:dashboardQuery,refetchInterval:3000});
 const [symbol,setSymbol]=useState("BTC/EUR"); const [timeframe,setTimeframe]=useState("1h");
 const candles=useQuery({queryKey:["market-candles",symbol,timeframe],queryFn:()=>marketCandlesQuery(symbol,timeframe),refetchInterval:30000});
 const [selected,setSelected]=useState<string|null>(null);
 const decision=useMemo(()=>dash.data?.decisions.find(d=>d.opportunity_id===selected)??dash.data?.decisions.at(-1)??null,[dash.data,selected]);
 const events=useMemo<ChartEvent[]>(()=>{
  if(!dash.data)return [];
  const result:ChartEvent[]=[];
  for(const opportunity of dash.data.opportunities){
   if(opportunity.symbol!==symbol||opportunity.timeframe!==timeframe||!opportunity.created_at)continue;
   result.push({event_id:`opp:${opportunity.opportunity_id}`,observed_at:opportunity.created_at,event_type:"OPPORTUNITY",label:`Scanner ${opportunity.priority_score??"—"}`,opportunity_id:opportunity.opportunity_id,agent:null,phase:null,price:null,details:{triggers:opportunity.triggers}});
   const linked=dash.data.decisions.find(item=>item.opportunity_id===opportunity.opportunity_id);
   if(linked?.professor)result.push({event_id:`final:${opportunity.opportunity_id}`,observed_at:opportunity.created_at,event_type:"FINAL",label:linked.professor.direction,opportunity_id:opportunity.opportunity_id,agent:"professor",phase:"FINAL",price:linked.proposal?.entry_price??null,details:{confidence:linked.professor.confidence,thesis:linked.professor.thesis}});
   if(linked?.risk)result.push({event_id:`risk:${linked.risk.risk_decision_id}`,observed_at:linked.risk.created_at,event_type:"RISK",label:linked.risk.status,opportunity_id:opportunity.opportunity_id,agent:"risk_engine",phase:"RISK",price:linked.proposal?.entry_price??null,details:{reason_codes:linked.risk.reason_codes}});
  }
  for(const system of dash.data.systems){
   for(const order of system.orders){if(order.symbol===symbol)result.push({event_id:`order:${order.broker_order_id}`,observed_at:order.created_at,event_type:"ORDER",label:`${order.side} ${order.status}`,opportunity_id:null,agent:null,phase:"EXECUTION",price:order.average_fill_price??order.limit_price??null,details:{client_order_id:order.client_order_id,system_id:order.system_id}})}
   for(const fill of system.fills){const order=system.orders.find(item=>item.broker_order_id===fill.broker_order_id);if(order?.symbol===symbol)result.push({event_id:`fill:${fill.fill_id}`,observed_at:fill.filled_at,event_type:"FILL",label:`Fill ${fill.quantity}`,opportunity_id:null,agent:null,phase:"EXECUTION",price:fill.price,details:{broker_order_id:fill.broker_order_id,fee:fill.fee}})}
  }
  return result.sort((a,b)=>a.observed_at.localeCompare(b.observed_at));
 },[dash.data,symbol,timeframe]);
 return <div className="flex h-full min-h-[760px] flex-col gap-3">
  <div className="panel flex flex-wrap items-center gap-2 p-3"><StatusBadge value={caps.data?.default_system_id??"balanced_v1"}/><StatusBadge value={caps.data?.runtime_mode??"PAPER"}/><select className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs" value={symbol} onChange={e=>setSymbol(e.target.value)}>{caps.data?.market_symbols.map(s=><option key={s}>{s}</option>)}</select><select className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs" value={timeframe} onChange={e=>setTimeframe(e.target.value)}>{caps.data?.market_timeframes.filter(t=>["5m","15m","30m","1h","4h","1d"].includes(t)).map(t=><option key={t}>{t}</option>)}</select><span className="ml-auto text-xs text-slate-500">Kraken public · {candles.data?.source??"chargement"}</span></div>
  <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_340px]"><section className="panel min-h-[520px] overflow-hidden">{candles.data?<TradingChart mode={caps.data?.runtime_mode??"PAPER"} symbol={symbol} timeframe={timeframe} candles={candles.data.candles} events={events} onEventSelect={(event)=>event.opportunity_id&&setSelected(event.opportunity_id)}/>:<div className="p-6 text-sm text-slate-500">{candles.isError?"Market data indisponible.":"Chargement des candles…"}</div>}</section><aside className="panel overflow-auto"><DecisionInspector decision={decision}/></aside></div>
  <div className="panel max-h-[230px] overflow-auto"><div className="grid min-w-[800px] grid-cols-[160px_120px_1fr_130px_130px] border-b border-slate-800 px-4 py-2 text-[10px] uppercase tracking-wider text-slate-500"><span>Opportunity</span><span>Score</span><span>Triggers</span><span>AI</span><span>Risk</span></div>{dash.data?.opportunities.filter(o=>o.symbol===symbol&&o.timeframe===timeframe).slice().reverse().map(o=>{const d=dash.data?.decisions.find(x=>x.opportunity_id===o.opportunity_id);return <button key={o.opportunity_id} onClick={()=>setSelected(o.opportunity_id)} className="grid w-full min-w-[800px] grid-cols-[160px_120px_1fr_130px_130px] border-b border-slate-900 px-4 py-2 text-left text-xs hover:bg-slate-900/70"><span className="truncate font-mono">{o.opportunity_id.slice(0,8)}</span><span>{o.priority_score??"—"}</span><span className="truncate text-slate-400">{o.triggers.join(", ")}</span><span><StatusBadge value={d?.professor?.direction??d?.branch_status??"NO_ANALYSIS"}/></span><span>{d?.risk?<StatusBadge value={d.risk.status}/> : "—"}</span></button>})}</div>
 </div>;
}
