import type { BacktestReplay } from "@/lib/api/schemas";

export type ReplaySpeed = 1 | 2 | 5 | 10;
export type ReplayCursor = { index: number; playing: boolean; speed: ReplaySpeed };

export function clampIndex(index: number, candleCount: number): number {
  if (candleCount <= 0) return 0;
  return Math.max(0, Math.min(index, candleCount - 1));
}

export function eventIndex(replay: BacktestReplay, fromIndex: number, direction: 1 | -1): number {
  if (replay.candles.length === 0) return 0;
  const current = replay.candles[clampIndex(fromIndex, replay.candles.length)]?.time ?? 0;
  const eventTimes = replay.events.map((event) => Math.floor(new Date(event.observed_at).getTime() / 1000));
  const target = direction === 1
    ? eventTimes.find((time) => time > current)
    : eventTimes.slice().reverse().find((time) => time < current);
  if (target === undefined) return direction === 1 ? replay.candles.length - 1 : 0;
  let nearest = 0;
  let distance = Number.POSITIVE_INFINITY;
  replay.candles.forEach((candle, index) => {
    const next = Math.abs(candle.time - target);
    if (next < distance) { nearest = index; distance = next; }
  });
  return nearest;
}
