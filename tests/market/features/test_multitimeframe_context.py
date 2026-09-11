from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market.features import FeatureEngine
from app.market.features.multitimeframe import (
    build_multi_timeframe_feature_context,
)
from app.market.models import Candle
from app.market.multitimeframe import HistoricalMultiTimeframeCursor


def _series(*, start: datetime, count: int, timeframe: str):
    interval = {
        "1m": timedelta(minutes=1),
        "1h": timedelta(hours=1),
    }[timeframe]
    output = []
    for index in range(count):
        opened = start + index * interval
        price = Decimal("100") + Decimal(index) / Decimal("100")
        output.append(
            Candle(
                symbol="BTC/USDC",
                timeframe=timeframe,
                open_time=opened,
                close_time=opened + interval,
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=price + Decimal("0.25"),
                volume=Decimal(index + 1),
                is_closed=True,
            )
        )
    return tuple(output)


def test_context_marks_missing_and_reuses_decision_feature():
    source = _series(
        start=datetime(2026, 9, 1, tzinfo=UTC),
        count=60,
        timeframe="1m",
    )
    cursor = HistoricalMultiTimeframeCursor(
        source_timeframe="1m",
        target_timeframes=("15m", "1h", "4h", "1d"),
    )
    for candle in source:
        cursor.push(candle)

    engine = FeatureEngine()
    decision_series = cursor.series("1h")
    decision = engine.compute(
        decision_series,
        symbol="BTC/USDC",
        timeframe="1h",
        observed_at=source[-1].close_time,
    )
    context = build_multi_timeframe_feature_context(
        feature_engine=engine,
        mtf_cursor=cursor,
        observed_at=source[-1].close_time,
        decision_timeframe="1h",
        decision_feature=decision,
    )

    assert context.decision_snapshot is decision
    assert set(context.snapshots) == {"15m", "1h"}
    assert context.missing_timeframes == ("1d", "4h")
    assert set(context.warmup_incomplete_timeframes) == {"15m", "1h"}
    assert context.all_timeframes_available is False
    assert context.all_warmups_complete is False


def test_context_fingerprint_is_deterministic():
    source = _series(
        start=datetime(2026, 9, 1, tzinfo=UTC),
        count=4 * 60,
        timeframe="1m",
    )
    cursor = HistoricalMultiTimeframeCursor(
        source_timeframe="1m",
        target_timeframes=("15m", "1h", "4h", "1d"),
    )
    for candle in source:
        cursor.push(candle)

    engine = FeatureEngine()
    first = build_multi_timeframe_feature_context(
        feature_engine=engine,
        mtf_cursor=cursor,
        observed_at=source[-1].close_time,
        decision_timeframe="1h",
    )
    second = build_multi_timeframe_feature_context(
        feature_engine=engine,
        mtf_cursor=cursor,
        observed_at=source[-1].close_time,
        decision_timeframe="1h",
    )

    assert first.context_fingerprint == second.context_fingerprint
    assert first.snapshots == second.snapshots
    assert first.missing_timeframes == ("1d",)


def test_daily_warmup_becomes_complete_after_35_closed_daily_bars():
    source = _series(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        count=35 * 24,
        timeframe="1h",
    )
    cursor = HistoricalMultiTimeframeCursor(
        source_timeframe="1h",
        target_timeframes=("1h", "4h", "1d"),
    )
    for candle in source:
        cursor.push(candle)

    engine = FeatureEngine()
    context = build_multi_timeframe_feature_context(
        feature_engine=engine,
        mtf_cursor=cursor,
        observed_at=source[-1].close_time,
        decision_timeframe="1h",
    )

    assert len(cursor.series("1d")) == 35
    assert context.snapshots["1d"].quality.warmup_complete is True
    assert context.all_warmups_complete is True
