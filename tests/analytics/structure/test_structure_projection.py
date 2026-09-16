from datetime import UTC, datetime
from decimal import Decimal

from app.analytics.structure import (
    StructureSource,
    project_money_heist_structure,
)
from app.market.structure import (
    BreakoutState,
    MarketStructureContextV1,
    RangeLocation,
    SwingStructure,
    TimeframeStructure,
)

FP = "a" * 64
CTX_FP = "b" * 64


def test_projection_preserves_production_structure_without_recomputation() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    summary = TimeframeStructure(
        timeframe="1h",
        observed_at=now,
        candle_count=30,
        close=Decimal("100"),
        prior_range_high=Decimal("102"),
        prior_range_low=Decimal("95"),
        range_location=RangeLocation.INSIDE_RANGE,
        breakout_state=BreakoutState.INSIDE_RANGE,
        swing_structure=SwingStructure.MIXED,
        previous_swing_high=None,
        latest_swing_high=None,
        previous_swing_low=None,
        latest_swing_low=None,
        missing_fields=("swing_highs", "swing_lows"),
    )
    context = MarketStructureContextV1(
        version="market-structure-v1",
        symbol="BTC/EUR",
        observed_at=now,
        source_cursor_fingerprint=FP,
        range_lookback=20,
        pivot_span=2,
        requested_timeframes=("1h",),
        timeframes={"1h": summary},
        missing_timeframes=(),
        incomplete_timeframes=("1h",),
        context_fingerprint=CTX_FP,
    )
    observation = project_money_heist_structure(context)
    assert observation.source == StructureSource.MONEY_HEIST_STRUCTURE
    assert observation.context is context
    assert observation.as_of == now
    assert observation.source_cursor_fingerprint == FP
