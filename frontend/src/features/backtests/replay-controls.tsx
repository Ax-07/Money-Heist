"use client";
import { useEffect } from "react";
import { ChevronFirst, ChevronLast, ChevronLeft, ChevronRight, Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { BacktestReplay } from "@/lib/api/schemas";
import { eventIndex, type ReplaySpeed } from "./replay-state";

export function ReplayControls({replay,index,setIndex,playing,setPlaying,speed,setSpeed}:{
  replay:BacktestReplay;index:number;setIndex:(index:number)=>void;playing:boolean;setPlaying:(value:boolean)=>void;speed:ReplaySpeed;setSpeed:(value:ReplaySpeed)=>void;
}){
 useEffect(()=>{if(!playing||replay.candles.length<2)return;const timer=window.setInterval(()=>setIndex(Math.min(index+1,replay.candles.length-1)),Math.max(80,800/speed));return()=>window.clearInterval(timer)},[playing,speed,index,replay.candles.length,setIndex]);
 useEffect(()=>{if(playing&&index>=replay.candles.length-1)setPlaying(false)},[index,playing,replay.candles.length,setPlaying]);
 const icon="h-4 w-4";
 return <div className="flex flex-wrap items-center gap-1 border-t border-slate-800 bg-slate-950/85 px-3 py-2">
  <Button size="icon" variant="ghost" title="Début" onClick={()=>setIndex(0)}><ChevronFirst className={icon}/></Button>
  <Button size="icon" variant="ghost" title="Événement précédent" onClick={()=>setIndex(eventIndex(replay,index,-1))}><SkipBack className={icon}/></Button>
  <Button size="icon" variant="ghost" title="Bougie précédente" onClick={()=>setIndex(Math.max(0,index-1))}><ChevronLeft className={icon}/></Button>
  <Button size="icon" variant="secondary" title={playing?"Pause":"Lecture"} onClick={()=>setPlaying(!playing)}>{playing?<Pause className={icon}/>:<Play className={icon}/>}</Button>
  <Button size="icon" variant="ghost" title="Bougie suivante" onClick={()=>setIndex(Math.min(replay.candles.length-1,index+1))}><ChevronRight className={icon}/></Button>
  <Button size="icon" variant="ghost" title="Événement suivant" onClick={()=>setIndex(eventIndex(replay,index,1))}><SkipForward className={icon}/></Button>
  <Button size="icon" variant="ghost" title="Fin" onClick={()=>setIndex(Math.max(0,replay.candles.length-1))}><ChevronLast className={icon}/></Button>
  <div className="ml-2 flex gap-1">{([1,2,5,10] as const).map(value=><button key={value} className={`rounded px-2 py-1 text-[11px] ${speed===value?"bg-violet-500/20 text-violet-200":"text-slate-500 hover:bg-slate-800"}`} onClick={()=>setSpeed(value)}>x{value}</button>)}</div>
  <input aria-label="Timeline du replay" type="range" min={0} max={Math.max(0,replay.candles.length-1)} value={index} onChange={event=>setIndex(Number(event.target.value))} className="ml-3 min-w-[220px] flex-1 accent-violet-500"/>
  <span className="min-w-[150px] text-right font-mono text-[11px] text-slate-400">{replay.candles[index]?.close_time ? new Date(replay.candles[index].close_time).toLocaleString("fr-FR",{timeZone:"UTC"})+" UTC":"—"}</span>
 </div>
}
