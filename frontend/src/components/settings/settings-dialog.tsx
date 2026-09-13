"use client";
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { frontendCapabilitiesQuery, backtestCapabilitiesQuery } from "@/lib/api/queries";
import { useUiStore } from "@/lib/ui-store";
import { StatusBadge } from "@/components/ui/badge";

const SETTINGS_TABS = [
  ["general", "Général"],
  ["market", "Marché"],
  ["trading", "Trading"],
  ["agents", "Agents / IA"],
  ["risk", "Risque"],
  ["backtest", "Backtest"],
  ["interface", "Interface"],
] as const;

function Row({label, value}: {label: string; value: React.ReactNode}) { return <div className="flex items-center justify-between gap-4 border-b border-slate-800/70 py-3 text-sm"><span className="text-slate-400">{label}</span><span className="text-right font-mono text-slate-200">{value}</span></div>; }
export function SettingsDialog() {
  const open = useUiStore(s => s.settingsOpen); const setOpen = useUiStore(s => s.setSettingsOpen);
  const caps = useQuery({queryKey: ["frontend-capabilities"], queryFn: frontendCapabilitiesQuery});
  const backtest = useQuery({queryKey: ["backtest-capabilities"], queryFn: backtestCapabilitiesQuery});
  return <Dialog open={open} onOpenChange={setOpen}><DialogContent>
    <div className="border-b border-slate-800 px-6 py-5"><DialogTitle className="text-lg font-semibold">Réglages Money Heist</DialogTitle><p className="mt-1 text-sm text-slate-500">Les réglages sans API backend d’écriture restent en lecture seule.</p></div>
    <Tabs defaultValue="general" className="grid max-h-[75vh] grid-cols-[190px_1fr] overflow-hidden">
      <TabsList className="m-4 flex-col items-stretch justify-start border-0 bg-transparent">
        {SETTINGS_TABS.map(([v,l]) => <TabsTrigger key={v} value={v} className="justify-start">{l}</TabsTrigger>)}
      </TabsList>
      <div className="scrollbar-thin overflow-y-auto border-l border-slate-800 p-6">
        <TabsContent value="general"><h3 className="mb-4 font-semibold">Runtime</h3><Row label="Mode backend" value={<StatusBadge value={caps.data?.runtime_mode ?? "UNKNOWN"}/>} /><Row label="Environnement" value={caps.data?.app_env ?? "—"}/><Row label="Temps réel" value={caps.data?.realtime_transport ?? "—"}/><Row label="Contrôles LIVE HTTP" value={caps.data?.live_controls_exposed ? "Exposés" : "Non exposés"}/></TabsContent>
        <TabsContent value="market"><h3 className="mb-4 font-semibold">Marché</h3><Row label="Symboles backend" value={caps.data?.market_symbols.join(", ") ?? "—"}/><Row label="Timeframes Kraken" value={caps.data?.market_timeframes.join(", ") ?? "—"}/><p className="mt-4 text-xs text-slate-500">Le chart consomme uniquement les candles renvoyées par le backend.</p></TabsContent>
        <TabsContent value="trading"><h3 className="mb-4 font-semibold">Trading</h3><Row label="Système par défaut" value={caps.data?.default_system_id ?? "—"}/><Row label="Environnement LIVE" value={caps.data?.live_environment ?? "—"}/><Row label="État d'armement" value="Non exposé par l'API actuelle"/><p className="mt-4 rounded-lg border border-amber-900/50 bg-amber-950/20 p-3 text-xs text-amber-200">Aucun bouton d’armement LIVE n’est ajouté tant qu’une API backend opérateur sécurisée n’existe pas.</p></TabsContent>
        <TabsContent value="agents"><h3 className="mb-4 font-semibold">Agents / IA</h3>{backtest.data?.agents.map(a => <Row key={a.agent} label={`${a.agent} · ${a.role}`} value={<StatusBadge value={a.state}/>}/>)}</TabsContent>
        <TabsContent value="risk"><h3 className="mb-4 font-semibold">Risque</h3><p className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-400">Les garde-fous constitutionnels ne sont pas modifiables depuis cette interface. Les valeurs de backtest restent configurables uniquement dans le formulaire de campagne PAPER.</p></TabsContent>
        <TabsContent value="backtest"><h3 className="mb-4 font-semibold">Backtest</h3><Row label="PAPER only" value={String(backtest.data?.paper_only ?? true)}/><Row label="Modes IA" value={backtest.data?.modes.join(", ") ?? "—"}/><Row label="LIVE_EVAL disponible" value={String(backtest.data?.live_eval_available ?? false)}/></TabsContent>
        <TabsContent value="interface"><h3 className="mb-4 font-semibold">Interface</h3><p className="text-sm text-slate-400">Le panneau latéral mémorise localement son état réduit. Aucun secret n’est stocké dans le navigateur.</p></TabsContent>
      </div>
    </Tabs>
  </DialogContent></Dialog>;
}
