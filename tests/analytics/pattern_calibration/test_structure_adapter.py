from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.pattern_calibration.pivots import pattern_pivots_from_money_heist_structure
from app.analytics.structure import StructureSource
from app.market.models import Candle
from app.market.structure import _strict_pivots

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(i, high, low, close=100):
    start = BASE + timedelta(hours=i)
    return Candle(
        symbol="BTC/EUR",
        timeframe="1h",
        open_time=start,
        close_time=start + timedelta(hours=1),
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("10"),
        is_closed=True,
    )


def test_structure_adapter_confirms_after_right_span_and_is_prefix_stable() -> None:
    candles = tuple(
        _candle(i, high, low)
        for i, (high, low) in enumerate(
            [
                (101, 99),
                (102, 98),
                (110, 97),
                (103, 96),
                (102, 95),
                (103, 94),
                (104, 90),
                (103, 94),
                (102, 95),
                (101, 96),
            ]
        )
    )
    full = pattern_pivots_from_money_heist_structure(candles, span=2)
    prefix = pattern_pivots_from_money_heist_structure(candles[:8], span=2)
    assert full
    assert all(item.source is StructureSource.MONEY_HEIST_STRUCTURE for item in full)
    peak = next(item for item in full if item.kind == "HIGH" and item.candle_index == 2)
    assert peak.confirmed_index == 4
    assert peak.confirmed_at == candles[4].close_time
    full_by_id = {item.pivot_id: item for item in full}
    for item in prefix:
        assert item.pivot_id in full_by_id
        assert item.source_fingerprint == full_by_id[item.pivot_id].source_fingerprint
        assert item.source_cursor_fingerprint == full_by_id[item.pivot_id].source_cursor_fingerprint


def test_structure_adapter_matches_production_strict_pivot_geometry() -> None:
    candles = tuple(
        _candle(i, high, low)
        for i, (high, low) in enumerate(
            [
                (101, 99),
                (102, 98),
                (110, 97),
                (103, 96),
                (102, 95),
                (103, 94),
                (104, 90),
                (103, 94),
                (102, 95),
            ]
        )
    )
    projected = pattern_pivots_from_money_heist_structure(candles, span=2)
    prod_highs, prod_lows = _strict_pivots(candles, span=2)
    expected = {(item.kind, item.close_time, item.price) for item in (*prod_highs, *prod_lows)}
    actual = {(item.kind, item.pivot_at, item.price) for item in projected}
    assert actual == expected
