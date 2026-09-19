"use client";

import {
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import type { FrontendAnalyticsOverlays } from "@/lib/api/analytics-overlay-schemas";
import type { BacktestReplay, MarketCandles } from "@/lib/api/schemas";
import { buildChartOverlayModel, selectionAtTime } from "./analytics-overlays";
import type { OverlayFilters, OverlaySelection, OverlayVisibility } from "@/lib/analytics-overlay-state";

export type TradingChartCandle = MarketCandles["candles"][number];
export type TradingChartEvent = BacktestReplay["events"][number];

export type TradingChartAdapterProps = {
  candles: TradingChartCandle[];
  events?: TradingChartEvent[];
  analyticsOverlays?: FrontendAnalyticsOverlays | null;
  overlayVisibility: OverlayVisibility;
  overlayFilters: OverlayFilters;
  cursorTime?: number | null;
  onEventSelect?: (event: TradingChartEvent) => void;
  onOverlaySelect?: (selection: OverlaySelection) => void;
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
    text: opportunity ? "OPP" : eventType,
  };
}

/**
 * lightweight-charts 4.2.x does not parse HSL strings.
 * Money Heist theme tokens are stored as Tailwind-style HSL triplets
 * (for example "217 16% 58%"), so convert them to legacy rgb(...)
 * before passing them to lightweight-charts.
 */
export function chartColorFromHslToken(value: string, fallback: string): string {
  const normalized = value.trim();
  const match = normalized.match(
    /^(-?(?:\d+(?:\.\d+)?|\.\d+))(?:deg)?\s+((?:\d+(?:\.\d+)?|\.\d+)%)\s+((?:\d+(?:\.\d+)?|\.\d+)%)$/,
  );

  if (!match) return fallback;

  const [, hueToken, saturationToken, lightnessToken] = match;

  if (!hueToken || !saturationToken || !lightnessToken) {
    return fallback;
  }

  const rawHue = Number(hueToken);
  const saturation = Number(saturationToken.slice(0, -1));
  const lightness = Number(lightnessToken.slice(0, -1));

  if (
    !Number.isFinite(rawHue) ||
    !Number.isFinite(saturation) ||
    !Number.isFinite(lightness) ||
    saturation < 0 ||
    saturation > 100 ||
    lightness < 0 ||
    lightness > 100
  ) {
    return fallback;
  }

  const hue = ((rawHue % 360) + 360) % 360;
  const s = saturation / 100;
  const l = lightness / 100;

  const chroma = (1 - Math.abs(2 * l - 1)) * s;
  const hueSector = hue / 60;
  const x = chroma * (1 - Math.abs((hueSector % 2) - 1));

  let r1 = 0;
  let g1 = 0;
  let b1 = 0;

  if (hueSector < 1) {
    r1 = chroma;
    g1 = x;
  } else if (hueSector < 2) {
    r1 = x;
    g1 = chroma;
  } else if (hueSector < 3) {
    g1 = chroma;
    b1 = x;
  } else if (hueSector < 4) {
    g1 = x;
    b1 = chroma;
  } else if (hueSector < 5) {
    r1 = x;
    b1 = chroma;
  } else {
    r1 = chroma;
    b1 = x;
  }

  const m = l - chroma / 2;
  const red = Math.round((r1 + m) * 255);
  const green = Math.round((g1 + m) * 255);
  const blue = Math.round((b1 + m) * 255);

  return `rgb(${red}, ${green}, ${blue})`;
}

function cssToken(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value ? chartColorFromHslToken(value, fallback) : fallback;
}

