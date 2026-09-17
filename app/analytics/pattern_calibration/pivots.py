from __future__ import annotations

from collections.abc import Sequence

from app.analytics.patterns.models import PatternPivot
from app.analytics.structure import StructureSource
from app.common.canonical import stable_digest, stable_uuid
from app.market.models import Candle
from app.market.structure import MARKET_STRUCTURE_VERSION

from .registry import MONEY_HEIST_STRUCTURE_PIVOT_ADAPTER_VERSION


def _candle_payload(candle: Candle) -> dict[str, object]:
    return {
        "symbol": candle.symbol,
        "timeframe": candle.timeframe,
        "open_time": candle.open_time,
        "close_time": candle.close_time,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "is_closed": candle.is_closed,
    }


def _atr_series(candles: Sequence[Candle], period: int = 14) -> list[float]:
    true_ranges: list[float] = []
    previous_close: float | None = None
    for candle in candles:
        high = float(candle.high)
        low = float(candle.low)
        close = float(candle.close)
        value = (
            high - low
            if previous_close is None
            else max(high - low, abs(high - previous_close), abs(low - previous_close))
        )
        true_ranges.append(max(value, 1e-12))
        previous_close = close
    result: list[float] = []
    running = 0.0
    for index, value in enumerate(true_ranges):
        running += value
        if index >= period:
            running -= true_ranges[index - period]
        result.append(max(running / min(index + 1, period), 1e-12))
    return result


def _confirmation_cursor_fingerprint(
    candles: Sequence[Candle], confirmed_index: int, *, span: int
) -> str:
    return stable_digest(
        {
            "adapter_version": MONEY_HEIST_STRUCTURE_PIVOT_ADAPTER_VERSION,
            "production_structure_version": MARKET_STRUCTURE_VERSION,
            "span": span,
            "prefix": tuple(_candle_payload(item) for item in candles[: confirmed_index + 1]),
        }
    )


def pattern_pivots_from_money_heist_structure(
    candles: Sequence[Candle], *, span: int
) -> tuple[PatternPivot, ...]:
    """Project production strict-pivot semantics into PatternPivot without production changes."""
    if span < 1:
        raise ValueError("span must be >= 1")
    rows = tuple(candle for candle in candles if candle.is_closed)
    if len(rows) < span * 2 + 1:
        return ()
    symbol = rows[0].symbol
    timeframe = rows[0].timeframe
    if any(item.symbol != symbol or item.timeframe != timeframe for item in rows):
        raise ValueError("structure pivot projection requires one symbol/timeframe")
    for previous, current in zip(rows, rows[1:], strict=False):
        if current.close_time <= previous.close_time:
            raise ValueError("structure pivot candles must be chronological")

    atr = _atr_series(rows)
    pivots: list[PatternPivot] = []
    for index in range(span, len(rows) - span):
        center = rows[index]
        window = rows[index - span : index + span + 1]
        other_highs = [item.high for offset, item in enumerate(window) if offset != span]
        other_lows = [item.low for offset, item in enumerate(window) if offset != span]
        kinds: list[tuple[str, object]] = []
        if center.high > max(other_highs):
            kinds.append(("HIGH", center.high))
        if center.low < min(other_lows):
            kinds.append(("LOW", center.low))
        confirmed_index = index + span
        confirmed_at = rows[confirmed_index].close_time
        cursor_fp = _confirmation_cursor_fingerprint(rows, confirmed_index, span=span)
        for kind, price in kinds:
            identity = {
                "adapter_version": MONEY_HEIST_STRUCTURE_PIVOT_ADAPTER_VERSION,
                "production_structure_version": MARKET_STRUCTURE_VERSION,
                "symbol": symbol,
                "timeframe": timeframe,
                "span": span,
                "kind": kind,
                "price": price,
                "pivot_at": center.close_time,
                "confirmed_at": confirmed_at,
                "candle_index": index,
                "confirmed_index": confirmed_index,
            }
            pivots.append(
                PatternPivot(
                    pivot_id=stable_uuid("analytics-money-heist-structure-pivot", identity),
                    kind=kind,
                    price=price,
                    pivot_at=center.close_time,
                    confirmed_at=confirmed_at,
                    symbol=symbol,
                    timeframe=timeframe,
                    source=StructureSource.MONEY_HEIST_STRUCTURE,
                    source_fingerprint=stable_digest(identity),
                    source_cursor_fingerprint=cursor_fp,
                    atr_at_pivot=str(atr[index]),
                    candle_index=index,
                    confirmed_index=confirmed_index,
                )
            )
    return tuple(
        sorted(pivots, key=lambda item: (item.candle_index, item.confirmed_at, item.pivot_id))
    )
