"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  backtestCapabilitiesQuery,
  datasetPreviewQuery,
  datasetsQuery,
  frontendCapabilitiesQuery,
  importLocalCampaignDataset,
  localCampaignDatasetsQuery,
  marketConstraintsQuery,
  openAiModelsQuery,
  saveDatasetFile,
  startBacktestFromDataset
} from "@/lib/api/queries";
import type { DatasetCatalogItem, DatasetPreview, LocalCampaignDataset, OpenAiModel, SplitIndices } from "@/lib/api/schemas";
import {
  buildCampaignConfig,
  canonicalDerivativesIdentity,
  defaultBacktestForm,
  detectHistoricalDatasetIdentity,
  durationPresetSplit,
  fullDatasetSplit,
  HISTORICAL_DATASET_SYMBOLS,
  HISTORICAL_DATASET_TIMEFRAMES,
  historicalMarketPreset,
  initialSplitIndices,
  quickTestSplit,
  type AiMode,
  type BacktestFormState,
  type PositioningMode,
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
  const localCampaignDatasets = useQuery({queryKey:["local-campaign-datasets"],queryFn:localCampaignDatasetsQuery,retry:false});
  const openAiCatalog = useQuery({queryKey:["openai-model-catalog"],queryFn:openAiModelsQuery,staleTime:300000});
  const [tab,setTab]=useState<Tab>("dataset");
  const [datasetFile,setDatasetFile]=useState<File|null>(null);
  const [fileName,setFileName]=useState("");
  const [symbol,setSymbol]=useState("BTC/USDC");
  const [timeframe,setTimeframe]=useState("1h");
  const [selectedDatasetId,setSelectedDatasetId]=useState("");
  const [preview,setPreview]=useState<DatasetPreview|null>(null);
  const [splitIndices,setSplitIndices]=useState<SplitIndices|null>(null);
  const [form,setForm]=useState<BacktestFormState>(()=>defaultBacktestForm());
  const marketSymbol=preview?.symbol??symbol;
  const historicalPreset=historicalMarketPreset(marketSymbol);
  const constraints=useQuery({queryKey:["market-constraints",marketSymbol],queryFn:()=>marketConstraintsQuery(marketSymbol),retry:false,enabled:Boolean(marketSymbol)&&!historicalPreset});

  const setField=<K extends keyof BacktestFormState>(key:K,value:BacktestFormState[K])=>setForm(current=>({...current,[key]:value}));

  useEffect(()=>{
    const systemId=front.data?.default_system_id;
    if(!systemId)return;
    setForm(current=>current.systemId==="balanced_v1"?{...current,systemId}:current);
  },[front.data?.default_system_id]);
  useEffect(()=>{
    const data=constraints.data;
    if(!data)return;
    setForm(current=>({...current,qtyStep:data.qty_step,minQty:data.min_qty,minNotional:data.min_notional,marketMaxLeverage:data.max_leverage,positioningMode:data.positioning_mode}));
  },[constraints.data]);

  useEffect(()=>{
    if(form.aiMode==="MOCK")return;
    const models=openAiCatalog.data?.models??[];
    if(!models.length||models.some(model=>model.model_id===form.modelId))return;
    const selected=models.find(model=>model.recommended)??models[0];
    if(!selected)return;
    setForm(current=>({...current,modelId:selected.model_id,reasoningEffort:selected.default_reasoning_effort}));
  },[form.aiMode,form.modelId,openAiCatalog.data?.models]);

  const selectPreview=(next:DatasetPreview)=>{
    setPreview(next); setSelectedDatasetId(next.dataset_id); setSymbol(next.symbol); setTimeframe(next.timeframe); setSplitIndices(initialSplitIndices(next));
    const preset=historicalMarketPreset(next.symbol);
    if(preset){
      setForm(current=>({...current,qtyStep:preset.qtyStep,minQty:preset.minQty,minNotional:preset.minNotional,maxQty:preset.maxQty,marketMaxLeverage:preset.maxLeverage,positioningMode:preset.positioningMode}));
    }
    if(!["1m","5m","15m"].includes(next.timeframe)) setForm(current=>({...current,derivativesEnabled:false,denverPriorEnabled:false}));
    setTab("periods");
  };
  const saveMutation=useMutation({
    mutationFn:()=>{if(!datasetFile)throw new Error("Sélectionnez un fichier CSV.");return saveDatasetFile(datasetFile,{symbol,timeframe,source:`frontend_v2:${fileName||datasetFile.name||"upload.csv"}`});},
    onSuccess:async next=>{selectPreview(next);await queryClient.invalidateQueries({queryKey:["backtest-datasets"]});}
  });
  const loadDatasetMutation=useMutation({
    mutationFn:(datasetId:string)=>datasetPreviewQuery(datasetId),
    onSuccess:selectPreview
  });
  const importLocalDatasetMutation=useMutation({
    mutationFn:(durationMonths:number)=>importLocalCampaignDataset(durationMonths),
    onSuccess:async next=>{selectPreview(next);await queryClient.invalidateQueries({queryKey:["backtest-datasets"]});}
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
  const changeAiMode=(mode:AiMode)=>setForm(current=>{
    if(mode==="MOCK")return {...current,aiMode:mode,modelId:"mock-backtest-v1",reasoningEffort:"low",mockAgentCoverage:current.mockAgentCoverage};
    const models=openAiCatalog.data?.models??[];
    const selected=models.find(model=>model.model_id===current.modelId)??models.find(model=>model.recommended)??models[0];
    return {...current,aiMode:mode,modelId:selected?.model_id??"",reasoningEffort:selected?.default_reasoning_effort??current.reasoningEffort,mockAgentCoverage:false};
  });
  const launchError=saveMutation.error??loadDatasetMutation.error??importLocalDatasetMutation.error??runMutation.error;

  return <section className="panel overflow-hidden">
    <div className="flex flex-wrap items-center gap-3 border-b border-slate-800 p-5">
      <div><p className="panel-title">Nouvelle campagne</p><h2 className="mt-1 text-xl font-semibold">Backtest Cockpit</h2><p className="mt-1 text-xs text-slate-500">Configuration explicite, figée puis rejouée par le moteur Batch 16.</p></div>
      <div className="ml-auto flex gap-2"><StatusBadge value="PAPER ONLY"/><StatusBadge value={form.aiMode}/></div>
    </div>
    <Tabs value={tab} onValueChange={value=>setTab(value as Tab)}>
      <div className="overflow-x-auto border-b border-slate-800 px-4 py-3"><TabsList className="w-max">
        <TabsTrigger value="dataset">1 · Dataset</TabsTrigger><TabsTrigger value="periods" disabled={!preview}>2 · Périodes</TabsTrigger><TabsTrigger value="risk" disabled={!preview}>3 · Risk</TabsTrigger><TabsTrigger value="ai" disabled={!preview}>4 · IA</TabsTrigger><TabsTrigger value="execution" disabled={!preview}>5 · Exécution</TabsTrigger><TabsTrigger value="advanced" disabled={!preview}>6 · Contexte historique</TabsTrigger><TabsTrigger value="walk-forward" disabled={!preview}>7 · Walk-Forward</TabsTrigger><TabsTrigger value="review" disabled={!preview}>8 · Revue</TabsTrigger>
      </TabsList></div>
      <div className="p-5">
        <TabsContent value="dataset"><DatasetStep datasets={datasets.data??[]} localDatasets={localCampaignDatasets.data??[]} localLoading={localCampaignDatasets.isLoading} localError={localCampaignDatasets.isError} localImporting={importLocalDatasetMutation.isPending} onSelectLocal={months=>importLocalDatasetMutation.mutate(months)} selectedDatasetId={selectedDatasetId} onSelectDataset={id=>{setSelectedDatasetId(id);if(id)loadDatasetMutation.mutate(id);}} datasetLoading={loadDatasetMutation.isPending} datasetFile={datasetFile} setDatasetFile={setDatasetFile} fileName={fileName} setFileName={setFileName} symbol={symbol} setSymbol={value=>{setSymbol(value);setPreview(null);setSelectedDatasetId("");}} timeframe={timeframe} setTimeframe={value=>{setTimeframe(value);setPreview(null);setSelectedDatasetId("");}} symbols={Array.from(new Set([...HISTORICAL_DATASET_SYMBOLS,...(front.data?.market_symbols??[])]))} timeframes={[...HISTORICAL_DATASET_TIMEFRAMES]} savePending={saveMutation.isPending} onSave={()=>saveMutation.mutate()} preview={preview}/></TabsContent>
        <TabsContent value="periods">{preview&&<PeriodsStep preview={preview} indices={splitIndices} setIndices={setSplitIndices}/>}</TabsContent>
        <TabsContent value="risk">{preview&&<RiskStep form={form} setField={setField} constraintsStatus={historicalPreset?"HISTORICAL PRESET":constraints.data?"KRAKEN PUBLIC":constraints.isError?"MANUEL":"CHARGEMENT"}/>}</TabsContent>
        <TabsContent value="ai"><AiStep form={form} setField={setField} modes={(caps.data?.modes??["MOCK","CACHED","LIVE_EVAL"]) as AiMode[]} liveEvalAvailable={caps.data?.live_eval_available??false} onMode={changeAiMode} models={openAiCatalog.data?.models??[]} catalogLoading={openAiCatalog.isLoading} catalogError={openAiCatalog.isError}/></TabsContent>
        <TabsContent value="execution"><ExecutionStep form={form} setField={setField}/></TabsContent>
        <TabsContent value="advanced">{preview&&<AdvancedDataStep symbol={preview.symbol} timeframe={preview.timeframe} form={form} setField={setField}/>}</TabsContent>
        <TabsContent value="walk-forward">{preview&&<WalkForwardStep form={form} setField={setField} candleCount={preview.candle_count}/>}</TabsContent>
        <TabsContent value="review">{preview&&splitIndices&&<ReviewStep preview={preview} indices={splitIndices} form={form} pending={runMutation.isPending} onLaunch={()=>runMutation.mutate()}/>}</TabsContent>
      </div>
    </Tabs>
    {launchError&&<div className="border-t border-rose-900/60 bg-rose-950/20 px-5 py-3 text-sm text-rose-300">{String(launchError.message)}</div>}
  </section>;
}

function DatasetStep({datasets,localDatasets,localLoading,localError,localImporting,onSelectLocal,selectedDatasetId,onSelectDataset,datasetLoading,datasetFile,setDatasetFile,fileName,setFileName,symbol,setSymbol,timeframe,setTimeframe,symbols,timeframes,savePending,onSave,preview}:{datasets:DatasetCatalogItem[];localDatasets:LocalCampaignDataset[];localLoading:boolean;localError:boolean;localImporting:boolean;onSelectLocal:(months:number)=>void;selectedDatasetId:string;onSelectDataset:(id:string)=>void;datasetLoading:boolean;datasetFile:File|null;setDatasetFile:(v:File|null)=>void;fileName:string;setFileName:(v:string)=>void;symbol:string;setSymbol:(v:string)=>void;timeframe:string;setTimeframe:(v:string)=>void;symbols:string[];timeframes:string[];savePending:boolean;onSave:()=>void;preview:DatasetPreview|null}){
 return <div className="space-y-5"><div className="grid gap-4 xl:grid-cols-3"><Block title="Datasets locaux de campagne" description="Préfixes 1m canoniques générés sous data/. Le backend vérifie le manifeste et le SHA-256 avant de les enregistrer dans la bibliothèque V2.">{localLoading?<p className="text-xs text-slate-500">Lecture du manifeste local…</p>:localError?<p className="text-xs text-rose-300">Manifeste local invalide ou illisible.</p>:localDatasets.length===0?<p className="text-xs leading-5 text-slate-600">Aucun dataset local détecté. Exécute build_campaign_prefix_datasets.py depuis la racine du projet.</p>:<div className="grid grid-cols-2 gap-2 sm:grid-cols-5 xl:grid-cols-2">{localDatasets.map(item=><Button key={item.duration_months} size="sm" variant="secondary" disabled={!item.available||localImporting} onClick={()=>onSelectLocal(item.duration_months)}>{item.duration_months} mois</Button>)}</div>}{localDatasets.length>0&&<div className="mt-3 space-y-1 text-[10px] text-slate-600">{localDatasets.map(item=><p key={item.duration_months}>{item.duration_months}m · {item.rows.toLocaleString("fr-FR")} bars · {item.dataset_start_utc} → {item.dataset_end_utc_inclusive} · {item.available?"disponible":"fichier absent"}</p>)}</div>}{localImporting&&<p className="mt-3 text-xs text-violet-300">Validation et enregistrement du dataset local…</p>}</Block><Block title="Réutiliser un dataset" description="Les datasets déjà validés par Frontend V2 sont persistés côté backend."><label className="text-xs text-slate-400">Dataset enregistré<select className={`${fieldClass} mt-1 w-full`} value={selectedDatasetId} onChange={e=>onSelectDataset(e.target.value)}><option value="">— sélectionner —</option>{datasets.map(item=><option key={item.dataset_id} value={item.dataset_id}>{item.symbol} · {item.timeframe} · {item.candle_count} bars · {item.start_at.slice(0,10)} → {item.end_at.slice(0,10)}</option>)}</select></label>{datasetLoading&&<p className="mt-3 text-xs text-slate-500">Chargement des bornes du dataset…</p>}{datasets.length===0&&<p className="mt-3 text-xs text-slate-600">Aucun dataset V2 enregistré pour le moment.</p>}</Block>
 <Block title="Importer un nouveau CSV" description="Upload brut vers le backend : le navigateur ne convertit plus les gros datasets en JSON. Les fichiers 1m de plusieurs dizaines de Mo sont supportés."><div className="grid gap-3 sm:grid-cols-2"><label className="text-xs text-slate-400">Symbol<input list="backtest-symbols" className={`${fieldClass} mt-1 w-full`} value={symbol} onChange={e=>setSymbol(e.target.value.toUpperCase())} placeholder="BTC/USDC"/><datalist id="backtest-symbols">{symbols.map(value=><option key={value} value={value}/>)}</datalist></label><label className="text-xs text-slate-400">Timeframe<select className={`${fieldClass} mt-1 w-full`} value={timeframe} onChange={e=>setTimeframe(e.target.value)}>{timeframes.map(value=><option key={value}>{value}</option>)}</select></label></div><label className="mt-3 block text-xs text-slate-400">Fichier CSV<input type="file" accept=".csv,text/csv" className="mt-2 block w-full text-xs" onChange={e=>{const file=e.target.files?.[0]??null;setDatasetFile(file);setFileName(file?.name??"");if(file){const detected=detectHistoricalDatasetIdentity(file.name);if(detected.symbol)setSymbol(detected.symbol);if(detected.timeframe)setTimeframe(detected.timeframe);}}}/></label><div className="mt-2 text-[11px] text-slate-500">{datasetFile?`PRÊT · ${datasetFile.name} · ${(datasetFile.size/1024/1024).toFixed(1)} Mo`:"Aucun fichier sélectionné — le bouton reste disponible pour afficher une erreur explicite."} · La limite opérateur 25 Mo a été supprimée.</div><div className="mt-4 flex items-center gap-3"><Button variant="secondary" disabled={savePending} onClick={onSave}>{savePending?"Upload & validation…":"Valider & enregistrer"}</Button>{fileName&&<span className="text-xs text-slate-500">{fileName}</span>}</div></Block></div>{preview&&<DatasetSummary preview={preview}/>}</div>
}

function DatasetSummary({preview}:{preview:DatasetPreview}){return <div className="grid gap-3 rounded-lg border border-slate-800 bg-slate-950/60 p-4 sm:grid-cols-2 xl:grid-cols-6"><Metric label="Dataset" value={preview.dataset_id}/><Metric label="Symbol / TF" value={`${preview.symbol} · ${preview.timeframe}`}/><Metric label="Bougies" value={String(preview.candle_count)}/><Metric label="Période" value={`${preview.start_at.slice(0,10)} → ${preview.end_at.slice(0,10)}`}/><Metric label="Qualité" value={preview.is_valid?`VALID · ${preview.gap_count} gaps`:"INVALID"}/><Metric label="SHA-256" value={preview.content_sha256.slice(0,16)}/></div>}

function PeriodsStep({preview,indices,setIndices}:{preview:DatasetPreview;indices:SplitIndices|null;setIndices:(value:SplitIndices)=>void}){
 const [presetError,setPresetError]=useState("");
 if(!indices)return <p className="text-sm text-amber-200">Le backend n’a pas fourni assez d’information pour découper ce dataset.</p>;
 const applyPreset=(factory:()=>SplitIndices)=>{try{setIndices(factory());setPresetError("");}catch(error){setPresetError(error instanceof Error?error.message:String(error));}};
 const update=(key:keyof SplitIndices,value:string)=>{setPresetError("");setIndices({...indices,[key]:Number(value)});};
 const count=(start:number,end:number)=>Math.max(0,end-start+1);
 return <div className="space-y-5"><Block title="DESIGN / VALIDATION / OOS" description="Raccourcis opérateur hérités de l’ancien cockpit. Les presets calendaires utilisent les timestamps réels du dataset puis répartissent la fenêtre en 60 / 20 / 20."><div className="mb-5 flex flex-wrap gap-2"><Button size="sm" variant="secondary" onClick={()=>applyPreset(()=>quickTestSplit(preview))}>Test rapide</Button><Button size="sm" variant="secondary" onClick={()=>applyPreset(()=>durationPresetSplit(preview,30))}>1 mois</Button><Button size="sm" variant="secondary" onClick={()=>applyPreset(()=>durationPresetSplit(preview,90))}>3 mois</Button><Button size="sm" variant="secondary" onClick={()=>applyPreset(()=>durationPresetSplit(preview,365))}>1 an</Button><Button size="sm" variant="secondary" onClick={()=>applyPreset(()=>fullDatasetSplit(preview))}>Tout le dataset</Button><Button size="sm" variant="ghost" onClick={()=>applyPreset(()=>{const reset=initialSplitIndices(preview);if(!reset)throw new Error("Impossible de calculer le split 60 / 20 / 20 pour ce dataset.");return reset;})}>Réinitialiser 60 / 20 / 20</Button></div>{presetError&&<p className="mb-4 rounded-lg border border-rose-900/50 bg-rose-950/20 p-3 text-xs text-rose-300">{presetError}</p>}<div className="mb-4 rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-[11px] leading-5 text-slate-500"><span className="font-semibold text-slate-300">Test rapide</span> : 35 bougies de warm-up puis 100 bougies max. <span className="font-semibold text-slate-300">1 mois / 3 mois / 1 an</span> : 30 / 90 / 365 jours calendaires après le warm-up, avec clamp automatique à l’historique disponible.</div><div className="grid gap-4 lg:grid-cols-3"><PeriodCard title="DESIGN" start={indices.design_start} end={indices.design_end} max={preview.candle_count-1} onStart={v=>update("design_start",v)} onEnd={v=>update("design_end",v)} count={count(indices.design_start,indices.design_end)} preview={preview}/><PeriodCard title="VALIDATION" start={indices.validation_start} end={indices.validation_end} max={preview.candle_count-1} onStart={v=>update("validation_start",v)} onEnd={v=>update("validation_end",v)} count={count(indices.validation_start,indices.validation_end)} preview={preview}/><PeriodCard title="OOS · OUT-OF-SAMPLE" start={indices.oos_start} end={indices.oos_end} max={preview.candle_count-1} onStart={v=>update("oos_start",v)} onEnd={v=>update("oos_end",v)} count={count(indices.oos_start,indices.oos_end)} preview={preview}/></div></Block><p className="rounded-lg border border-amber-900/50 bg-amber-950/20 p-3 text-xs leading-5 text-amber-200/80">OOS doit rester hors échantillon : évite d’ajuster la stratégie après avoir consulté ses résultats. Le moteur conserve les rapports DESIGN, VALIDATION et OOS séparés.</p></div>
}

function PeriodCard({title,start,end,max,onStart,onEnd,count,preview}:{title:string;start:number;end:number;max:number;onStart:(v:string)=>void;onEnd:(v:string)=>void;count:number;preview:DatasetPreview}){const at=(index:number)=>preview.candle_close_ms[index]?new Date(preview.candle_close_ms[index]).toISOString():"—";return <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4"><div className="flex items-center justify-between"><p className="text-xs font-semibold text-slate-200">{title}</p><span className="text-[10px] text-slate-500">{count} bars</span></div><div className="mt-3 grid grid-cols-2 gap-2"><NumberField label="Start index" value={String(start)} min={0} max={max} onChange={onStart}/><NumberField label="End index" value={String(end)} min={0} max={max} onChange={onEnd}/></div><p className="mt-3 break-all font-mono text-[10px] text-slate-600">{at(start)}<br/>→ {at(end)}</p></div>}

function RiskStep({form,setField,constraintsStatus}:{form:BacktestFormState;setField:<K extends keyof BacktestFormState>(key:K,value:BacktestFormState[K])=>void;constraintsStatus:string}){return <div className="space-y-5"><Block title="Profil de risque" description="Valeurs en pourcentage côté interface ; elles sont converties en fractions avant envoi au Risk Engine."><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><TextField label="Risk profile ID" value={form.riskProfileId} onChange={v=>setField("riskProfileId",v)}/><TextField label="Risk version" value={form.riskVersion} onChange={v=>setField("riskVersion",v)}/><TextField label="Risque / trade (%)" value={form.maxRiskPerTradePct} onChange={v=>setField("maxRiskPerTradePct",v)}/><TextField label="Perte journalière max (%)" value={form.maxDailyLossPct} onChange={v=>setField("maxDailyLossPct",v)}/><TextField label="Drawdown max (%)" value={form.maxDrawdownPct} onChange={v=>setField("maxDrawdownPct",v)}/><TextField label="Portfolio risk max (%)" value={form.maxPortfolioRiskPct} onChange={v=>setField("maxPortfolioRiskPct",v)}/><TextField label="Exposition corrélée max (%)" value={form.maxCorrelatedExposurePct} onChange={v=>setField("maxCorrelatedExposurePct",v)}/><TextField label="Max positions" value={form.maxPositions} onChange={v=>setField("maxPositions",v)}/><TextField label="Max leverage Risk" value={form.riskMaxLeverage} onChange={v=>setField("riskMaxLeverage",v)}/><TextField label="RR minimum" value={form.minExpectedRr} onChange={v=>setField("minExpectedRr",v)}/></div></Block><Block title="Contraintes marché" description="La capacité directionnelle est une entrée matérielle du run. SPOT_LONG_ONLY interdit toute ouverture nette SHORT mais autorise toujours les ventes qui réduisent ou clôturent un LONG existant."><div className="mb-3 flex flex-wrap items-center gap-2"><StatusBadge value={constraintsStatus}/><StatusBadge value={form.positioningMode==="SPOT_LONG_ONLY"?"SPOT · LONG ONLY":"LONG + SHORT"}/></div><div className="mb-4 grid gap-3 md:grid-cols-2"><label className="text-xs text-slate-400">Positionnement<select className={`${fieldClass} mt-1 w-full`} value={form.positioningMode} onChange={e=>setField("positioningMode",e.target.value as PositioningMode)}><option value="SPOT_LONG_ONLY">Spot · LONG only</option><option value="LONG_SHORT">Dérivés / simulation · LONG + SHORT</option></select></label><div className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-[11px] leading-5 text-slate-500">{form.positioningMode==="SPOT_LONG_ONLY"?"Le Professor ne peut proposer que LONG ou NO_TRADE. Le Risk Engine et le PaperBroker bloquent aussi toute entrée SHORT.":"Les entrées LONG et SHORT sont autorisées. À utiliser uniquement pour un marché dont le contrat le permet."}</div></div><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5"><TextField label="qty_step" value={form.qtyStep} onChange={v=>setField("qtyStep",v)}/><TextField label="min_qty" value={form.minQty} onChange={v=>setField("minQty",v)}/><TextField label="min_notional" value={form.minNotional} onChange={v=>setField("minNotional",v)}/><TextField label="max_qty (optionnel)" value={form.maxQty} onChange={v=>setField("maxQty",v)}/><TextField label="max_leverage" value={form.marketMaxLeverage} onChange={v=>setField("marketMaxLeverage",v)}/></div></Block></div>}

function AiStep({form,setField,modes,liveEvalAvailable,onMode,models,catalogLoading,catalogError}:{form:BacktestFormState;setField:<K extends keyof BacktestFormState>(key:K,value:BacktestFormState[K])=>void;modes:AiMode[];liveEvalAvailable:boolean;onMode:(mode:AiMode)=>void;models:OpenAiModel[];catalogLoading:boolean;catalogError:boolean}){
 const selectedModel=models.find(model=>model.model_id===form.modelId)??null;
 const reasoningOptions=form.aiMode==="MOCK"?["none","low","medium","high","xhigh","max"] as ReasoningEffort[]:(selectedModel?.reasoning_efforts??[]);
 const selectModel=(modelId:string)=>{const model=models.find(item=>item.model_id===modelId);setField("modelId",modelId);if(model&&!model.reasoning_efforts.includes(form.reasoningEffort))setField("reasoningEffort",model.default_reasoning_effort)};
 return <div className="space-y-5"><Block title="Mode IA" description="LIVE_EVAL appelle OpenAI mais le broker du backtest reste PAPER. Les tarifs sont fournis par le backend Money Heist depuis un snapshot vérifié de la tarification officielle OpenAI."><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><label className="text-xs text-slate-400">Mode<select className={`${fieldClass} mt-1 w-full`} value={form.aiMode} onChange={e=>onMode(e.target.value as AiMode)}>{modes.map(mode=><option key={mode} disabled={mode==="LIVE_EVAL"&&!liveEvalAvailable}>{mode}</option>)}</select></label>{form.aiMode==="MOCK"?<div className="rounded-md border border-slate-800 bg-slate-950 px-3 py-2"><p className="text-[10px] uppercase tracking-wider text-slate-600">Model ID</p><p className="mt-1 font-mono text-sm text-slate-300">{form.modelId}</p></div>:<label className="text-xs text-slate-400">Model ID<select className={`${fieldClass} mt-1 w-full`} value={form.modelId} onChange={e=>selectModel(e.target.value)} disabled={catalogLoading||catalogError||models.length===0}><option value="">— sélectionner —</option>{models.map(model=><option key={model.model_id} value={model.model_id}>{model.display_name} · {model.model_id}{model.recommended?" · recommandé":""}</option>)}</select></label>}<label className="text-xs text-slate-400">Reasoning effort<select className={`${fieldClass} mt-1 w-full`} value={form.reasoningEffort} onChange={e=>setField("reasoningEffort",e.target.value as ReasoningEffort)} disabled={form.aiMode!=="MOCK"&&!selectedModel}>{reasoningOptions.map(value=><option key={value}>{value}</option>)}</select></label><TextField label="Budget IA (USD)" value={form.hardBudgetUsd} onChange={value=>setField("hardBudgetUsd",value)}/></div>{form.aiMode!=="MOCK"&&<div className="mt-5 space-y-3">{catalogLoading&&<p className="text-xs text-slate-500">Chargement du catalogue OpenAI…</p>}{catalogError&&<p className="rounded-lg border border-rose-900/50 bg-rose-950/20 p-3 text-xs text-rose-300">Catalogue OpenAI indisponible. LIVE_EVAL reste bloqué tant que les tarifs vérifiés ne sont pas disponibles.</p>}{selectedModel&&<><div className="grid gap-3 md:grid-cols-3"><PriceCard label="Input / 1M tokens" value={`$${selectedModel.input_per_million_usd}`}/><PriceCard label="Cached input / 1M" value={`$${selectedModel.cached_input_per_million_usd}`}/><PriceCard label="Output / 1M tokens" value={`$${selectedModel.output_per_million_usd}`}/></div><div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-500"><StatusBadge value="USD"/><StatusBadge value={selectedModel.pricing_tier}/><span>Source: OpenAI officielle · snapshot {selectedModel.pricing_snapshot_at}</span><span>· contexte standard &lt; {Math.round(selectedModel.standard_context_max_tokens/1000)}K tokens</span></div>{selectedModel.pricing_valid_until&&<p className="rounded-lg border border-amber-900/40 bg-amber-950/20 p-3 text-xs text-amber-200/80">Tarif promotionnel annoncé au moins jusqu’au {new Date(`${selectedModel.pricing_valid_until}T00:00:00Z`).toLocaleDateString("fr-FR")}.</p>}{selectedModel.notes.filter(note=>!note.toLowerCase().includes("promotionnelle")).map(note=><p key={note} className="text-[10px] text-slate-600">{note}</p>)}</>}</div>}{form.aiMode==="MOCK"&&<label className="mt-4 flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={form.mockAgentCoverage} onChange={e=>setField("mockAgentCoverage",e.target.checked)}/> Couvrir les agents avec le provider MOCK déterministe</label>}</Block></div>
}

function PriceCard({label,value}:{label:string;value:string}){return <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4"><p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p><p className="mt-2 font-mono text-lg font-semibold text-slate-200">{value}</p><p className="mt-1 text-[10px] text-slate-600">Lecture seule · catalogue backend</p></div>}

function ExecutionStep({form,setField}:{form:BacktestFormState;setField:<K extends keyof BacktestFormState>(key:K,value:BacktestFormState[K])=>void}){return <div className="space-y-5"><Block title="Capital & modèle d'exécution" description="Ces paramètres sont figés dans le manifeste du run."><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><TextField label="Capital initial" value={form.initialBalance} onChange={v=>setField("initialBalance",v)}/><TextField label="Maker fee (bps)" value={form.makerFeeBps} onChange={v=>setField("makerFeeBps",v)}/><TextField label="Taker fee (bps)" value={form.takerFeeBps} onChange={v=>setField("takerFeeBps",v)}/><TextField label="Slippage marché (bps)" value={form.slippageBps} onChange={v=>setField("slippageBps",v)}/><TextField label="Execution model version" value={form.executionModelVersion} onChange={v=>setField("executionModelVersion",v)}/><TextField label="Random seed" value={form.randomSeed} onChange={v=>setField("randomSeed",v)}/><div className="md:col-span-2"><TextField label="Code version / commit" value={form.codeVersion} onChange={v=>setField("codeVersion",v)} placeholder="git rev-parse HEAD"/></div><TextField label="System ID" value={form.systemId} onChange={v=>setField("systemId",v)}/></div></Block></div>}

function AdvancedDataStep({symbol,timeframe,form,setField}:{symbol:string;timeframe:string;form:BacktestFormState;setField:<K extends keyof BacktestFormState>(key:K,value:BacktestFormState[K])=>void}){
 const mtfSupported=["1m","5m","15m"].includes(timeframe);
 const [derivativesFileName,setDerivativesFileName]=useState("");
 const [denverFileName,setDenverFileName]=useState("");
 const mtfState=(target:"15m"|"1h"|"4h"|"1d")=>{
   if(timeframe===target)return "NATIF";
   if(mtfSupported)return "CONSTRUIT";
   return "INDISPONIBLE";
 };
 const rioIdentity=canonicalDerivativesIdentity(form.derivativesCsvText);
 const rioSymbolMatches=!rioIdentity||rioIdentity.symbol===symbol.trim().toUpperCase();
 const rioReady=mtfSupported&&form.derivativesEnabled&&Boolean(form.derivativesCsvText.trim())&&rioSymbolMatches;
 const denverReady=mtfSupported&&form.denverPriorEnabled&&Boolean(form.denverPriorJsonText.trim());
 return <div className="space-y-5">
  <Block title="Contexte historique fourni au moteur" description="Cet écran n’ajoute aucune logique de trading dans le navigateur. Il montre quelles données le Historical Replay pourra réellement fournir au Scanner et aux agents.">
   <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
    <ContextCard label="Dataset source" value={timeframe} detail="OHLCV historique"/>
    <ContextCard label="Decision timeframe" value={mtfSupported?"1h":timeframe} detail={mtfSupported?"runtime MTF historique":"source native / legacy"}/>
    <ContextCard label="MTF Runtime" value={mtfSupported?"ACTIF":"INACTIF"} detail={mtfSupported?"15m · 1h · 4h · 1d":"source trop grossière pour reconstruire le 15m"}/>
    <ContextCard label="Données enrichies" value={(rioReady||denverReady)?"PARTIEL / ACTIF":"OPTIONNEL"} detail={`Rio ${rioReady?"✓":"✕"} · Denver ${denverReady?"✓":"✕"}`}/>
   </div>
   <div className="mt-4 grid gap-2 sm:grid-cols-4">
    {(["15m","1h","4h","1d"] as const).map(target=><div key={target} className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2"><div className="flex items-center justify-between gap-2"><span className="font-mono text-xs text-slate-300">{target}</span><StatusBadge value={mtfState(target)}/></div></div>)}
   </div>
   {!mtfSupported&&<p className="mt-4 rounded-lg border border-amber-900/50 bg-amber-950/20 p-3 text-xs leading-5 text-amber-200/80">Dataset source <strong>{timeframe}</strong> : Money Heist ne fabrique pas artificiellement un 15m à partir d’une source plus grossière. Pour le contexte MTF complet et l’activation Rio / Denver historique, charge une source 1m, 5m ou 15m.</p>}
  </Block>

  <Block title="Rio · marché dérivés" description="Ajoute au contexte historique les données Kraken Derivatives disponibles au moment de chaque décision : funding, open interest, variation d’open interest et long/short ratio.">
   <div className="flex flex-wrap items-center gap-3"><StatusBadge value={!mtfSupported?"INDISPONIBLE":!rioSymbolMatches?"SYMBOL MISMATCH":rioReady?"PRÊT":form.derivativesEnabled?"ARCHIVE REQUISE":"DÉSACTIVÉ"}/><span className="text-xs text-slate-500">Optionnel · désactivé par défaut.</span></div>
   {rioIdentity&&<p className={`mt-3 rounded-lg border p-3 text-xs ${rioSymbolMatches?"border-emerald-900/50 bg-emerald-950/20 text-emerald-200":"border-rose-900/60 bg-rose-950/30 text-rose-200"}`}>Archive Rio: <strong>{rioIdentity.symbol}</strong> · {rioIdentity.instrument} · Dataset: <strong>{symbol}</strong>{rioSymbolMatches?" · compatible":" · incompatible"}</p>}
   <label className="mt-4 flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" disabled={!mtfSupported} checked={form.derivativesEnabled} onChange={e=>setField("derivativesEnabled",e.target.checked)}/> Activer Rio historique</label>
   {form.derivativesEnabled&&<div className="mt-4 grid gap-3 md:grid-cols-[1fr_220px]"><label className="text-xs text-slate-400">Archive CSV dérivés canonique<input type="file" accept=".csv,text/csv" className="mt-2 block w-full text-xs" onChange={async e=>{const file=e.target.files?.[0];if(file){setDerivativesFileName(file.name);setField("derivativesCsvText",await file.text())}}}/>{derivativesFileName&&<span className="mt-1 block text-[10px] text-slate-600">{derivativesFileName}</span>}</label><TextField label="Fraîcheur max (secondes)" value={form.derivativesMaxAgeSeconds} onChange={v=>setField("derivativesMaxAgeSeconds",v)}/></div>}
  </Block>

  <Block title="Denver · mémoire statistique historique" description="Charge un prior statistique figé provenant d’une campagne antérieure. OOS_ONLY est recommandé afin de ne pas réinjecter cette mémoire dans DESIGN / VALIDATION.">
   <div className="flex flex-wrap items-center gap-3"><StatusBadge value={!mtfSupported?"INDISPONIBLE":denverReady?"PRÊT":form.denverPriorEnabled?"PRIOR REQUIS":"DÉSACTIVÉ"}/><span className="text-xs text-slate-500">Prior figé · aucune découverte automatique sur disque.</span></div>
   <label className="mt-4 flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" disabled={!mtfSupported} checked={form.denverPriorEnabled} onChange={e=>setField("denverPriorEnabled",e.target.checked)}/> Activer un prior Denver figé</label>
   {form.denverPriorEnabled&&<div className="mt-4 grid gap-3 md:grid-cols-[1fr_220px]"><label className="text-xs text-slate-400">Prior Denver JSON<input type="file" accept=".json,application/json" className="mt-2 block w-full text-xs" onChange={async e=>{const file=e.target.files?.[0];if(file){setDenverFileName(file.name);setField("denverPriorJsonText",await file.text())}}}/>{denverFileName&&<span className="mt-1 block text-[10px] text-slate-600">{denverFileName}</span>}</label><label className="text-xs text-slate-400">Activation<select className={`${fieldClass} mt-1 w-full`} value={form.denverActivationMode} onChange={e=>setField("denverActivationMode",e.target.value as "OOS_ONLY"|"ALL_PERIODS")}><option value="OOS_ONLY">OOS seulement · recommandé</option><option value="ALL_PERIODS">Toutes les périodes</option></select></label></div>}
  </Block>

  <Block title="Couverture du contexte décisionnel" description="Résumé opérateur de ce qui sera disponible pendant le replay. Le backend reste l’autorité sur le contenu exact envoyé à chaque agent.">
   <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
    <CoverageRow label="OHLCV source" enabled/>
    <CoverageRow label="Features techniques" enabled/>
    <CoverageRow label="Multi-timeframe 15m / 1h / 4h / 1d" enabled={mtfSupported}/>
    <CoverageRow label="Rio · dérivés" enabled={rioReady}/>
    <CoverageRow label="Denver · prior historique" enabled={denverReady}/>
    <CoverageRow label="Historical Replay / Risk Engine" enabled/>
   </div>
  </Block>
 </div>
}

function ContextCard({label,value,detail}:{label:string;value:string;detail:string}){return <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p><p className="mt-1 text-sm font-semibold text-slate-200">{value}</p><p className="mt-1 text-[10px] text-slate-600">{detail}</p></div>}
function CoverageRow({label,enabled}:{label:string;enabled:boolean}){return <div className="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-950/50 px-3 py-2 text-xs"><span className={enabled?"text-emerald-300":"text-slate-600"}>{enabled?"✓":"✕"}</span><span className={enabled?"text-slate-300":"text-slate-600"}>{label}</span></div>}

function WalkForwardStep({form,setField,candleCount}:{form:BacktestFormState;setField:<K extends keyof BacktestFormState>(key:K,value:BacktestFormState[K])=>void;candleCount:number}){const windowSize=Number(form.walkForwardDesignBars||0)+Number(form.walkForwardValidationBars||0)+Number(form.walkForwardOosBars||0);return <div className="space-y-5"><Block title="Walk-Forward V1" description="Le moteur construit des fenêtres glissantes avec une configuration unique figée. Il ne réalise aucune optimisation automatique."><label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={form.walkForwardEnabled} onChange={e=>setField("walkForwardEnabled",e.target.checked)}/> Activer le walk-forward</label><div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4"><TextField label="DESIGN bars" value={form.walkForwardDesignBars} onChange={v=>setField("walkForwardDesignBars",v)}/><TextField label="VALIDATION bars" value={form.walkForwardValidationBars} onChange={v=>setField("walkForwardValidationBars",v)}/><TextField label="OOS bars" value={form.walkForwardOosBars} onChange={v=>setField("walkForwardOosBars",v)}/><TextField label="Step bars" value={form.walkForwardStepBars} onChange={v=>setField("walkForwardStepBars",v)}/></div><p className={`mt-3 text-xs ${form.walkForwardEnabled&&windowSize>candleCount?"text-rose-300":"text-slate-500"}`}>Fenêtre = {windowSize} bars · dataset = {candleCount} bars.</p></Block></div>}

function ReviewStep({preview,indices,form,pending,onLaunch}:{preview:DatasetPreview;indices:SplitIndices;form:BacktestFormState;pending:boolean;onLaunch:()=>void}){const counts={design:indices.design_end-indices.design_start+1,validation:indices.validation_end-indices.validation_start+1,oos:indices.oos_end-indices.oos_start+1};return <div className="space-y-5"><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><MetricCard label="Dataset" value={`${preview.symbol} · ${preview.timeframe}`} detail={`${preview.candle_count} bars · ${preview.dataset_id}`}/><MetricCard label="Splits" value={`${counts.design} / ${counts.validation} / ${counts.oos}`} detail="DESIGN / VALIDATION / OOS"/><MetricCard label="Risk" value={`${form.maxRiskPerTradePct}% / trade`} detail={`DD max ${form.maxDrawdownPct}% · RR ≥ ${form.minExpectedRr}`}/><MetricCard label="Positionnement" value={form.positioningMode==="SPOT_LONG_ONLY"?"SPOT · LONG ONLY":"LONG + SHORT"} detail={form.positioningMode==="SPOT_LONG_ONLY"?"Aucune entrée SHORT nette":"SHORT explicitement autorisé"}/><MetricCard label="IA" value={`${form.aiMode} · ${form.modelId||"—"}`} detail={`budget $${form.hardBudgetUsd} · reasoning ${form.reasoningEffort}`}/><MetricCard label="Capital" value={form.initialBalance} detail={`fees ${form.makerFeeBps}/${form.takerFeeBps} bps · slip ${form.slippageBps}`}/><MetricCard label="Version" value={form.codeVersion||"MANQUANTE"} detail={form.executionModelVersion}/><MetricCard label="Données avancées" value={form.derivativesEnabled||form.denverPriorEnabled?"ACTIVES":"OFF"} detail={`${form.derivativesEnabled?"Derivatives ":""}${form.denverPriorEnabled?`Denver ${form.denverActivationMode}`:""}`.trim()||"Aucun companion input"}/><MetricCard label="Walk-Forward" value={form.walkForwardEnabled?"ACTIF":"DÉSACTIVÉ"} detail={form.walkForwardEnabled?`${form.walkForwardDesignBars}/${form.walkForwardValidationBars}/${form.walkForwardOosBars}, step ${form.walkForwardStepBars}`:"Split principal uniquement"}/><MetricCard label="Broker" value="PAPER" detail="Aucun ordre LIVE"/></div><div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4"><p className="text-sm font-semibold">Avant lancement</p><p className="mt-2 text-xs leading-5 text-slate-500">Le backend revalide toute la configuration. Le Risk Engine n’est pas bypassé. Le dataset, la configuration, les traces et les exports de replay V2 sont persistés côté backend afin de pouvoir rouvrir la campagne après redémarrage.</p><div className="mt-4 flex flex-wrap items-center gap-3"><Button disabled={pending} onClick={onLaunch}>{pending?"Lancement…":"Lancer DESIGN → VALIDATION → OOS"}</Button><StatusBadge value="CONFIGURATION FIGÉE AU LANCEMENT"/></div></div></div>}

function Block({title,description,children}:{title:string;description:string;children:React.ReactNode}){return <div className="rounded-xl border border-slate-800 bg-slate-950/35 p-4"><h3 className="text-sm font-semibold text-slate-200">{title}</h3><p className="mb-4 mt-1 text-xs leading-5 text-slate-500">{description}</p>{children}</div>}
function TextField({label,value,onChange,placeholder}:{label:string;value:string;onChange:(value:string)=>void;placeholder?:string}){return <label className="text-xs text-slate-400">{label}<input className={`${fieldClass} mt-1 w-full`} value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder}/></label>}
function NumberField({label,value,onChange,min,max}:{label:string;value:string;onChange:(value:string)=>void;min:number;max:number}){return <label className="text-[10px] text-slate-500">{label}<input type="number" min={min} max={max} className={`${fieldClass} mt-1 w-full`} value={value} onChange={e=>onChange(e.target.value)}/></label>}
function Metric({label,value}:{label:string;value:string}){return <div><p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p><p className="mt-1 truncate font-mono text-xs text-slate-200" title={value}>{value}</p></div>}
function MetricCard({label,value,detail}:{label:string;value:string;detail:string}){return <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4"><p className="text-[10px] uppercase tracking-wider text-slate-600">{label}</p><p className="mt-2 truncate text-sm font-semibold text-slate-200" title={value}>{value}</p><p className="mt-1 truncate text-[10px] text-slate-500" title={detail}>{detail}</p></div>}
