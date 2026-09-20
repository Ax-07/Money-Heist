"use client";

import type { FrontendAnalyticsOverlays } from "@/lib/api/analytics-overlay-schemas";
import type { DecisionIndicatorPoint } from "@/lib/api/decision-chart-schemas";
import type { DecisionChartDisplayMode, SelectedTradePlan } from "@/lib/trade-terminal";
import type { BacktestReplay, MarketCandles } from "@/lib/api/schemas";
import { useUiStore } from "@/lib/ui-store";
import type { OverlaySelection } from "@/lib/analytics-overlay-state";
import { TradingChartAdapter } from "./trading-chart-adapter";

type Candle = MarketCandles["candles"][number];
type Event = BacktestReplay["events"][number];
type Trade = BacktestReplay["trades"][number];
export type TradingChartProps = {
  mode: string;
  symbol: string;
  timeframe: string;
  candles: Candle[];
  events?: Event[];
  trades?: Trade[];
  analyticsOverlays?: FrontendAnalyticsOverlays | null;
  cursorTime?: number | null;
  decisionOnly?: boolean;
  decisionIndicators?: DecisionIndicatorPoint[];
  decisionDisplayMode?: DecisionChartDisplayMode;
  selectedTradeId?: string | null;
  selectedOpportunityId?: string | null;
  selectedTradePlan?: SelectedTradePlan | null;
  onEventSelect?: (event: Event) => void;
  onOverlaySelect?: (selection: OverlaySelection) => void;
};

export function TradingChart({
  candles,
  events,
  trades,
  analyticsOverlays,
  cursorTime,
  decisionOnly,
  decisionIndicators,
  decisionDisplayMode,
  selectedTradeId,
  selectedOpportunityId,
  selectedTradePlan,
  onEventSelect,
  onOverlaySelect,
}: TradingChartProps) {
  const overlayVisibility = useUiStore(state => state.overlayVisibility);
  const overlayFilters = useUiStore(state => state.overlayFilters);
  return (
    <TradingChartAdapter
      candles={candles}
      events={events}
      trades={trades}
      analyticsOverlays={analyticsOverlays}
      overlayVisibility={overlayVisibility}
      overlayFilters={overlayFilters}
      cursorTime={cursorTime}
      decisionOnly={decisionOnly}
      decisionIndicators={decisionIndicators}
      decisionDisplayMode={decisionDisplayMode}
      selectedTradeId={selectedTradeId}
      selectedOpportunityId={selectedOpportunityId}
      selectedTradePlan={selectedTradePlan}
      onEventSelect={onEventSelect}
      onOverlaySelect={onOverlaySelect}
    />
  );
}
