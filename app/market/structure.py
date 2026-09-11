from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from app.market.models import Candle
from app.market.multitimeframe import HistoricalMultiTimeframeCursor


MARKET_STRUCTURE_VERSION = "market-structure-v1"


class SwingStructure(StrEnum):
    BULLISH_HH_HL = "BULLISH_HH_HL"
    BEARISH_LH_LL = "BEARISH_LH_LL"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class BreakoutState(StrEnum):
    BREAKOUT_UP = "BREAKOUT_UP"
    BREAKOUT_DOWN = "BREAKOUT_DOWN"
    RETEST_UP = "RETEST_UP"
    RETEST_DOWN = "RETEST_DOWN"
    FALSE_BREAK_UP = "FALSE_BREAK_UP"
    FALSE_BREAK_DOWN = "FALSE_BREAK_DOWN"
    SWEEP_BOTH = "SWEEP_BOTH"
    INSIDE_RANGE = "INSIDE_RANGE"
    UNKNOWN = "UNKNOWN"


class RangeLocation(StrEnum):
    ABOVE_RANGE = "ABOVE_RANGE"
    BELOW_RANGE = "BELOW_RANGE"
    INSIDE_RANGE = "INSIDE_RANGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class SwingPoint:
    kind: str
    price: Decimal
    close_time: datetime

    def __post_init__(self) -> None:
        if self.kind not in {"HIGH", "LOW"}:
            raise ValueError("SwingPoint.kind must be HIGH or LOW")
        if self.close_time.tzinfo is None or self.close_time.utcoffset() is None:
            raise ValueError("SwingPoint.close_time must be timezone-aware")
        object.__setattr__(self, "close_time", self.close_time.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class TimeframeStructure:
    timeframe: str
    observed_at: datetime
    candle_count: int
    close: Decimal
    prior_range_high: Decimal | None
    prior_range_low: Decimal | None
    range_location: RangeLocation
    breakout_state: BreakoutState
    swing_structure: SwingStructure
    previous_swing_high: SwingPoint | None
    latest_swing_high: SwingPoint | None
    previous_swing_low: SwingPoint | None
    latest_swing_low: SwingPoint | None
    orderbook_available: bool = False
    liquidation_data_available: bool = False
    missing_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        timeframe = self.timeframe.strip().lower()
        if not timeframe:
            raise ValueError("timeframe must not be empty")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.candle_count <= 0:
            raise ValueError("candle_count must be greater than zero")
        if self.orderbook_available:
            raise ValueError("OHLCV structure context cannot claim orderbook availability")
        if self.liquidation_data_available:
            raise ValueError("OHLCV structure context cannot claim liquidation availability")
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))
        object.__setattr__(
            self,
            "missing_fields",
            tuple(sorted(set(self.missing_fields))),
        )

    @property
    def structure_ready(self) -> bool:
        return not self.missing_fields


