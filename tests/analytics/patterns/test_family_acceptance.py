from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.analytics.patterns.engine import patterns_at
from app.analytics.patterns.models import PatternPivot
from app.analytics.patterns.registry import PatternType
from app.analytics.structure import StructureSource
from app.market.models import Candle

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _candles(
    count: int = 24,
    *,
    timeframe: str = "1h",
    step_hours: int = 1,
) -> tuple[Candle, ...]:
    rows: list[Candle] = []
    for index in range(count):
        start = BASE + timedelta(hours=index * step_hours)
        rows.append(
            Candle(
                symbol="BTC/USDC",
                timeframe=timeframe,
                open_time=start,
                close_time=start + timedelta(hours=step_hours),
                open=Decimal("120"),
                high=Decimal("125"),
                low=Decimal("115"),
                close=Decimal("120"),
                volume=Decimal("10"),
                is_closed=True,
            )
        )
    return tuple(rows)


def _pivot(
    index: int,
    kind: str,
    price: float | int,
    *,
    timeframe: str = "1h",
    step_hours: int = 1,
    atr: str = "10",
    source: StructureSource = StructureSource.CAUSAL_ZIGZAG,
) -> PatternPivot:
    return PatternPivot(
        pivot_id=f"pivot-{index}-{kind.lower()}",
        kind=kind,
        price=Decimal(str(price)),
        pivot_at=BASE + timedelta(hours=index * step_hours),
        confirmed_at=BASE + timedelta(hours=(index + 1) * step_hours),
        symbol="BTC/USDC",
        timeframe=timeframe,
        source=source,
        source_fingerprint=f"{index + 1:064x}"[-64:],
        source_cursor_fingerprint="a" * 64,
        atr_at_pivot=Decimal(atr),
        candle_index=index,
        confirmed_index=index,
    )


def _detect(
    pivots: tuple[PatternPivot, ...],
    *,
    candles: tuple[Candle, ...] | None = None,
):
    visible_candles = candles or _candles()
    return patterns_at(
        candles=visible_candles,
        pivots=pivots,
        as_of=visible_candles[-1].close_time,
        analytics_run_id="run-acceptance",
        source_cursor_fingerprint="f" * 64,
    )


@pytest.mark.parametrize(
    ("expected", "points"),
    [
        (
            PatternType.DOUBLE_TOP,
            ((2, "HIGH", 110), (5, "LOW", 100), (8, "HIGH", 110)),
        ),
        (
            PatternType.DOUBLE_BOTTOM,
            ((2, "LOW", 100), (5, "HIGH", 110), (8, "LOW", 100)),
        ),
        (
            PatternType.HEAD_AND_SHOULDERS,
            (
                (1, "HIGH", 108),
                (3, "LOW", 100),
                (5, "HIGH", 112),
                (7, "LOW", 101),
                (9, "HIGH", 108),
            ),
        ),
        (
            PatternType.INVERSE_HEAD_AND_SHOULDERS,
            (
                (1, "LOW", 102),
                (3, "HIGH", 110),
                (5, "LOW", 98),
                (7, "HIGH", 109),
                (9, "LOW", 102),
            ),
        ),
    ],
)
def test_reversal_family_is_detected_by_full_engine(
    expected: PatternType,
    points: tuple[tuple[int, str, int], ...],
) -> None:
    pivots = tuple(_pivot(index, kind, price, atr="4") for index, kind, price in points)
    detected = _detect(pivots)
    assert expected in {pattern.pattern_type for pattern in detected}


GEOMETRIES = {
    PatternType.ASCENDING_TRIANGLE: (0.0, 1.5),
    PatternType.DESCENDING_TRIANGLE: (-1.5, 0.0),
    PatternType.SYMMETRICAL_TRIANGLE: (-0.75, 0.75),
    PatternType.RISING_WEDGE: (0.5, 1.5),
    PatternType.FALLING_WEDGE: (-1.5, -0.5),
    PatternType.ASCENDING_CHANNEL: (0.8, 0.75),
    PatternType.DESCENDING_CHANNEL: (-0.8, -0.75),
    PatternType.RANGE: (0.0, 0.0),
}


@pytest.mark.parametrize(("expected", "slopes"), GEOMETRIES.items())
def test_geometry_family_is_detected_by_full_engine(
    expected: PatternType,
    slopes: tuple[float, float],
) -> None:
    high_slope, low_slope = slopes
    pivots: list[PatternPivot] = []
    for index, kind in (
        (0, "HIGH"),
        (2, "LOW"),
        (4, "HIGH"),
        (6, "LOW"),
        (8, "HIGH"),
        (10, "LOW"),
    ):
        intercept = 140.0 if kind == "HIGH" else 100.0
        slope = high_slope if kind == "HIGH" else low_slope
        pivots.append(_pivot(index, kind, intercept + slope * index))
    detected = _detect(tuple(pivots))
    assert expected in {pattern.pattern_type for pattern in detected}
