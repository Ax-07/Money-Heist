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
import type { DecisionIndicatorPoint } from "@/lib/api/decision-chart-schemas";
import type { DecisionChartDisplayMode, SelectedTradePlan } from "@/lib/trade-terminal";
import type { BacktestReplay, MarketCandles } from "@/lib/api/schemas";
import { buildChartOverlayModel, buildDecisionOverlayMarkers, buildRiskRejectedPoints, buildTradeEntryMarkers, buildTradeExitMarkers, buildTradeLinkSegments, selectionAtTime } from "./analytics-overlays";
import type { OverlayFilters, OverlaySelection, OverlayVisibility } from "@/lib/analytics-overlay-state";

export type TradingChartCandle = MarketCandles["candles"][number];
export type TradingChartEvent = BacktestReplay["events"][number];
export type TradingChartTrade = BacktestReplay["trades"][number];

export type TradingChartAdapterProps = {
  candles: TradingChartCandle[];
  events?: TradingChartEvent[];
  trades?: TradingChartTrade[];
  analyticsOverlays?: FrontendAnalyticsOverlays | null;
  overlayVisibility: OverlayVisibility;
  overlayFilters: OverlayFilters;
  cursorTime?: number | null;
  decisionOnly?: boolean;
  decisionIndicators?: DecisionIndicatorPoint[];
  decisionDisplayMode?: DecisionChartDisplayMode;
  selectedTradeId?: string | null;
  selectedOpportunityId?: string | null;
  selectedTradePlan?: SelectedTradePlan | null;
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

type DecisionPriceIndicatorKey = "ema_fast" | "ema_slow" | "prior_range_high_20" | "prior_range_low_20";

function indicatorLineData(points: DecisionIndicatorPoint[], key: DecisionPriceIndicatorKey) {
  const output: Array<{ time: Time; value: number }> = [];
  for (const point of points) {
    const value = point[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      output.push({ time: point.time as Time, value });
    }
  }
  return output;
}

export function TradingChartAdapter({
  candles,
  events = [],
  trades = [],
  analyticsOverlays,
  overlayVisibility,
  overlayFilters,
  cursorTime = null,
  decisionOnly = false,
  decisionIndicators = [],
  decisionDisplayMode = "MIXED",
  selectedTradeId = null,
  selectedOpportunityId = null,
  selectedTradePlan = null,
  onEventSelect,
  onOverlaySelect,
}: TradingChartAdapterProps) {
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const zigzagRef = useRef<ISeriesApi<"Line"> | null>(null);
  const emaFastRef = useRef<ISeriesApi<"Line"> | null>(null);
  const emaSlowRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rangeHighRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rangeLowRef = useRef<ISeriesApi<"Line"> | null>(null);
  const executionOverlayRef = useRef<SVGSVGElement | null>(null);
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
  const decisionMarkers = useMemo(
    () => buildDecisionOverlayMarkers(analyticsOverlays, null),
    [analyticsOverlays],
  );
  const candleTimes = useMemo(() => candles.map(candle => candle.time), [candles]);
  const tradeExitMarkers = useMemo(
    () => buildTradeExitMarkers(trades, candleTimes),
    [candleTimes, trades],
  );
  const tradeEntryMarkers = useMemo(
    () => buildTradeEntryMarkers(trades, candleTimes),
    [candleTimes, trades],
  );
  const tradeLinkSegments = useMemo(
    () => buildTradeLinkSegments(trades, candleTimes),
    [candleTimes, trades],
  );
  const riskRejectedPoints = useMemo(
    () => buildRiskRejectedPoints(analyticsOverlays, candleTimes),
    [analyticsOverlays, candleTimes],
  );
  const decisionChartMarkers = useMemo(() => {
    const base = decisionDisplayMode === "TRADES"
      ? [...tradeEntryMarkers, ...tradeExitMarkers]
      : decisionDisplayMode === "DECISIONS"
        ? decisionMarkers
        : [...decisionMarkers, ...tradeExitMarkers];
    const hasFocus = selectedTradeId !== null || selectedOpportunityId !== null;
    return base
      .sort((left, right) => Number(left.marker.time) - Number(right.marker.time) || right.priority - left.priority)
      .map(item => {
        if (!hasFocus) return item;
        const selected = item.selection.objectId === selectedTradeId
          || item.selection.details.trade_id === selectedTradeId
          || item.selection.opportunityId === selectedOpportunityId;
        if (!selected) return item;
        const currentSize = typeof item.marker.size === "number" ? item.marker.size : 1;
        return {
          ...item,
          marker: {
            ...item.marker,
            size: currentSize + 1,
          },
        };
      });
  }, [decisionDisplayMode, decisionMarkers, selectedOpportunityId, selectedTradeId, tradeEntryMarkers, tradeExitMarkers]);
  const indicatorSeriesData = useMemo(() => ({
    emaFast: indicatorLineData(decisionIndicators, "ema_fast"),
    emaSlow: indicatorLineData(decisionIndicators, "ema_slow"),
    rangeHigh: indicatorLineData(decisionIndicators, "prior_range_high_20"),
    rangeLow: indicatorLineData(decisionIndicators, "prior_range_low_20"),
  }), [decisionIndicators]);

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
    const emaFast = chart.addLineSeries({
      color: "#38bdf8",
      lineWidth: 1,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });
    const emaSlow = chart.addLineSeries({
      color: "#a78bfa",
      lineWidth: 1,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });
    const rangeHigh = chart.addLineSeries({
      color: "#64748b",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });
    const rangeLow = chart.addLineSeries({
      color: "#64748b",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });
    const executionOverlay = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    executionOverlay.setAttribute("aria-hidden", "true");
    executionOverlay.style.position = "absolute";
    executionOverlay.style.inset = "0";
    executionOverlay.style.width = "100%";
    executionOverlay.style.height = "100%";
    executionOverlay.style.pointerEvents = "none";
    executionOverlay.style.zIndex = "3";
    host.current.appendChild(executionOverlay);

    chartRef.current = chart;
    candleRef.current = series;
    volumeRef.current = volume;
    zigzagRef.current = zigzag;
    emaFastRef.current = emaFast;
    emaSlowRef.current = emaSlow;
    rangeHighRef.current = rangeHigh;
    rangeLowRef.current = rangeLow;
    executionOverlayRef.current = executionOverlay;
    return () => {
      patternRefs.current = [];
      executionOverlay.remove();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
      zigzagRef.current = null;
      emaFastRef.current = null;
      emaSlowRef.current = null;
      rangeHighRef.current = null;
      rangeLowRef.current = null;
      executionOverlayRef.current = null;
      initialFitDone.current = false;
    };
  }, []);

  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;
    series.setData(chartData);
    volumeRef.current?.setData(volumeData);
    const replayMarkers = !decisionOnly && overlayVisibility.trading
      ? events.filter((event) => event.event_type.toUpperCase() !== "ANALYSIS").map(markerFor)
      : [];
    const markers = decisionOnly
      ? decisionChartMarkers.map(item => item.marker)
      : [...replayMarkers, ...overlayModel.markers.map((item) => item.marker)].sort(
          (left, right) => Number(left.time) - Number(right.time),
        );
    series.setMarkers(markers);
    zigzagRef.current?.setData(decisionOnly ? [] : overlayModel.zigzag);
    emaFastRef.current?.setData(decisionOnly ? indicatorSeriesData.emaFast : []);
    emaSlowRef.current?.setData(decisionOnly ? indicatorSeriesData.emaSlow : []);
    rangeHighRef.current?.setData(decisionOnly ? indicatorSeriesData.rangeHigh : []);
    rangeLowRef.current?.setData(decisionOnly ? indicatorSeriesData.rangeLow : []);
    if (!initialFitDone.current && chartData.length > 0) {
      chartRef.current?.timeScale().fitContent();
      initialFitDone.current = true;
    }
  }, [chartData, decisionChartMarkers, decisionOnly, events, indicatorSeriesData, overlayModel, overlayVisibility.trading, volumeData]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    for (const series of patternRefs.current) chart.removeSeries(series);
    patternRefs.current = [];
    if (decisionOnly) return;
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
  }, [decisionOnly, overlayModel.patternSegments]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = candleRef.current;
    const overlay = executionOverlayRef.current;
    const container = host.current;
    if (!chart || !series || !overlay || !container) return;

    const svgNs = "http://www.w3.org/2000/svg";
    const timeScale = chart.timeScale();

    const xForTimestamp = (timestamp: number): number | null => {
      if (candleTimes.length === 0) return null;
      const firstTime = candleTimes[0];
      const lastTime = candleTimes[candleTimes.length - 1];
      if (firstTime === undefined || lastTime === undefined) return null;
      if (timestamp <= firstTime) return timeScale.timeToCoordinate(firstTime as Time);
      if (timestamp >= lastTime) return timeScale.timeToCoordinate(lastTime as Time);
      let low = 0;
      let high = candleTimes.length - 1;
      while (low < high) {
        const mid = Math.floor((low + high) / 2);
        if ((candleTimes[mid] ?? lastTime) < timestamp) low = mid + 1;
        else high = mid;
      }
      const rightIndex = low;
      const leftIndex = Math.max(0, rightIndex - 1);
      const leftTime = candleTimes[leftIndex];
      const rightTime = candleTimes[rightIndex];
      if (leftTime === undefined || rightTime === undefined) return null;
      const leftX = timeScale.timeToCoordinate(leftTime as Time);
      const rightX = timeScale.timeToCoordinate(rightTime as Time);
      if (leftX === null || rightX === null) return null;
      if (rightTime === leftTime) return rightX;
      const ratio = Math.min(1, Math.max(0, (timestamp - leftTime) / (rightTime - leftTime)));
      return leftX + (rightX - leftX) * ratio;
    };

    const redraw = () => {
      overlay.replaceChildren();
      if (!decisionOnly) return;
      const width = Math.max(1, container.clientWidth);
      const height = Math.max(1, container.clientHeight);
      overlay.setAttribute("viewBox", `0 0 ${width} ${height}`);

      if (decisionDisplayMode !== "DECISIONS") {
        for (const segment of tradeLinkSegments) {
          const x1 = xForTimestamp(segment.entryTimestamp);
          const x2 = xForTimestamp(segment.exitTimestamp);
          const y1 = series.priceToCoordinate(segment.entryPrice);
          const y2 = series.priceToCoordinate(segment.exitPrice);
          if (x1 === null || x2 === null || y1 === null || y2 === null) continue;
          const selected = selectedTradeId === segment.tradeId;
          const hasFocus = selectedTradeId !== null;
          const color = segment.profitable ? "#22c55e" : "#ef4444";
          const line = document.createElementNS(svgNs, "line");
          line.setAttribute("x1", String(x1));
          line.setAttribute("y1", String(y1));
          line.setAttribute("x2", String(x2));
          line.setAttribute("y2", String(y2));
          line.setAttribute("stroke", color);
          line.setAttribute("stroke-width", selected ? "3" : "2");
          line.setAttribute("stroke-linecap", "round");
          line.setAttribute("opacity", hasFocus ? (selected ? "1" : "0.48") : "0.82");
          line.setAttribute("vector-effect", "non-scaling-stroke");
          overlay.appendChild(line);

          for (const [cx, cy] of [[x1, y1], [x2, y2]] as const) {
            const endpoint = document.createElementNS(svgNs, "circle");
            endpoint.setAttribute("cx", String(cx));
            endpoint.setAttribute("cy", String(cy));
            endpoint.setAttribute("r", selected ? "3.5" : "2.25");
            endpoint.setAttribute("fill", color);
            endpoint.setAttribute("stroke", "#0f172a");
            endpoint.setAttribute("stroke-width", "1");
            endpoint.setAttribute("opacity", hasFocus ? (selected ? "1" : "0.62") : "0.9");
            overlay.appendChild(endpoint);
          }
        }

        const selectedSegment = selectedTradeId
          ? tradeLinkSegments.find(segment => segment.tradeId === selectedTradeId)
          : undefined;
        if (selectedSegment && selectedTradePlan) {
          const x1 = xForTimestamp(selectedSegment.entryTimestamp);
          const x2 = xForTimestamp(selectedSegment.exitTimestamp);
          if (x1 !== null && x2 !== null) {
            const levels = [
              { price: selectedTradePlan.stopPrice, color: "#ef4444", dash: "5 4" },
              ...selectedTradePlan.targets.map(price => ({ price, color: "#22c55e", dash: "5 4" })),
            ];
            for (const level of levels) {
              const y = series.priceToCoordinate(level.price);
              if (y === null) continue;
              const guide = document.createElementNS(svgNs, "line");
              guide.setAttribute("x1", String(x1));
              guide.setAttribute("x2", String(x2));
              guide.setAttribute("y1", String(y));
              guide.setAttribute("y2", String(y));
              guide.setAttribute("stroke", level.color);
              guide.setAttribute("stroke-width", "1.5");
              guide.setAttribute("stroke-dasharray", level.dash);
              guide.setAttribute("opacity", "0.78");
              guide.setAttribute("vector-effect", "non-scaling-stroke");
              overlay.appendChild(guide);
            }
          }
        }
      }

      if (decisionDisplayMode !== "TRADES") {
        for (const point of riskRejectedPoints) {
          const x = timeScale.timeToCoordinate(point.time);
          const candle = candles.find(item => item.time === Number(point.time));
          if (x === null || !candle) continue;
          const long = point.direction === "LONG";
          const anchorPrice = Number(long ? candle.low : candle.high);
          if (!Number.isFinite(anchorPrice)) continue;
          const anchorY = series.priceToCoordinate(anchorPrice);
          if (anchorY === null) continue;
          const y = long ? Math.min(height - 7, anchorY + 9) : Math.max(7, anchorY - 9);
          const selected = point.selection.opportunityId === selectedOpportunityId;
          const hasFocus = selectedOpportunityId !== null;
          const opacity = hasFocus ? (selected ? "1" : "0.72") : "1";
          const radius = 3.5;
          for (const [x1, y1, x2, y2] of [
            [x - radius, y - radius, x + radius, y + radius],
            [x - radius, y + radius, x + radius, y - radius],
          ]) {
            const stroke = document.createElementNS(svgNs, "line");
            stroke.setAttribute("x1", String(x1));
            stroke.setAttribute("y1", String(y1));
            stroke.setAttribute("x2", String(x2));
            stroke.setAttribute("y2", String(y2));
            stroke.setAttribute("stroke", "#ef4444");
            stroke.setAttribute("stroke-width", "2");
            stroke.setAttribute("stroke-linecap", "round");
            stroke.setAttribute("opacity", opacity);
            stroke.setAttribute("vector-effect", "non-scaling-stroke");
            overlay.appendChild(stroke);
          }
          if (onOverlaySelect) {
            const hit = document.createElementNS(svgNs, "circle");
            hit.setAttribute("cx", String(x));
            hit.setAttribute("cy", String(y));
            hit.setAttribute("r", "8");
            hit.setAttribute("fill", "transparent");
            hit.style.pointerEvents = "all";
            hit.style.cursor = "pointer";
            hit.addEventListener("click", event => {
              event.stopPropagation();
              onOverlaySelect(point.selection);
            });
            overlay.appendChild(hit);
          }
        }
      }
    };

    let animationFrame: number | null = null;
    const scheduleRedraw = () => {
      if (animationFrame !== null) return;
      animationFrame = window.requestAnimationFrame(() => {
        animationFrame = null;
        redraw();
      });
    };
    redraw();
    timeScale.subscribeVisibleLogicalRangeChange(scheduleRedraw);
    chart.subscribeCrosshairMove(scheduleRedraw);
    const resizeObserver = new ResizeObserver(scheduleRedraw);
    resizeObserver.observe(container);
    return () => {
      timeScale.unsubscribeVisibleLogicalRangeChange(scheduleRedraw);
      chart.unsubscribeCrosshairMove(scheduleRedraw);
      resizeObserver.disconnect();
      if (animationFrame !== null) window.cancelAnimationFrame(animationFrame);
      overlay.replaceChildren();
    };
  }, [candleTimes, candles, decisionDisplayMode, decisionOnly, onOverlaySelect, riskRejectedPoints, selectedOpportunityId, selectedTradeId, selectedTradePlan, tradeLinkSegments]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || (!onEventSelect && !onOverlaySelect)) return;
    const handler = (param: { time?: Time }) => {
      if (param.time === undefined) return;
      const activeMarkers = decisionOnly ? decisionChartMarkers : overlayModel.markers;
      const overlaySelection = selectionAtTime(activeMarkers, param.time);
      if (overlaySelection && onOverlaySelect) {
        onOverlaySelect(overlaySelection);
        return;
      }
      if (decisionOnly || !onEventSelect) return;
      const clicked = Number(param.time);
      const event = events
        .slice()
        .reverse()
        .find((item) => Math.floor(new Date(item.observed_at).getTime() / 1000) === clicked);
      if (event) onEventSelect(event);
    };
    chart.subscribeClick(handler);
    return () => chart.unsubscribeClick(handler);
  }, [decisionChartMarkers, decisionOnly, events, onEventSelect, onOverlaySelect, overlayModel.markers]);

  useEffect(() => {
    // Decision Chart is a post-run observability view: keep the whole role history
    // loaded/visible and use the replay cursor only to inspect indicator values.
    if (decisionOnly || !cursorTime || !chartRef.current) return;
    const last = candles.at(-1)?.time;
    const previous = candles.at(-2)?.time;
    const interval = last !== undefined && previous !== undefined ? Math.max(60, last - previous) : 3600;
    const halfWindow = Math.max(16 * 3600, interval * 40);
    chartRef.current.timeScale().setVisibleRange({
      from: (cursorTime - halfWindow) as Time,
      to: (cursorTime + halfWindow) as Time,
    });
  }, [candles, cursorTime, decisionOnly]);

  return (
    <div
      ref={host}
      className="relative h-full min-h-[420px] w-full overflow-hidden"
      aria-label={decisionOnly ? "Graphique des décisions et indicateurs" : "Graphique de trading et overlays Analytics"}
    />
  );
}
