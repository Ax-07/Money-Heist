"use client";
import { useQuery } from "@tanstack/react-query";
import { Menu, Wifi, WifiOff } from "lucide-react";
import { frontendCapabilitiesQuery } from "@/lib/api/queries";
import { StatusBadge } from "@/components/ui/badge";
import { useUiStore } from "@/lib/ui-store";
export function Topbar(){const caps=useQuery({queryKey:["frontend-capabilities"],queryFn:frontendCapabilitiesQuery,refetchInterval:5000});const open=useUiStore(s=>s.setMobileSidebarOpen);return <header className="flex h-16 items-center justify-between border-b border-slate-800 bg-slate-950/70 px-3 md:px-5 backdrop-blur"><div className="flex min-w-0 items-center gap-2"><button aria-label="Ouvrir la navigation" className="mr-1 rounded p-2 text-slate-400 hover:bg-slate-900 md:hidden" onClick={()=>open(true)}><Menu className="h-5 w-5"/></button><StatusBadge value={caps.data?.default_system_id??"system ?"}/><StatusBadge value={caps.data?.runtime_mode??"UNKNOWN"}/><span className="hidden text-xs text-slate-500 lg:inline">Polling backend · source de vérité FastAPI</span></div><div className="flex items-center gap-2 text-xs text-slate-400">{caps.isError?<><WifiOff className="h-4 w-4 text-rose-400"/><span className="hidden sm:inline">Déconnecté</span></>:<><Wifi className="h-4 w-4 text-emerald-400"/><span className="hidden sm:inline">Backend connecté</span></>}</div></header>}
