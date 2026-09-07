from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable

from .models import Candle, MarketSnapshot
from .quality import FreshnessPolicy, build_quality, count_gaps, is_stale, validate_candle_series


def create_market_snapshot(
    *,
    symbol: str,
    source: str,
    observed_at: datetime,
    received_at: datetime,
    now: datetime,
    freshness_policy: FreshnessPolicy,
    last_price: Decimal | None = None,
    candle_sets: dict[str, Iterable[Candle]] | None = None,
    expected_intervals: dict[str, timedelta] | None = None,
    missing_fields: Iterable[str] = (),
) -> MarketSnapshot:
    """Construit un snapshot et calcule ses flags de qualité de façon déterministe."""

    normalized: dict[str, tuple[Candle, ...]] = {}
    total_gaps = 0
    expected_intervals = expected_intervals or {}

    for timeframe, candles in (candle_sets or {}).items():
        interval = expected_intervals.get(timeframe)
        series = validate_candle_series(candles, expected_interval=interval)
        normalized[timeframe] = series
        if interval is not None:
            total_gaps += count_gaps(series, expected_interval=interval)

    stale = is_stale(observed_at, now=now, policy=freshness_policy)
    quality = build_quality(
        stale=stale,
        missing_fields=missing_fields,
        gap_count=total_gaps,
    )

    return MarketSnapshot(
        symbol=symbol,
        source=source,
        observed_at=observed_at,
        received_at=received_at,
        last_price=last_price,
        candles=normalized,
        quality=quality,
    )
