"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  backtestCapabilitiesQuery,
  datasetPreviewQuery,
  datasetsQuery,
  frontendCapabilitiesQuery,
  marketConstraintsQuery,
  saveDataset,
  startBacktestFromDataset
} from "@/lib/api/queries";
import type { DatasetCatalogItem, DatasetPreview, SplitIndices } from "@/lib/api/schemas";
import {
  buildCampaignConfig,
  defaultBacktestForm,
  initialSplitIndices,
  type AiMode,
  type BacktestFormState,
  type ReasoningEffort
} from "./backtest-config";

const fieldClass = "h-9 rounded-md border border-slate-700 bg-slate-950 px-3 text-sm text-slate-200 outline-none focus:border-violet-500";

type Tab = "dataset" | "periods" | "risk" | "ai" | "execution" | "advanced" | "walk-forward" | "review";

export function BacktestLauncher() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const caps = useQuery({queryKey:["backtest-capabilities"],queryFn:backtestCapabilitiesQuery});
  const front = useQuery({queryKey:["frontend-capabilities"],queryFn:frontendCapabilitiesQuery});
  const datasets = useQuery({queryKey:["backtest-datasets"],queryFn:datasetsQuery});
  const [tab,setTab]=useState<Tab>("dataset");
  const [csvText,setCsvText]=useState("");
  const [fileName,setFileName]=useState("");
  const [symbol,setSymbol]=useState("BTC/EUR");
  const [timeframe,setTimeframe]=useState("1h");
  const [selectedDatasetId,setSelectedDatasetId]=useState("");
  const [preview,setPreview]=useState<DatasetPreview|null>(null);
  const [splitIndices,setSplitIndices]=useState<SplitIndices|null>(null);
  const [form,setForm]=useState<BacktestFormState>(()=>defaultBacktestForm());
  const marketSymbol=preview?.symbol??symbol;
  const constraints=useQuery({queryKey:["market-constraints",marketSymbol],queryFn:()=>marketConstraintsQuery(marketSymbol),retry:false,enabled:Boolean(marketSymbol)});

  const setField=<K extends keyof BacktestFormState>(key:K,value:BacktestFormState[K])=>setForm(current=>({...current,[key]:value}));
  const supported=useMemo(()=>caps.data?.supported_timeframes??["1h"],[caps.data]);

  useEffect(()=>{
    const systemId=front.data?.default_system_id;
    if(!systemId)return;
    setForm(current=>current.systemId==="balanced_v1"?{...current,systemId}:current);
  },[front.data?.default_system_id]);
  useEffect(()=>{
    const data=constraints.data;
    if(!data)return;
    setForm(current=>({...current,qtyStep:data.qty_step,minQty:data.min_qty,minNotional:data.min_notional,marketMaxLeverage:data.max_leverage}));
  },[constraints.data]);

  const selectPreview=(next:DatasetPreview)=>{
    setPreview(next); setSelectedDatasetId(next.dataset_id); setSymbol(next.symbol); setTimeframe(next.timeframe); setSplitIndices(initialSplitIndices(next));
    if(!["1m","5m","15m"].includes(next.timeframe)) setForm(current=>({...current,derivativesEnabled:false,denverPriorEnabled:false}));
    setTab("periods");
  };
  const saveMutation=useMutation({
    mutationFn:()=>saveDataset({csv_text:csvText,symbol,timeframe,source:`frontend_v2:${fileName||"upload.csv"}`,candle_interval_seconds:null}),
    onSuccess:async next=>{selectPreview(next);await queryClient.invalidateQueries({queryKey:["backtest-datasets"]});}
  });
  const loadDatasetMutation=useMutation({
    mutationFn:(datasetId:string)=>datasetPreviewQuery(datasetId),
    onSuccess:selectPreview
  });
  const runMutation=useMutation({
    mutationFn:()=>{
      if(!preview||!selectedDatasetId)throw new Error("Sélectionnez et validez un dataset.");
      if(!splitIndices)throw new Error("Définissez les périodes DESIGN / VALIDATION / OOS.");
      const config=buildCampaignConfig(preview,splitIndices,form);
      return startBacktestFromDataset({dataset_id:selectedDatasetId,...config});
    },
    onSuccess:progress=>router.push(`/backtests/${progress.campaign_id}`)
  });
  const changeAiMode=(mode:AiMode)=>setForm(current=>({
    ...current,
    aiMode:mode,
    modelId:mode==="MOCK"?"mock-backtest-v1":current.modelId.startsWith("mock-")?"":current.modelId,
    inputPrice:mode==="MOCK"?"0":current.inputPrice,
    outputPrice:mode==="MOCK"?"0":current.outputPrice,
    mockAgentCoverage:mode==="MOCK"?current.mockAgentCoverage:false
  }));
  const launchError=saveMutation.error??loadDatasetMutation.error??runMutation.error;

  return <section className="panel overflow-hidden">
    <div className="flex flex-wrap items-center gap-3 border-b border-slate-800 p-5">
      <div><p className="panel-title">Nouvelle campagne</p><h2 className="mt-1 text-xl font-semibold">Backtest Cockpit</h2><p className="mt-1 text-xs text-slate-500">Configuration explicite, figée puis rejouée par le moteur Batch 16.</p></div>
      <div className="ml-auto flex gap-2"><StatusBadge value="PAPER ONLY"/><StatusBadge value={form.aiMode}/></div>
    </div>
    <Tabs value={tab} onValueChange={value=>setTab(value as Tab)}>
      <div className="overflow-x-auto border-b border-slate-800 px-4 py-3"><TabsList className="w-max">
        <TabsTrigger value="dataset">1 · Dataset</TabsTrigger><TabsTrigger value="periods" disabled={!preview}>2 · Périodes</TabsTrigger><TabsTrigger value="risk" disabled={!preview}>3 · Risk</TabsTrigger><TabsTrigger value="ai" disabled={!preview}>4 · IA</TabsTrigger><TabsTrigger value="execution" disabled={!preview}>5 · Exécution</TabsTrigger><TabsTrigger value="advanced" disabled={!preview}>6 · Données avancées</TabsTrigger><TabsTrigger value="walk-forward" disabled={!preview}>7 · Walk-Forward</TabsTrigger><TabsTrigger value="review" disabled={!preview}>8 · Revue</TabsTrigger>
      </TabsList></div>
      <div className="p-5">
        <TabsContent value="dataset"><DatasetStep datasets={datasets.data??[]} selectedDatasetId={selectedDatasetId} onSelectDataset={id=>{setSelectedDatasetId(id);if(id)loadDatasetMutation.mutate(id);}} datasetLoading={loadDatasetMutation.isPending} csvText={csvText} setCsvText={setCsvText} fileName={fileName} setFileName={setFileName} symbol={symbol} setSymbol={value=>{setSymbol(value);setPreview(null);setSelectedDatasetId("");}} timeframe={timeframe} setTimeframe={value=>{setTimeframe(value);setPreview(null);setSelectedDatasetId("");}} symbols={front.data?.market_symbols??["BTC/EUR","ETH/EUR","SOL/EUR"]} timeframes={supported} savePending={saveMutation.isPending} onSave={()=>saveMutation.mutate()} preview={preview}/></TabsContent>
        <TabsContent value="periods">{preview&&<PeriodsStep preview={preview} indices={splitIndices} setIndices={setSplitIndices}/>}</TabsContent>
        <TabsContent value="risk">{preview&&<RiskStep form={form} setField={setField} constraintsStatus={constraints.data?"KRAKEN PUBLIC":constraints.isError?"MANUEL":"CHARGEMENT"}/>}</TabsContent>
        <TabsContent value="ai"><AiStep form={form} setField={setField} modes={(caps.data?.modes??["MOCK","CACHED","LIVE_EVAL"]) as AiMode[]} liveEvalAvailable={caps.data?.live_eval_available??false} onMode={changeAiMode}/></TabsContent>
        <TabsContent value="execution"><ExecutionStep form={form} setField={setField}/></TabsContent>
        <TabsContent value="advanced">{preview&&<AdvancedDataStep timeframe={preview.timeframe} form={form} setField={setField}/>}</TabsContent>
        <TabsContent value="walk-forward">{preview&&<WalkForwardStep form={form} setField={setField} candleCount={preview.candle_count}/>}</TabsContent>
        <TabsContent value="review">{preview&&splitIndices&&<ReviewStep preview={preview} indices={splitIndices} form={form} pending={runMutation.isPending} onLaunch={()=>runMutation.mutate()}/>}</TabsContent>
      </div>
    </Tabs>
    {launchError&&<div className="border-t border-rose-900/60 bg-rose-950/20 px-5 py-3 text-sm text-rose-300">{String(launchError.message)}</div>}
  </section>;
}

