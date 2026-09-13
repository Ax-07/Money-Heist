"use client";
import { StatusBadge } from "@/components/ui/badge";
import type { AgentTrace } from "@/lib/api/schemas";

function strings(value: unknown): string[] {return Array.isArray(value)?value.filter((item):item is string=>typeof item==="string"):[]}
function valueAt(details: Record<string,unknown>,key:string):unknown{return details[key]}

export function ReplayInspector({traces}:{traces:AgentTrace[]}){
 const professor=traces.filter(t=>t.agent==="professor"&&t.phase==="FINAL").at(-1); const palermo=traces.filter(t=>t.agent==="palermo").at(-1); const risk=traces.filter(t=>t.agent==="risk_engine").at(-1); const specialists=traces.filter(t=>t.phase==="ANALYSIS");
 return <div className="space-y-5 p-4"><div><p className="panel-title">Pourquoi ?</p><h3 className="mt-1 text-base font-semibold">Decision Trace</h3></div>{traces.length===0?<p className="text-sm text-slate-500">Aucune décision au timestamp courant.</p>:<>
 <Section title="Professor"><div className="flex items-center gap-2"><StatusBadge value={professor?.title.split(" · ")[0]??"NO_ANALYSIS"}/><span className="text-xs text-slate-500">{professor?.title}</span></div>{strings(valueAt(professor?.details??{},"thesis")).map((item,i)=><p key={i} className="mt-2 text-xs leading-5 text-slate-300">{item}</p>)}</Section>
 <Section title="Crew">{specialists.length===0?<p className="text-xs text-slate-500">Aucun spécialiste enregistré.</p>:specialists.map(trace=><div key={trace.sequence} className="flex items-center justify-between border-b border-slate-900 py-2"><span className="capitalize text-xs text-slate-300">{trace.agent}</span><span className="text-[11px] text-slate-500">{trace.title}</span></div>)}</Section>
 <Section title="Palermo">{palermo?<><StatusBadge value={String(valueAt(palermo.details,"verdict")??palermo.title)}/>{strings(valueAt(palermo.details,"critical_objections")).map((item,i)=><p key={i} className="mt-2 text-xs text-amber-200/80">{item}</p>)}</>:<p className="text-xs text-slate-500">Non fourni.</p>}</Section>
 <Section title="Risk Engine">{risk?<><StatusBadge value={String(valueAt(risk.details,"status")??risk.title)}/><pre className="mt-2 whitespace-pre-wrap text-[10px] leading-4 text-slate-500">{JSON.stringify(risk.details,null,2)}</pre></>:<p className="text-xs text-slate-500">Aucune décision Risk enregistrée.</p>}</Section>
 </>}</div>
}
function Section({title,children}:{title:string;children:React.ReactNode}){return <section><p className="text-[10px] font-semibold uppercase tracking-[.16em] text-slate-600">{title}</p><div className="mt-2">{children}</div></section>}
