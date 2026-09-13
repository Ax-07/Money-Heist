"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Bot, CandlestickChart, ChartNoAxesCombined, ChevronsLeft, ChevronsRight, ClipboardList, Gauge, History, ListChecks, Settings, ShieldCheck, WalletCards } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/lib/ui-store";

const nav = [
  ["/dashboard", "Dashboard", Gauge], ["/trading", "Trading", CandlestickChart], ["/backtests", "Backtests", ChartNoAxesCombined],
  ["/opportunities", "Opportunités", Activity], ["/orders", "Ordres", ClipboardList], ["/positions", "Positions", WalletCards], ["/history", "Historique", History],
  ["/agents", "Agents", Bot], ["/evaluation", "Évaluation", ListChecks]
] as const;
export function Sidebar() {
  const pathname = usePathname(); const collapsed = useUiStore(s => s.sidebarCollapsed); const setCollapsed = useUiStore(s => s.setSidebarCollapsed); const setSettings = useUiStore(s => s.setSettingsOpen);
  return <aside className={cn("hidden h-screen shrink-0 flex-col md:flex border-r border-slate-800 bg-slate-950/95 transition-[width]", collapsed ? "w-[68px]" : "w-[220px]")}>
    <div className="flex h-16 items-center gap-3 border-b border-slate-800 px-4"><ShieldCheck className="h-7 w-7 text-violet-400"/><div className={cn("min-w-0", collapsed && "hidden")}><div className="font-semibold tracking-wide">MONEY HEIST</div><div className="text-[10px] uppercase tracking-[.2em] text-slate-500">Trading Cockpit</div></div></div>
    <nav className="flex-1 space-y-1 p-2">{nav.map(([href,label,Icon]) => { const active = pathname === href || (href === "/backtests" && pathname.startsWith("/backtests/")); return <Link key={href} href={href} title={collapsed ? label : undefined} className={cn("flex h-10 items-center gap-3 rounded-lg px-3 text-sm text-slate-400 hover:bg-slate-900 hover:text-slate-100", active && "bg-violet-950/50 text-violet-200 ring-1 ring-violet-900/60")}><Icon className="h-4 w-4 shrink-0"/><span className={collapsed ? "hidden" : "block"}>{label}</span></Link>; })}</nav>
    <div className="space-y-1 border-t border-slate-800 p-2"><button onClick={() => setSettings(true)} className="flex h-10 w-full items-center gap-3 rounded-lg px-3 text-sm text-slate-400 hover:bg-slate-900 hover:text-white"><Settings className="h-4 w-4"/><span className={collapsed ? "hidden" : "block"}>Réglages</span></button><button onClick={() => setCollapsed(!collapsed)} className="flex h-10 w-full items-center gap-3 rounded-lg px-3 text-sm text-slate-500 hover:bg-slate-900">{collapsed ? <ChevronsRight className="h-4 w-4"/> : <ChevronsLeft className="h-4 w-4"/>}<span className={collapsed ? "hidden" : "block"}>Réduire</span></button></div>
  </aside>;
}