function DatasetStep({datasets,selectedDatasetId,onSelectDataset,datasetLoading,csvText,setCsvText,fileName,setFileName,symbol,setSymbol,timeframe,setTimeframe,symbols,timeframes,savePending,onSave,preview}:{datasets:DatasetCatalogItem[];selectedDatasetId:string;onSelectDataset:(id:string)=>void;datasetLoading:boolean;csvText:string;setCsvText:(v:string)=>void;fileName:string;setFileName:(v:string)=>void;symbol:string;setSymbol:(v:string)=>void;timeframe:string;setTimeframe:(v:string)=>void;symbols:string[];timeframes:string[];savePending:boolean;onSave:()=>void;preview:DatasetPreview|null}){
 return <div className="space-y-5"><div className="grid gap-4 xl:grid-cols-2"><Block title="Réutiliser un dataset" description="Les datasets validés par Frontend V2 sont persistés côté backend."><label className="text-xs text-slate-400">Dataset enregistré<select className={`${fieldClass} mt-1 w-full`} value={selectedDatasetId} onChange={e=>onSelectDataset(e.target.value)}><option value="">— sélectionner —</option>{datasets.map(item=><option key={item.dataset_id} value={item.dataset_id}>{item.symbol} · {item.timeframe} · {item.candle_count} bars · {item.start_at.slice(0,10)} → {item.end_at.slice(0,10)}</option>)}</select></label>{datasetLoading&&<p className="mt-3 text-xs text-slate-500">Chargement des bornes du dataset…</p>}{datasets.length===0&&<p className="mt-3 text-xs text-slate-600">Aucun dataset V2 enregistré pour le moment.</p>}</Block>
 <Block title="Importer un nouveau CSV" description="Le CSV est validé par l'importeur historique du backend puis stocké localement côté backend pour être réutilisable."><div className="grid gap-3 sm:grid-cols-2"><label className="text-xs text-slate-400">Symbol<input list="backtest-symbols" className={`${fieldClass} mt-1 w-full`} value={symbol} onChange={e=>setSymbol(e.target.value.toUpperCase())} placeholder="BTC/USDC"/><datalist id="backtest-symbols">{symbols.map(value=><option key={value} value={value}/>)}</datalist></label><label className="text-xs text-slate-400">Timeframe<select className={`${fieldClass} mt-1 w-full`} value={timeframe} onChange={e=>setTimeframe(e.target.value)}>{timeframes.map(value=><option key={value}>{value}</option>)}</select></label></div><label className="mt-3 block text-xs text-slate-400">Fichier CSV<input type="file" accept=".csv,text/csv" className="mt-2 block w-full text-xs" onChange={async e=>{const file=e.target.files?.[0];if(file){setFileName(file.name);setCsvText(await file.text());}}}/></label><div className="mt-4 flex items-center gap-3"><Button variant="secondary" disabled={!csvText||savePending} onClick={onSave}>{savePending?"Validation…":"Valider & enregistrer"}</Button>{fileName&&<span className="text-xs text-slate-500">{fileName}</span>}</div></Block></div>{preview&&<DatasetSummary preview={preview}/>}</div>
}

