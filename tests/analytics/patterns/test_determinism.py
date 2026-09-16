from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.patterns.engine import patterns_at
from app.analytics.patterns.models import PatternPivot
from app.analytics.structure import StructureSource
from app.market.models import Candle

BASE = datetime(2026, 2, 1, tzinfo=UTC)


def _candles() -> tuple[Candle, ...]:
    return tuple(
        Candle(
            symbol="BTC/USDC",
            timeframe="1h",
            open_time=BASE + timedelta(hours=index),
            close_time=BASE + timedelta(hours=index + 1),
            open=Decimal("105"),
            high=Decimal("106"),
            low=Decimal("104"),
            close=Decimal("105"),
            volume=Decimal("10"),
            is_closed=True,
        )
        for index in range(18)
    )


def _pivots(source: StructureSource) -> tuple[PatternPivot, ...]:
    values = (
        (2, "HIGH", "110"),
        (5, "LOW", "100"),
        (8, "HIGH", "110"),
    )
    return tuple(
        PatternPivot(
            pivot_id=f"pivot-{index}-{kind.lower()}",
            kind=kind,
            price=Decimal(price),
            pivot_at=BASE + timedelta(hours=index),
            confirmed_at=BASE + timedelta(hours=index + 1),
            symbol="BTC/USDC",
            timeframe="1h",
            source=source,
            source_fingerprint=f"{index + 1:064x}"[-64:],
            source_cursor_fingerprint="a" * 64,
            atr_at_pivot=Decimal("4"),
            candle_index=index,
            confirmed_index=index,
        )
        for index, kind, price in values
    )


def _run(source: StructureSource):
    candles = _candles()
    return patterns_at(
        candles=candles,
        pivots=_pivots(source),
        as_of=candles[-1].close_time,
        analytics_run_id="run-deterministic",
        source_cursor_fingerprint="f" * 64,
    )


def test_pattern_results_are_deterministic_for_identical_inputs() -> None:
    first = _run(StructureSource.CAUSAL_ZIGZAG)
    second = _run(StructureSource.CAUSAL_ZIGZAG)
    assert [(item.pattern_id, item.current_status, item.pattern_fingerprint) for item in first] == [
        (item.pattern_id, item.current_status, item.pattern_fingerprint) for item in second
    ]


def test_distinct_pivot_sources_produce_distinct_pattern_fingerprints() -> None:
    zigzag = _run(StructureSource.CAUSAL_ZIGZAG)
    structure = _run(StructureSource.MONEY_HEIST_STRUCTURE)
    assert zigzag
    assert structure
    assert zigzag[0].pattern_id != structure[0].pattern_id
    assert zigzag[0].pattern_fingerprint != structure[0].pattern_fingerprint
