from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.analytics.indicators.models import AnalyticsIndicatorSnapshot, IndicatorValue
from app.analytics.indicators.registry import INDICATOR_REGISTRY
from app.common.canonical import stable_digest


@pytest.fixture
def indicator_snapshot_factory():
    def build(
        index: int,
        *,
        values: dict[str, float | None],
        candle_count: int | None = None,
        symbol: str = "BTC/EUR",
        timeframe: str = "1h",
        warmup_false: set[str] | None = None,
    ) -> AnalyticsIndicatorSnapshot:
        count = candle_count if candle_count is not None else 250 + index
        warmup_false = warmup_false or set()
        items = []
        for definition in INDICATOR_REGISTRY:
            value = values.get(definition.indicator_id)
            available = value is not None
            warmup_complete = available and definition.indicator_id not in warmup_false
            if definition.indicator_id in warmup_false:
                value = None
                available = False
                warmup_complete = False
            items.append(
                IndicatorValue(
                    indicator_id=definition.indicator_id,
                    value=value,
                    available=available,
                    warmup_complete=warmup_complete,
                    definition_version=definition.definition_version,
                )
            )
        as_of = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index)
        return AnalyticsIndicatorSnapshot.create(
            symbol=symbol,
            timeframe=timeframe,
            as_of=as_of,
            source_cursor_fingerprint=stable_digest(
                {"index": index, "count": count, "symbol": symbol, "timeframe": timeframe}
            ),
            candle_count=count,
            values=tuple(items),
        )

    return build