function DatasetSummary({preview}:{preview:DatasetPreview}){return <div className="grid gap-3 rounded-lg border border-slate-800 bg-slate-950/60 p-4 sm:grid-cols-2 xl:grid-cols-6"><Metric label="Dataset" value={preview.dataset_id}/><Metric label="Symbol / TF" value={`${preview.symbol} · ${preview.timeframe}`}/><Metric label="Bougies" value={String(preview.candle_count)}/><Metric label="Période" value={`${preview.start_at.slice(0,10)} → ${preview.end_at.slice(0,10)}`}/><Metric label="Qualité" value={preview.is_valid?`VALID · ${preview.gap_count} gaps`:"INVALID"}/><Metric label="SHA-256" value={preview.content_sha256.slice(0,16)}/></div>}

function PeriodsStep({preview,indices,setIndices}:{preview:DatasetPreview;indices:SplitIndices|null;setIndices:(value:SplitIndices)=>void}){
 if(!indices)return <p className="text-sm text-amber-200">Le backend n’a pas fourni assez d’information pour découper ce dataset.</p>;
 const update=(key:keyof SplitIndices,value:string)=>setIndices({...indices,[key]:Number(value)});
 const count=(start:number,end:number)=>Math.max(0,end-start+1);
 return <div className="space-y-5"><Block title="DESIGN / VALIDATION / OOS" description="Les bornes sont des indices de bougies. Elles doivent rester strictement ordonnées et sans chevauchement."><div className="grid gap-4 lg:grid-cols-3"><PeriodCard title="DESIGN" start={indices.design_start} end={indices.design_end} max={preview.candle_count-1} onStart={v=>update("design_start",v)} onEnd={v=>update("design_end",v)} count={count(indices.design_start,indices.design_end)} preview={preview}/><PeriodCard title="VALIDATION" start={indices.validation_start} end={indices.validation_end} max={preview.candle_count-1} onStart={v=>update("validation_start",v)} onEnd={v=>update("validation_end",v)} count={count(indices.validation_start,indices.validation_end)} preview={preview}/><PeriodCard title="OOS · OUT-OF-SAMPLE" start={indices.oos_start} end={indices.oos_end} max={preview.candle_count-1} onStart={v=>update("oos_start",v)} onEnd={v=>update("oos_end",v)} count={count(indices.oos_start,indices.oos_end)} preview={preview}/></div></Block><p className="rounded-lg border border-amber-900/50 bg-amber-950/20 p-3 text-xs leading-5 text-amber-200/80">OOS doit rester hors échantillon : évite d’ajuster la stratégie après avoir consulté ses résultats. Le moteur conserve les rapports DESIGN, VALIDATION et OOS séparés.</p></div>
}