export function TradingChartAdapter({
  candles,
  events = [],
  analyticsOverlays,
  overlayVisibility,
  overlayFilters,
  cursorTime = null,
  onEventSelect,
  onOverlaySelect,
}: TradingChartAdapterProps) {
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const zigzagRef = useRef<ISeriesApi<"Line"> | null>(null);
  const patternRefs = useRef<ISeriesApi<"Line">[]>([]);
  const initialFitDone = useRef(false);

  const chartData = useMemo(
    () =>
      candles.map((candle) => ({
        time: candle.time as Time,
        open: Number(candle.open),
        high: Number(candle.high),
        low: Number(candle.low),
        close: Number(candle.close),
      })),
    [candles],
  );
  const volumeData = useMemo(
    () =>
      candles.map((candle) => ({
        time: candle.time as Time,
        value: Number(candle.volume),
        color: Number(candle.close) >= Number(candle.open) ? "rgba(16,185,129,.35)" : "rgba(244,63,94,.35)",
      })),
    [candles],
  );
  const overlayModel = useMemo(
    () => buildChartOverlayModel(analyticsOverlays, overlayVisibility, overlayFilters, cursorTime),
    [analyticsOverlays, cursorTime, overlayFilters, overlayVisibility],
  );

  useEffect(() => {
    if (!host.current) return;
    const chart = createChart(host.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: cssToken("--background", "#070b13") },
        textColor: cssToken("--muted", "#94a3b8"),
      },
      grid: {
        vertLines: { color: cssToken("--border", "#121a29") },
        horzLines: { color: cssToken("--border", "#121a29") },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: cssToken("--border", "#1e293b") },
      timeScale: { borderColor: cssToken("--border", "#1e293b"), timeVisible: true, secondsVisible: false },
    });
    const series = chart.addCandlestickSeries({
      upColor: "#10b981",
      downColor: "#f43f5e",
      borderVisible: false,
      wickUpColor: "#34d399",
      wickDownColor: "#fb7185",
    });
    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    const zigzag = chart.addLineSeries({
      color: cssToken("--accent", "#a78bfa"),
      lineWidth: 2,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });
    chartRef.current = chart;
    candleRef.current = series;
    volumeRef.current = volume;
    zigzagRef.current = zigzag;
    return () => {
      patternRefs.current = [];
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
      zigzagRef.current = null;
      initialFitDone.current = false;
    };
  }, []);

  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;
    series.setData(chartData);
    volumeRef.current?.setData(volumeData);
    const replayMarkers = overlayVisibility.trading
      ? events.filter((event) => event.event_type.toUpperCase() !== "ANALYSIS").map(markerFor)
      : [];
    const markers = [...replayMarkers, ...overlayModel.markers.map((item) => item.marker)].sort(
      (left, right) => Number(left.time) - Number(right.time),
    );
    series.setMarkers(markers);
    zigzagRef.current?.setData(overlayModel.zigzag);
    if (!initialFitDone.current && chartData.length > 0) {
      chartRef.current?.timeScale().fitContent();
      initialFitDone.current = true;
    }
  }, [chartData, events, overlayModel, overlayVisibility.trading, volumeData]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    for (const series of patternRefs.current) chart.removeSeries(series);
    patternRefs.current = overlayModel.patternSegments.map((segment) => {
      const failed = segment.status === "FAILED" || segment.status === "INVALIDATED";
      const series = chart.addLineSeries({
        color: failed ? "#94a3b8" : cssToken("--accent", "#a78bfa"),
        lineWidth: 1,
        lineStyle: segment.status === "FORMING" ? LineStyle.Dashed : failed ? LineStyle.Dotted : LineStyle.Solid,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
      });
      series.setData(segment.points);
      return series;
    });
    return () => {
      const activeChart = chartRef.current;
      if (!activeChart) return;
      for (const series of patternRefs.current) activeChart.removeSeries(series);
      patternRefs.current = [];
    };
  }, [overlayModel.patternSegments]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || (!onEventSelect && !onOverlaySelect)) return;
    const handler = (param: { time?: Time }) => {
      if (param.time === undefined) return;
      const overlaySelection = selectionAtTime(overlayModel.markers, param.time);
      if (overlaySelection && onOverlaySelect) {
        onOverlaySelect(overlaySelection);
        return;
      }
      if (!onEventSelect) return;
      const clicked = Number(param.time);
      const event = events
        .slice()
        .reverse()
        .find((item) => Math.floor(new Date(item.observed_at).getTime() / 1000) === clicked);
      if (event) onEventSelect(event);
    };
    chart.subscribeClick(handler);
    return () => chart.unsubscribeClick(handler);
  }, [events, onEventSelect, onOverlaySelect, overlayModel.markers]);

  useEffect(() => {
    if (!cursorTime || !chartRef.current) return;
    const halfWindow = 16 * 3600;
    chartRef.current.timeScale().setVisibleRange({
      from: (cursorTime - halfWindow) as Time,
      to: (cursorTime + halfWindow) as Time,
    });
  }, [cursorTime]);

  return (
    <div ref={host} className="h-full min-h-[420px] w-full" aria-label="Graphique de trading et overlays Analytics" />
  );
}
