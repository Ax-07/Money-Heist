from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.structure import (
    ANALYTICS_STRUCTURE_IDENTITY,
    StructureSource,
)
from app.analytics.zigzag import CausalZigZagEngine, CausalZigZagInputBar
from app.analytics.zigzag.integration import canonical_candles_from_mtf_cursor
from app.market.models import Candle
from app.market.multitimeframe import HistoricalMultiTimeframeCursor
from app.market.structure import MARKET_STRUCTURE_VERSION

START = datetime(2026, 1, 1, tzinfo=UTC)
FP_A = "a" * 64
FP_B = "b" * 64


def _candle(index: int, *, high: str, low: str, timeframe: str = "1h") -> Candle:
    open_time = START + timedelta(hours=index)
    close_time = open_time + timedelta(hours=1)
    high_d = Decimal(high)
    low_d = Decimal(low)
    close = (high_d + low_d) / Decimal("2")
    return Candle(
        symbol="BTC/EUR",
        timeframe=timeframe,
        open_time=open_time,
        close_time=close_time,
        open=close,
        high=high_d,
        low=low_d,
        close=close,
        volume=Decimal("1"),
        is_closed=True,
    )


def _bar(index: int, *, high: str, low: str, atr: float = 2.0) -> CausalZigZagInputBar:
    return CausalZigZagInputBar(
        candle=_candle(index, high=high, low=low),
        atr_at_candle=atr,
        source_cursor_fingerprint=FP_A,
        source_indicator_snapshot_fingerprint=FP_B,
    )


def test_zigzag_pivot_not_available_before_confirmation() -> None:
    bars = (
        _bar(0, high="100", low="98"),
        _bar(1, high="103", low="100"),
        _bar(2, high="106", low="103"),
        _bar(3, high="105", low="102"),
    )
    engine = CausalZigZagEngine(reversal_multiple=2.0)
    pivots = engine.compute(bars, analytics_run_id="run-1")
    target = next(p for p in pivots if p.pivot_at == bars[2].candle.close_time)

    assert target not in engine.visible_at(pivots, as_of=bars[2].candle.close_time)
    assert target in engine.visible_at(pivots, as_of=bars[3].candle.close_time)


def test_zigzag_replay_is_deterministic() -> None:
    bars = (
        _bar(0, high="100", low="98"),
        _bar(1, high="103", low="100"),
        _bar(2, high="106", low="103"),
        _bar(3, high="105", low="102"),
        _bar(4, high="103", low="99"),
        _bar(5, high="104", low="100"),
    )
    engine = CausalZigZagEngine(reversal_multiple=2.0)
    first = engine.compute(bars, analytics_run_id="run-1")
    second = engine.compute(bars, analytics_run_id="run-1")

    assert first == second
    assert [pivot.pivot_id for pivot in first] == [pivot.pivot_id for pivot in second]
    assert [pivot.pivot_fingerprint for pivot in first] == [
        pivot.pivot_fingerprint for pivot in second
    ]


def test_incomplete_4h_candle_is_invisible_to_zigzag_source() -> None:
    cursor = HistoricalMultiTimeframeCursor(
        source_timeframe="1h",
        target_timeframes=("1h", "4h"),
    )
    for index in range(3):
        cursor.push(_candle(index, high=str(100 + index), low=str(98 + index)))

    assert len(cursor.series("1h")) == 3
    assert cursor.series("4h") == ()
    assert canonical_candles_from_mtf_cursor(
        mtf_cursor=cursor,
        timeframe="4h",
        as_of=cursor.state().as_of,
    ) == ()

    cursor.push(_candle(3, high="103", low="101"))
    closed_4h = canonical_candles_from_mtf_cursor(
        mtf_cursor=cursor,
        timeframe="4h",
        as_of=cursor.state().as_of,
    )
    assert len(closed_4h) == 1
    assert closed_4h[0].close_time == START + timedelta(hours=4)


def test_structure_sources_and_identity_remain_explicitly_distinct() -> None:
    assert StructureSource.MONEY_HEIST_STRUCTURE != StructureSource.CAUSAL_ZIGZAG
    assert MARKET_STRUCTURE_VERSION in ANALYTICS_STRUCTURE_IDENTITY
