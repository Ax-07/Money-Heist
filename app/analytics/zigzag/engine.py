from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .models import CausalZigZagInputBar, CausalZigZagPivot, ZigZagPivotKind
from .registry import CAUSAL_ZIGZAG_REVERSAL_MULTIPLE


@dataclass(frozen=True, slots=True)
class _Candidate:
    kind: ZigZagPivotKind
    index: int
    price: Decimal
    atr: Decimal
    source_cursor_fingerprint: str
    source_indicator_snapshot_fingerprint: str


class CausalZigZagEngine:
    """Deterministic closed-candle ZigZag with explicit causal confirmation."""

    def __init__(
        self,
        *,
        reversal_multiple: float = CAUSAL_ZIGZAG_REVERSAL_MULTIPLE,
    ) -> None:
        if reversal_multiple <= 0:
            raise ValueError("reversal_multiple must be > 0")
        self.reversal_multiple = Decimal(str(reversal_multiple))

    def compute(
        self,
        bars: Sequence[CausalZigZagInputBar],
        *,
        analytics_run_id: str,
    ) -> tuple[CausalZigZagPivot, ...]:
        if not bars:
            return ()
        self._validate_bars(bars)
        first_ready = next(
            (index for index, bar in enumerate(bars) if bar.atr_at_candle is not None),
            None,
        )
        if first_ready is None:
            return ()

        first = bars[first_ready]
        assert first.atr_at_candle is not None
        first_atr = Decimal(str(first.atr_at_candle))
        high_candidate = self._candidate(
            ZigZagPivotKind.HIGH, first_ready, first, first.candle.high, first_atr
        )
        low_candidate = self._candidate(
            ZigZagPivotKind.LOW, first_ready, first, first.candle.low, first_atr
        )

        direction: Literal["seeking_high", "seeking_low"] | None = None
        candidate: _Candidate | None = None
        pivots: list[CausalZigZagPivot] = []

        for index in range(first_ready + 1, len(bars)):
            bar = bars[index]
            if bar.atr_at_candle is None:
                continue
            atr = Decimal(str(bar.atr_at_candle))
            high = bar.candle.high
            low = bar.candle.low

            if direction is None:
                previous_high = high_candidate
                previous_low = low_candidate
                high_updated = high > previous_high.price
                low_updated = low < previous_low.price

                if high_updated:
                    high_candidate = self._candidate(
                        ZigZagPivotKind.HIGH, index, bar, high, atr
                    )
                if low_updated:
                    low_candidate = self._candidate(
                        ZigZagPivotKind.LOW, index, bar, low, atr
                    )

                rise_triggered = high >= (
                    low_candidate.price
                    + self.reversal_multiple * low_candidate.atr
                )
                fall_triggered = low <= (
                    high_candidate.price
                    - self.reversal_multiple * high_candidate.atr
                )

                # OHLC does not reveal whether high or low occurred first.
                if rise_triggered and fall_triggered:
                    continue

                if rise_triggered and not low_updated:
                    pivots.append(
                        self._confirmed(
                            low_candidate,
                            bars,
                            confirmed_index=index,
                            previous=None,
                            analytics_run_id=analytics_run_id,
                        )
                    )
                    direction = "seeking_high"
                    candidate = self._candidate(
                        ZigZagPivotKind.HIGH, index, bar, high, atr
                    )
                elif fall_triggered and not high_updated:
                    pivots.append(
                        self._confirmed(
                            high_candidate,
                            bars,
                            confirmed_index=index,
                            previous=None,
                            analytics_run_id=analytics_run_id,
                        )
                    )
                    direction = "seeking_low"
                    candidate = self._candidate(
                        ZigZagPivotKind.LOW, index, bar, low, atr
                    )
                continue

            assert candidate is not None
            if direction == "seeking_high":
                if high > candidate.price:
                    candidate = self._candidate(
                        ZigZagPivotKind.HIGH, index, bar, high, atr
                    )
                    # Never invent intrabar ordering by confirming a fresh extreme
                    # on the same OHLC candle.
                    continue
                if low <= (
                    candidate.price
                    - self.reversal_multiple * candidate.atr
                ):
                    pivots.append(
                        self._confirmed(
                            candidate,
                            bars,
                            confirmed_index=index,
                            previous=pivots[-1] if pivots else None,
                            analytics_run_id=analytics_run_id,
                        )
                    )
                    direction = "seeking_low"
                    candidate = self._candidate(
                        ZigZagPivotKind.LOW, index, bar, low, atr
                    )
            else:
                if low < candidate.price:
                    candidate = self._candidate(
                        ZigZagPivotKind.LOW, index, bar, low, atr
                    )
                    continue
                if high >= (
                    candidate.price
                    + self.reversal_multiple * candidate.atr
                ):
                    pivots.append(
                        self._confirmed(
                            candidate,
                            bars,
                            confirmed_index=index,
                            previous=pivots[-1] if pivots else None,
                            analytics_run_id=analytics_run_id,
                        )
                    )
                    direction = "seeking_high"
                    candidate = self._candidate(
                        ZigZagPivotKind.HIGH, index, bar, high, atr
                    )

        return tuple(
            sorted(
                pivots,
                key=lambda item: (
                    item.confirmed_at,
                    item.pivot_at,
                    item.kind.value,
                    item.pivot_id,
                ),
            )
        )

    @staticmethod
    def visible_at(
        pivots: Sequence[CausalZigZagPivot],
        *,
        as_of,
    ) -> tuple[CausalZigZagPivot, ...]:
        return tuple(pivot for pivot in pivots if pivot.confirmed_at <= as_of)

    @staticmethod
    def _candidate(
        kind: ZigZagPivotKind,
        index: int,
        bar: CausalZigZagInputBar,
        price: Decimal,
        atr: Decimal,
    ) -> _Candidate:
        return _Candidate(
            kind=kind,
            index=index,
            price=price,
            atr=atr,
            source_cursor_fingerprint=bar.source_cursor_fingerprint,
            source_indicator_snapshot_fingerprint=(
                bar.source_indicator_snapshot_fingerprint
            ),
        )

    def _confirmed(
        self,
        candidate: _Candidate,
        bars: Sequence[CausalZigZagInputBar],
        *,
        confirmed_index: int,
        previous: CausalZigZagPivot | None,
        analytics_run_id: str,
    ) -> CausalZigZagPivot:
        amplitude_pct: Decimal | None = None
        amplitude_atr: Decimal | None = None
        bars_from_previous: int | None = None

        if previous is not None:
            delta = candidate.price - previous.price
            if previous.price != 0:
                amplitude_pct = Decimal("100") * delta / previous.price
            if previous.atr_at_pivot != 0:
                amplitude_atr = delta / previous.atr_at_pivot
            bars_from_previous = candidate.index - previous.candle_index

        confirmation = bars[confirmed_index]
        pivot_bar = bars[candidate.index]
        threshold = self.reversal_multiple * candidate.atr
        return CausalZigZagPivot.create(
            analytics_run_id=analytics_run_id,
            symbol=pivot_bar.candle.symbol,
            timeframe=pivot_bar.candle.timeframe,
            kind=candidate.kind,
            pivot_at=pivot_bar.candle.close_time,
            confirmed_at=confirmation.candle.close_time,
            price=candidate.price,
            atr_at_pivot=candidate.atr,
            reversal_multiple=self.reversal_multiple,
            reversal_threshold=threshold,
            amplitude_pct=amplitude_pct,
            amplitude_atr=amplitude_atr,
            bars_from_previous=bars_from_previous,
            source_cursor_fingerprint=candidate.source_cursor_fingerprint,
            source_indicator_snapshot_fingerprint=(
                candidate.source_indicator_snapshot_fingerprint
            ),
            confirmation_indicator_snapshot_fingerprint=(
                confirmation.source_indicator_snapshot_fingerprint
            ),
            candle_index=candidate.index,
            confirmed_index=confirmed_index,
        )

    @staticmethod
    def _validate_bars(bars: Sequence[CausalZigZagInputBar]) -> None:
        first = bars[0].candle
        last_close = None
        for bar in bars:
            candle = bar.candle
            if candle.symbol != first.symbol or candle.timeframe != first.timeframe:
                raise ValueError("all ZigZag bars must share symbol and timeframe")
            if last_close is not None and candle.close_time <= last_close:
                raise ValueError("ZigZag bars must be strictly chronological")
            last_close = candle.close_time


__all__ = ["CausalZigZagEngine"]