@dataclass(frozen=True, slots=True)
class MarketStructureContextV1:
    version: str
    symbol: str
    observed_at: datetime
    source_cursor_fingerprint: str
    range_lookback: int
    pivot_span: int
    requested_timeframes: tuple[str, ...]
    timeframes: Mapping[str, TimeframeStructure]
    missing_timeframes: tuple[str, ...]
    incomplete_timeframes: tuple[str, ...]
    context_fingerprint: str

    def __post_init__(self) -> None:
        version = self.version.strip()
        symbol = self.symbol.strip()
        if not version or not symbol:
            raise ValueError("structure version and symbol must not be empty")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.range_lookback < 2:
            raise ValueError("range_lookback must be at least 2")
        if self.pivot_span < 1:
            raise ValueError("pivot_span must be at least 1")
        source_fp = self.source_cursor_fingerprint.strip().lower()
        if len(source_fp) != 64 or any(
            char not in "0123456789abcdef" for char in source_fp
        ):
            raise ValueError("source_cursor_fingerprint must be a SHA-256 hex digest")
        digest = self.context_fingerprint.strip().lower()
        if len(digest) != 64 or any(
            char not in "0123456789abcdef" for char in digest
        ):
            raise ValueError("context_fingerprint must be a SHA-256 hex digest")

        requested = tuple(item.strip().lower() for item in self.requested_timeframes)
        if not requested or len(set(requested)) != len(requested):
            raise ValueError("requested_timeframes must be non-empty and unique")
        frozen = MappingProxyType(dict(sorted(self.timeframes.items())))
        if not set(frozen).issubset(set(requested)):
            raise ValueError("structure timeframe is not requested")
        if any(item.timeframe != key for key, item in frozen.items()):
            raise ValueError("structure timeframe key mismatch")
        if any(item.observed_at != self.observed_at for item in frozen.values()):
            raise ValueError("all structure summaries must share observed_at")

        expected_missing = set(requested) - set(frozen)
        if set(self.missing_timeframes) != expected_missing:
            raise ValueError("missing_timeframes does not match absent summaries")
        expected_incomplete = {
            key for key, item in frozen.items() if not item.structure_ready
        }
        if set(self.incomplete_timeframes) != expected_incomplete:
            raise ValueError(
                "incomplete_timeframes does not match summary missing_fields"
            )

        object.__setattr__(self, "version", version)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))
        object.__setattr__(self, "source_cursor_fingerprint", source_fp)
        object.__setattr__(self, "requested_timeframes", requested)
        object.__setattr__(self, "timeframes", frozen)
        object.__setattr__(
            self,
            "missing_timeframes",
            tuple(sorted(expected_missing)),
        )
        object.__setattr__(
            self,
            "incomplete_timeframes",
            tuple(sorted(expected_incomplete)),
        )
        object.__setattr__(self, "context_fingerprint", digest)

    @property
    def all_timeframes_available(self) -> bool:
        return not self.missing_timeframes

    @property
    def all_structures_ready(self) -> bool:
        return self.all_timeframes_available and not self.incomplete_timeframes

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "symbol": self.symbol,
            "observed_at": _dt(self.observed_at),
            "source_cursor_fingerprint": self.source_cursor_fingerprint,
            "range_lookback": self.range_lookback,
            "pivot_span": self.pivot_span,
            "requested_timeframes": list(self.requested_timeframes),
            "timeframes": {
                key: _summary_payload(value)
                for key, value in sorted(self.timeframes.items())
            },
            "missing_timeframes": list(self.missing_timeframes),
            "incomplete_timeframes": list(self.incomplete_timeframes),
            "context_fingerprint": self.context_fingerprint,
        }