function PeriodCard({title,start,end,max,onStart,onEnd,count,preview}:{title:string;start:number;end:number;max:number;onStart:(v:string)=>void;onEnd:(v:string)=>void;count:number;preview:DatasetPreview}){const at=(index:number)=>preview.candle_close_ms[index]?new Date(preview.candle_close_ms[index]).toISOString():"—";return <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><div className="flex items-center justify-between"><p className="text-xs font-semibold text-slate-200">{title}</p><span className="text-[10px] text-slate-500">{count} bars</span></div><div className="mt-3 grid grid-cols-2 gap-2"><NumberField label="Start index" value={String(start)} min={0} max={max} onChange={onStart}/><NumberField label="End index" value={String(end)} min={0} max={max} onChange={onEnd}/></div><p className="mt-3 break-all font-mono text-[10px] text-slate-600">{at(start)}<br/>→ {at(end)}</p></div>}

function RiskStep({form,setField,constraintsStatus}:{form:BacktestFormState;setField:<K extends keyof BacktestFormState>(key:K,value:BacktestFormState[K])=>void;constraintsStatus:string}){return <div className="space-y-5"><Block title="Profil de risque" description="Valeurs en pourcentage côté interface ; elles sont converties en fractions avant envoi au Risk Engine."><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><TextField label="Risk profile ID" value={form.riskProfileId} onChange={v=>setField("riskProfileId",v)}/><TextField label="Risk version" value={form.riskVersion} onChange={v=>setField("riskVersion",v)}/><TextField label="Risque / trade (%)" value={form.maxRiskPerTradePct} onChange={v=>setField("maxRiskPerTradePct",v)}/><TextField label="Perte journalière max (%)" value={form.maxDailyLossPct} onChange={v=>setField("maxDailyLossPct",v)}/><TextField label="Drawdown max (%)" value={form.maxDrawdownPct} onChange={v=>setField("maxDrawdownPct",v)}/><TextField label="Portfolio risk max (%)" value={form.maxPortfolioRiskPct} onChange={v=>setField("maxPortfolioRiskPct",v)}/><TextField label="Exposition corrélée max (%)" value={form.maxCorrelatedExposurePct} onChange={v=>setField("maxCorrelatedExposurePct",v)}/><TextField label="Max positions" value={form.maxPositions} onChange={v=>setField("maxPositions",v)}/><TextField label="Max leverage Risk" value={form.riskMaxLeverage} onChange={v=>setField("riskMaxLeverage",v)}/><TextField label="RR minimum" value={form.minExpectedRr} onChange={v=>setField("minExpectedRr",v)}/></div></Block><Block title="Contraintes marché" description="Préremplies depuis les métadonnées publiques Kraken quand disponibles, mais visibles et modifiables."><div className="mb-3"><StatusBadge value={constraintsStatus}/></div><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5"><TextField label="qty_step" value={form.qtyStep} onChange={v=>setField("qtyStep",v)}/><TextField label="min_qty" value={form.minQty} onChange={v=>setField("minQty",v)}/><TextField label="min_notional" value={form.minNotional} onChange={v=>setField("minNotional",v)}/><TextField label="max_qty (optionnel)" value={form.maxQty} onChange={v=>setField("maxQty",v)}/><TextField label="max_leverage" value={form.marketMaxLeverage} onChange={v=>setField("marketMaxLeverage",v)}/></div></Block></div>}

function AiStep({form,setField,modes,liveEvalAvailable,onMode}:{form:BacktestFormState;setField:<K extends keyof BacktestFormState>(key:K,value:BacktestFormState[K])=>void;modes:AiMode[];liveEvalAvailable:boolean;onMode:(mode:AiMode)=>void}){return <div className="space-y-5"><Block title="Mode IA" description="LIVE_EVAL appelle le fournisseur IA mais le broker du backtest reste PAPER."><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><label className="text-xs text-slate-400">Mode<select className={`${fieldClass} mt-1 w-full`} value={form.aiMode} onChange={e=>onMode(e.target.value as AiMode)}>{modes.map(mode=><option key={mode} disabled={mode==="LIVE_EVAL"&&!liveEvalAvailable}>{mode}</option>)}</select></label><TextField label="Model ID" value={form.modelId} onChange={v=>setField("modelId",v)}/><label className="text-xs text-slate-400">Reasoning effort<select className={`${fieldClass} mt-1 w-full`} value={form.reasoningEffort} onChange={e=>setField("reasoningEffort",e.target.value as ReasoningEffort)}>{["none","low","medium","high","xhigh","max"].map(v=><option key={v}>{v}</option>)}</select></label><TextField label="Budget IA (€)" value={form.hardBudgetEur} onChange={v=>setField("hardBudgetEur",v)}/></div><div className="mt-3 grid gap-3 md:grid-cols-3"><TextField label="Input €/1M" value={form.inputPrice} onChange={v=>setField("inputPrice",v)}/><TextField label="Output €/1M" value={form.outputPrice} onChange={v=>setField("outputPrice",v)}/><TextField label="Cached input €/1M (optionnel)" value={form.cachedInputPrice} onChange={v=>setField("cachedInputPrice",v)}/></div>{form.aiMode==="MOCK"&&<label className="mt-4 flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={form.mockAgentCoverage} onChange={e=>setField("mockAgentCoverage",e.target.checked)}/> Couvrir les agents avec le provider MOCK déterministe</label>}</Block></div>}

function ExecutionStep({form,setField}:{form:BacktestFormState;setField:<K extends keyof BacktestFormState>(key:K,value:BacktestFormState[K])=>void}){return <div className="space-y-5"><Block title="Capital & modèle d'exécution" description="Ces paramètres sont figés dans le manifeste du run."><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><TextField label="Capital initial" value={form.initialBalance} onChange={v=>setField("initialBalance",v)}/><TextField label="Maker fee (bps)" value={form.makerFeeBps} onChange={v=>setField("makerFeeBps",v)}/><TextField label="Taker fee (bps)" value={form.takerFeeBps} onChange={v=>setField("takerFeeBps",v)}/><TextField label="Slippage marché (bps)" value={form.slippageBps} onChange={v=>setField("slippageBps",v)}/><TextField label="Execution model version" value={form.executionModelVersion} onChange={v=>setField("executionModelVersion",v)}/><TextField label="Random seed" value={form.randomSeed} onChange={v=>setField("randomSeed",v)}/><div className="md:col-span-2"><TextField label="Code version / commit" value={form.codeVersion} onChange={v=>setField("codeVersion",v)} placeholder="git rev-parse HEAD"/></div><TextField label="System ID" value={form.systemId} onChange={v=>setField("systemId",v)}/></div></Block></div>}

function AdvancedDataStep({timeframe,form,setField}:{timeframe:string;form:BacktestFormState;setField:<K extends keyof BacktestFormState>(key:K,value:BacktestFormState[K])=>void}){const supported=["1m","5m","15m"].includes(timeframe);return <div className="space-y-5"><Block title="Historical Derivatives Analytics" description="Entrée optionnelle déjà supportée par le moteur historique. Elle reste désactivée par défaut.">{!supported&&<p className="mb-4 rounded-lg border border-amber-900/50 bg-amber-950/20 p-3 text-xs text-amber-200/80">Le backend exige un timeframe source 1m, 5m ou 15m pour cette fonctionnalité. Dataset actuel : {timeframe}.</p>}<label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" disabled={!supported} checked={form.derivativesEnabled} onChange={e=>setField("derivativesEnabled",e.target.checked)}/> Activer l’archive derivatives historique</label>{form.derivativesEnabled&&<div className="mt-4 grid gap-3 md:grid-cols-[1fr_220px]"><label className="text-xs text-slate-400">CSV derivatives<input type="file" accept=".csv,text/csv" className="mt-2 block w-full text-xs" onChange={async e=>{const file=e.target.files?.[0];if(file)setField("derivativesCsvText",await file.text())}}/></label><TextField label="Max age (secondes)" value={form.derivativesMaxAgeSeconds} onChange={v=>setField("derivativesMaxAgeSeconds",v)}/></div>}</Block><Block title="Denver frozen prior" description="Prior optionnel figé. L’activation OOS_ONLY évite d’injecter le prior dans DESIGN/VALIDATION."><label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" disabled={!supported} checked={form.denverPriorEnabled} onChange={e=>setField("denverPriorEnabled",e.target.checked)}/> Activer un Denver prior figé</label>{form.denverPriorEnabled&&<div className="mt-4 grid gap-3 md:grid-cols-[1fr_220px]"><label className="text-xs text-slate-400">Prior JSON<input type="file" accept=".json,application/json" className="mt-2 block w-full text-xs" onChange={async e=>{const file=e.target.files?.[0];if(file)setField("denverPriorJsonText",await file.text())}}/></label><label className="text-xs text-slate-400">Activation<select className={`${fieldClass} mt-1 w-full`} value={form.denverActivationMode} onChange={e=>setField("denverActivationMode",e.target.value as "OOS_ONLY"|"ALL_PERIODS")}><option value="OOS_ONLY">OOS_ONLY</option><option value="ALL_PERIODS">ALL_PERIODS</option></select></label></div>}</Block></div>}

function WalkForwardStep({form,setField,candleCount}:{form:BacktestFormState;setField:<K extends keyof BacktestFormState>(key:K,value:BacktestFormState[K])=>void;candleCount:number}){const windowSize=Number(form.walkForwardDesignBars||0)+Number(form.walkForwardValidationBars||0)+Number(form.walkForwardOosBars||0);return <div className="space-y-5"><Block title="Walk-Forward V1" description="Le moteur construit des fenêtres glissantes avec une configuration unique figée. Il ne réalise aucune optimisation automatique."><label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={form.walkForwardEnabled} onChange={e=>setField("walkForwardEnabled",e.target.checked)}/> Activer le walk-forward</label><div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4"><TextField label="DESIGN bars" value={form.walkForwardDesignBars} onChange={v=>setField("walkForwardDesignBars",v)}/><TextField label="VALIDATION bars" value={form.walkForwardValidationBars} onChange={v=>setField("walkForwardValidationBars",v)}/><TextField label="OOS bars" value={form.walkForwardOosBars} onChange={v=>setField("walkForwardOosBars",v)}/><TextField label="Step bars" value={form.walkForwardStepBars} onChange={v=>setField("walkForwardStepBars",v)}/></div><p className={`mt-3 text-xs ${form.walkForwardEnabled&&windowSize>candleCount?"text-rose-300":"text-slate-500"}`}>Fenêtre = {windowSize} bars · dataset = {candleCount} bars.</p></Block></div>}

function ReviewStep({preview,indices,form,pending,onLaunch}:{preview:DatasetPreview;indices:SplitIndices;form:BacktestFormState;pending:boolean;onLaunch:()=>void}){const counts={design:indices.design_end-indices.design_start+1,validation:indices.validation_end-indices.validation_start+1,oos:indices.oos_end-indices.oos_start+1};return <div className="space-y-5"><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><MetricCard label="Dataset" value={`${preview.symbol} · ${preview.timeframe}`} detail={`${preview.candle_count} bars · ${preview.dataset_id}`}/><MetricCard label="Splits" value={`${counts.design} / ${counts.validation} / ${counts.oos}`} detail="DESIGN / VALIDATION / OOS"/><MetricCard label="Risk" value={`${form.maxRiskPerTradePct}% / trade`} detail={`DD max ${form.maxDrawdownPct}% · RR ≥ ${form.minExpectedRr}`}/><MetricCard label="IA" value={`${form.aiMode} · ${form.modelId||"—"}`} detail={`budget ${form.hardBudgetEur} € · reasoning ${form.reasoningEffort}`}/><MetricCard label="Capital" value={form.initialBalance} detail={`fees ${form.makerFeeBps}/${form.takerFeeBps} bps · slip ${form.slippageBps}`}/><MetricCard label="Version" value={form.codeVersion||"MANQUANTE"} detail={form.executionModelVersion}/><MetricCard label="Données avancées" value={form.derivativesEnabled||form.denverPriorEnabled?"ACTIVES":"OFF"} detail={`${form.derivativesEnabled?"Derivatives ":""}${form.denverPriorEnabled?`Denver ${form.denverActivationMode}`:""}`.trim()||"Aucun companion input"}/><MetricCard label="Walk-Forward" value={form.walkForwardEnabled?"ACTIF":"DÉSACTIVÉ"} detail={form.walkForwardEnabled?`${form.walkForwardDesignBars}/${form.walkForwardValidationBars}/${form.walkForwardOosBars}, step ${form.walkForwardStepBars}`:"Split principal uniquement"}/><MetricCard label="Broker" value="PAPER" detail="Aucun ordre LIVE"/></div><div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4"><p className="text-sm font-semibold">Avant lancement</p><p className="mt-2 text-xs leading-5 text-slate-500">Le backend revalide toute la configuration. Le Risk Engine n’est pas bypassé. Le dataset, la configuration, les traces et les exports de replay V2 sont persistés côté backend afin de pouvoir rouvrir la campagne après redémarrage.</p><div className="mt-4 flex flex-wrap items-center gap-3"><Button disabled={pending} onClick={onLaunch}>{pending?"Lancement…":"Lancer DESIGN → VALIDATION → OOS"}</Button><StatusBadge value="CONFIGURATION FIGÉE AU LANCEMENT"/></div></div></div>}

function Block({title,description,children}:{title:string;description:string;children:React.ReactNode}){return <div className="rounded-xl border border-slate-800 bg-slate-950/35 p-4"><h3 className="text-sm font-semibold text-slate-200">{title}</h3><p className="mb-4 mt-1 text-xs leading-5 text-slate-500">{description}</p>{children}</div>}
function TextField({label,value,onChange,placeholder}:{label:string;value:string;onChange:(value:string)=>void;placeholder?:string}){return <label className="text-xs text-slate-400">{label}<input className={`${fieldClass} mt-1 w-full`} value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder}/></label>}
function NumberField({label,value,onChange,min,max}:{label:string;value:string;onChange:(value:string)=>void;min:number;max:number}){return <label className="text-[10px] text-slate-500">{label}<input type="number" min={min} max={max} className={`${fieldClass} mt-1 w-full`} value={value} onChange={e=>onChange(e.target.value)}/></label>}
function Metric({label,value}:{label:string;value:string}){return <div><p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p><p className="mt-1 truncate font-mono text-xs text-slate-200" title={value}>{value}</p></div>}
function MetricCard({label,value,detail}:{label:string;value:string;detail:string}){return <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4"><p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p><p className="mt-2 truncate text-sm font-semibold text-slate-200" title={value}>{value}</p><p className="mt-1 truncate text-[10px] text-slate-500" title={detail}>{detail}</p></div>}
