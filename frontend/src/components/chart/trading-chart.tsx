"use client";
import type { BacktestReplay, MarketCandles } from "@/lib/api/schemas";
import { TradingChartAdapter } from "./trading-chart-adapter";

type Candle = MarketCandles["candles"][number];
type Event = BacktestReplay["events"][number];
export type TradingChartProps = {
  mode: string; symbol: string; timeframe: string; candles: Candle[]; events?: Event[]; cursorTime?: number | null; onEventSelect?: (event: Event) => void;
};

export function TradingChart({ candles, events, cursorTime, onEventSelect }: TradingChartProps) {
  return <TradingChartAdapter candles={candles} events={events} cursorTime={cursorTime} onEventSelect={onEventSelect} />;
}