def _dt(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not value.is_finite():
        raise ValueError("structure decimals must be finite")
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _swing_payload(value: SwingPoint | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "kind": value.kind,
        "price": _decimal(value.price),
        "close_time": _dt(value.close_time),
    }


def _summary_payload(value: TimeframeStructure) -> dict[str, Any]:
    return {
        "timeframe": value.timeframe,
        "observed_at": _dt(value.observed_at),
        "candle_count": value.candle_count,
        "close": _decimal(value.close),
        "prior_range_high": _decimal(value.prior_range_high),
        "prior_range_low": _decimal(value.prior_range_low),
        "range_location": value.range_location.value,
        "breakout_state": value.breakout_state.value,
        "swing_structure": value.swing_structure.value,
        "previous_swing_high": _swing_payload(value.previous_swing_high),
        "latest_swing_high": _swing_payload(value.latest_swing_high),
        "previous_swing_low": _swing_payload(value.previous_swing_low),
        "latest_swing_low": _swing_payload(value.latest_swing_low),
        "orderbook_available": value.orderbook_available,
        "liquidation_data_available": value.liquidation_data_available,
        "missing_fields": list(value.missing_fields),
    }


def _strict_pivots(
    candles: tuple[Candle, ...],
    *,
    span: int,
) -> tuple[list[SwingPoint], list[SwingPoint]]:
    highs: list[SwingPoint] = []
    lows: list[SwingPoint] = []
    if len(candles) < span * 2 + 1:
        return highs, lows

    for index in range(span, len(candles) - span):
        center = candles[index]
        window = candles[index - span : index + span + 1]
        other_highs = [
            item.high for offset, item in enumerate(window) if offset != span
        ]
        other_lows = [
            item.low for offset, item in enumerate(window) if offset != span
        ]
        if center.high > max(other_highs):
            highs.append(
                SwingPoint(
                    kind="HIGH",
                    price=center.high,
                    close_time=center.close_time,
                )
            )
        if center.low < min(other_lows):
            lows.append(
                SwingPoint(
                    kind="LOW",
                    price=center.low,
                    close_time=center.close_time,
                )
            )
    return highs, lows


def _swing_structure(
    highs: list[SwingPoint],
    lows: list[SwingPoint],
) -> SwingStructure:
    if len(highs) < 2 or len(lows) < 2:
        return SwingStructure.UNKNOWN
    higher_high = highs[-1].price > highs[-2].price
    higher_low = lows[-1].price > lows[-2].price
    lower_high = highs[-1].price < highs[-2].price
    lower_low = lows[-1].price < lows[-2].price
    if higher_high and higher_low:
        return SwingStructure.BULLISH_HH_HL
    if lower_high and lower_low:
        return SwingStructure.BEARISH_LH_LL
    return SwingStructure.MIXED


def _prior_range(
    candles: tuple[Candle, ...],
    *,
    lookback: int,
    exclude: int = 1,
) -> tuple[Decimal | None, Decimal | None]:
    required = lookback + exclude
    if len(candles) < required:
        return None, None
    stop = len(candles) - exclude
    start = stop - lookback
    window = candles[start:stop]
    return (
        max(item.high for item in window),
        min(item.low for item in window),
    )


def _range_location(
    close: Decimal,
    high: Decimal | None,
    low: Decimal | None,
) -> RangeLocation:
    if high is None or low is None:
        return RangeLocation.UNKNOWN
    if close > high:
        return RangeLocation.ABOVE_RANGE
    if close < low:
        return RangeLocation.BELOW_RANGE
    return RangeLocation.INSIDE_RANGE


def _breakout_state(
    candles: tuple[Candle, ...],
    *,
    lookback: int,
    prior_high: Decimal | None,
    prior_low: Decimal | None,
) -> BreakoutState:
    if prior_high is None or prior_low is None:
        return BreakoutState.UNKNOWN

    current = candles[-1]
    swept_high = current.high > prior_high and current.close <= prior_high
    swept_low = current.low < prior_low and current.close >= prior_low
    if swept_high and swept_low:
        return BreakoutState.SWEEP_BOTH
    if swept_high:
        return BreakoutState.FALSE_BREAK_UP
    if swept_low:
        return BreakoutState.FALSE_BREAK_DOWN

    ref_high, ref_low = _prior_range(
        candles,
        lookback=lookback,
        exclude=2,
    )
    if (
        len(candles) >= 2
        and ref_high is not None
        and candles[-2].close > ref_high
        and current.low <= ref_high
        and current.close > ref_high
    ):
        return BreakoutState.RETEST_UP
    if (
        len(candles) >= 2
        and ref_low is not None
        and candles[-2].close < ref_low
        and current.high >= ref_low
        and current.close < ref_low
    ):
        return BreakoutState.RETEST_DOWN

    if current.close > prior_high:
        return BreakoutState.BREAKOUT_UP
    if current.close < prior_low:
        return BreakoutState.BREAKOUT_DOWN
    return BreakoutState.INSIDE_RANGE


def _summary(
    candles: tuple[Candle, ...],
    *,
    observed_at: datetime,
    lookback: int,
    pivot_span: int,
) -> TimeframeStructure:
    if not candles:
        raise ValueError("structure summary requires at least one candle")
    if any(not item.is_closed for item in candles):
        raise ValueError("structure context requires closed candles only")
    if any(item.close_time > observed_at for item in candles):
        raise ValueError("lookahead rejected: structure candle closes after observed_at")

    prior_high, prior_low = _prior_range(candles, lookback=lookback)
    pivot_highs, pivot_lows = _strict_pivots(candles, span=pivot_span)
    swing = _swing_structure(pivot_highs, pivot_lows)

    missing: list[str] = []
    if prior_high is None or prior_low is None:
        missing.append("prior_range")
    if len(pivot_highs) < 2:
        missing.append("swing_highs")
    if len(pivot_lows) < 2:
        missing.append("swing_lows")

    return TimeframeStructure(
        timeframe=candles[-1].timeframe,
        observed_at=observed_at,
        candle_count=len(candles),
        close=candles[-1].close,
        prior_range_high=prior_high,
        prior_range_low=prior_low,
        range_location=_range_location(
            candles[-1].close,
            prior_high,
            prior_low,
        ),
        breakout_state=_breakout_state(
            candles,
            lookback=lookback,
            prior_high=prior_high,
            prior_low=prior_low,
        ),
        swing_structure=swing,
        previous_swing_high=pivot_highs[-2] if len(pivot_highs) >= 2 else None,
        latest_swing_high=pivot_highs[-1] if pivot_highs else None,
        previous_swing_low=pivot_lows[-2] if len(pivot_lows) >= 2 else None,
        latest_swing_low=pivot_lows[-1] if pivot_lows else None,
        missing_fields=tuple(missing),
    )


def build_market_structure_context(
    *,
    mtf_cursor: HistoricalMultiTimeframeCursor,
    observed_at: datetime,
    version: str = MARKET_STRUCTURE_VERSION,
    range_lookback: int = 20,
    pivot_span: int = 2,
) -> MarketStructureContextV1:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    observed_at = observed_at.astimezone(UTC)
    state = mtf_cursor.state()
    if state.as_of != observed_at:
        raise ValueError(
            "MTF cursor as_of must equal market-structure observed_at"
        )

    summaries: dict[str, TimeframeStructure] = {}
    missing: list[str] = []
    incomplete: list[str] = []
    for timeframe in mtf_cursor.target_timeframes:
        series = mtf_cursor.series(timeframe)
        if not series:
            missing.append(timeframe)
            continue
        summary = _summary(
            series,
            observed_at=observed_at,
            lookback=range_lookback,
            pivot_span=pivot_span,
        )
        summaries[timeframe] = summary
        if not summary.structure_ready:
            incomplete.append(timeframe)

    base_payload = {
        "schema": "money-heist.market-structure.v1",
        "version": version,
        "symbol": state.symbol,
        "observed_at": _dt(observed_at),
        "source_cursor_fingerprint": state.cursor_fingerprint,
        "range_lookback": range_lookback,
        "pivot_span": pivot_span,
        "requested_timeframes": list(mtf_cursor.target_timeframes),
        "timeframes": {
            key: _summary_payload(value)
            for key, value in sorted(summaries.items())
        },
        "missing_timeframes": sorted(missing),
        "incomplete_timeframes": sorted(incomplete),
    }
    digest = hashlib.sha256(
        json.dumps(
            base_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()

    return MarketStructureContextV1(
        version=version,
        symbol=state.symbol,
        observed_at=observed_at,
        source_cursor_fingerprint=state.cursor_fingerprint,
        range_lookback=range_lookback,
        pivot_span=pivot_span,
        requested_timeframes=mtf_cursor.target_timeframes,
        timeframes=summaries,
        missing_timeframes=tuple(sorted(missing)),
        incomplete_timeframes=tuple(sorted(incomplete)),
        context_fingerprint=digest,
    )
