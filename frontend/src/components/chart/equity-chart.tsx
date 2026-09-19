"use client";
import { ColorType, createChart, type IChartApi, type ISeriesApi, type Time } from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";

type EquityPoint = { observed_at: string; equity: string };

export function EquityChart({ points }: {points: readonly EquityPoint[]}) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const line = useRef<ISeriesApi<"Line"> | null>(null);
  const data = useMemo(() => points.map((point) => ({time: Math.floor(new Date(point.observed_at).getTime()/1000) as Time, value: Number(point.equity)})), [points]);
  useEffect(() => {
    if (!host.current) return;
    const instance = createChart(host.current, {autoSize: true, layout: {background: {type: ColorType.Solid, color: "#070b13"}, textColor: "#94a3b8"}, grid: {vertLines: {color: "#121a29"}, horzLines: {color: "#121a29"}}, timeScale: {timeVisible: true}});
    chart.current = instance; line.current = instance.addLineSeries({lineWidth: 2});
    return () => {instance.remove(); chart.current=null; line.current=null;};
  }, []);
  useEffect(() => {line.current?.setData(data); chart.current?.timeScale().fitContent();}, [data]);
  return <div ref={host} className="h-[220px] w-full" aria-label="Equity curve"/>;
}
