from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics.events import TechnicalEventEngine
from app.analytics.indicators import AnalyticsIndicatorEngine
from app.common.canonical import stable_digest
from app.market.models import Candle


def _scenario() -> list[Candle]:
    """Build one deterministic regime sequence that exercises real 24A.2 indicators."""

    base = datetime(2026, 1, 1, tzinfo=UTC)
    closes: list[float] = []
    # Non-zero low-volatility seed keeps Bollinger width defined and ADX initially muted.
    for index in range(45):
        closes.append(100.0 + (0.15 if index % 2 else -0.15))
    # A directional selloff creates bearish momentum/strength/band transitions.
    price = closes[-1]
    for _ in range(35):
        price -= 0.8
        closes.append(price)
    # A strong reversal creates bullish EMA/RSI/MACD transitions.
    for _ in range(60):
        price += 1.4
        closes.append(price)

    output: list[Candle] = []
    for index, close_value in enumerate(closes):
        open_time = base + timedelta(hours=index)
        close = Decimal(str(close_value))
        volume = Decimal("250" if index == 80 else "100")
        output.append(
            Candle(
                symbol="BTC/EUR",
                timeframe="1h",
                open_time=open_time,
                close_time=open_time + timedelta(hours=1),
                open=close,
                high=close + Decimal("0.6"),
                low=close - Decimal("0.6"),
                close=close,
                volume=volume,
                is_closed=True,
            )
        )
    return output


def _scan(candles: list[Candle]) -> set[str]:
    indicator_engine = AnalyticsIndicatorEngine()
    event_engine = TechnicalEventEngine()
    previous = None
    observed: set[str] = set()
    for index, candle in enumerate(candles):
        current = indicator_engine.compute(
            candles,
            symbol="BTC/EUR",
            timeframe="1h",
            as_of=candle.close_time,
            source_cursor_fingerprint=stable_digest({"cursor": index}),
        )
        observed.update(
            event.event_type
            for event in event_engine.detect(previous, current, analytics_run_id="run-real")
        )
        previous = current
    return observed


def test_real_indicator_engine_produces_representative_technical_events() -> None:
    observed = _scan(_scenario())
    expected = {
        "EMA_9_CROSS_ABOVE_EMA_20",
        "RSI_14_ENTER_OVERSOLD",
        "MACD_HISTOGRAM_CROSS_ABOVE_ZERO",
        "ADX_14_CROSS_ABOVE_25",
        "PRICE_BREAK_BELOW_BOLLINGER_LOWER",
        "VOLUME_SPIKE_20",
    }
    assert expected <= observed
