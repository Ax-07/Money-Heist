"use client";

import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import type { BacktestReplay, MarketCandles } from "@/lib/api/schemas";

export type TradingChartCandle = MarketCandles["candles"][number];
export type TradingChartEvent = BacktestReplay["events"][number];

export type TradingChartAdapterProps = {
  candles: TradingChartCandle[];
  events?: TradingChartEvent[];
  cursorTime?: number | null;
  onEventSelect?: (event: TradingChartEvent) => void;
};

export function markerFor(event: TradingChartEvent): SeriesMarker<Time> {
  const eventType = event.event_type.toUpperCase();
  const entry = eventType === "ENTRY";
  const exit = eventType === "EXIT";
  const risk = eventType === "RISK";
  const opportunity = eventType === "OPPORTUNITY";
  return {
    time: Math.floor(new Date(event.observed_at).getTime() / 1000) as Time,
    position: entry || eventType === "FINAL" ? "belowBar" : "aboveBar",
    color: entry ? "#34d399" : exit ? "#f59e0b" : risk ? "#fb923c" : opportunity ? "#8b5cf6" : "#a78bfa",
    shape: entry ? "arrowUp" : exit ? "arrowDown" : risk ? "square" : "circle",
    text: opportunity ? "OPP" : eventType
  };
}

export function TradingChartAdapter({ candles, events = [], cursorTime, onEventSelect }: TradingChartAdapterProps) {
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const initialFitDone = useRef(false);

  const chartData = useMemo(
    () => candles.map((candle) => ({
      time: candle.time as Time,
      open: Number(candle.open), high: Number(candle.high), low: Number(candle.low), close: Number(candle.close)
    })),
    [candles]
  );
  const volumeData = useMemo(
    () => candles.map((candle) => ({
      time: candle.time as Time, value: Number(candle.volume),
      color: Number(candle.close) >= Number(candle.open) ? "rgba(16,185,129,.35)" : "rgba(244,63,94,.35)"
    })),
    [candles]
  );

  useEffect(() => {
    if (!host.current) return;
    const chart = createChart(host.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "#070b13" }, textColor: "#94a3b8" },
      grid: { vertLines: { color: "#121a29" }, horzLines: { color: "#121a29" } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#1e293b" },
      timeScale: { borderColor: "#1e293b", timeVisible: true, secondsVisible: false }
    });
    const series = chart.addCandlestickSeries({
      upColor: "#10b981", downColor: "#f43f5e", borderVisible: false, wickUpColor: "#34d399", wickDownColor: "#fb7185"
    });
    const volume = chart.addHistogramSeries({priceFormat: {type: "volume"}, priceScaleId: "", lastValueVisible: false, priceLineVisible: false});
    volume.priceScale().applyOptions({scaleMargins: {top: 0.82, bottom: 0}});
    chartRef.current = chart;
    candleRef.current = series;
    volumeRef.current = volume;
    return () => {
      chart.remove(); chartRef.current = null; candleRef.current = null; volumeRef.current = null; initialFitDone.current = false;
    };
  }, []);

  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;
    series.setData(chartData);
    volumeRef.current?.setData(volumeData);
    const markers = events
      .filter((event) => event.event_type.toUpperCase() !== "ANALYSIS")
      .map(markerFor)
      .sort((left, right) => Number(left.time) - Number(right.time));
    series.setMarkers(markers);
    if (!initialFitDone.current && chartData.length > 0) {
      chartRef.current?.timeScale().fitContent();
      initialFitDone.current = true;
    }
  }, [chartData, events, volumeData]);


  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !onEventSelect) return;
    const handler = (param: {time?: Time}) => {
      if (param.time === undefined) return;
      const clicked = Number(param.time);
      const event = events.slice().reverse().find((item) => Math.floor(new Date(item.observed_at).getTime() / 1000) === clicked);
      if (event) onEventSelect(event);
    };
    chart.subscribeClick(handler);
    return () => chart.unsubscribeClick(handler);
  }, [events, onEventSelect]);

  useEffect(() => {
    if (!cursorTime || !chartRef.current) return;
    const halfWindow = 16 * 3600;
    chartRef.current.timeScale().setVisibleRange({
      from: (cursorTime - halfWindow) as Time,
      to: (cursorTime + halfWindow) as Time
    });
  }, [cursorTime]);

  return <div ref={host} className="h-full min-h-[420px] w-full" aria-label="Graphique de trading" />;
}
