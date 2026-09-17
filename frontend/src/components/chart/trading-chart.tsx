"use client";

import type { FrontendAnalyticsOverlays } from "@/lib/api/analytics-overlay-schemas";
import type { BacktestReplay, MarketCandles } from "@/lib/api/schemas";
import { useUiStore } from "@/lib/ui-store";
import type { OverlaySelection } from "@/lib/analytics-overlay-state";
import { TradingChartAdapter } from "./trading-chart-adapter";

type Candle = MarketCandles["candles"][number];
type Event = BacktestReplay["events"][number];
export type TradingChartProps = {
  mode: string;
  symbol: string;
  timeframe: string;
  candles: Candle[];
  events?: Event[];
  analyticsOverlays?: FrontendAnalyticsOverlays | null;
  cursorTime?: number | null;
  onEventSelect?: (event: Event) => void;
  onOverlaySelect?: (selection: OverlaySelection) => void;
};

export function TradingChart({
  candles,
  events,
  analyticsOverlays,
  cursorTime,
  onEventSelect,
  onOverlaySelect,
}: TradingChartProps) {
  const overlayVisibility = useUiStore(state => state.overlayVisibility);
  const overlayFilters = useUiStore(state => state.overlayFilters);
  return (
    <TradingChartAdapter
      candles={candles}
      events={events}
      analyticsOverlays={analyticsOverlays}
      overlayVisibility={overlayVisibility}
      overlayFilters={overlayFilters}
      cursorTime={cursorTime}
      onEventSelect={onEventSelect}
      onOverlaySelect={onOverlaySelect}
    />
  );
}
