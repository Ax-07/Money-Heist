from __future__ import annotations

from datetime import datetime, timezone

from app.market.features import FeatureQuality, FeatureSnapshot, MarketRegime
from app.market.scanner import DeterministicScanner, ScannerConfig, ScannerTrigger


def feature(**overrides: object) -> FeatureSnapshot:
    data = dict(
        feature_version="feature-engine-v1",
        snapshot_id="snap-1",
        symbol="BTCUSDT",
        timeframe="5m",
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        candle_count=60,
        close=100.0,
        ema_fast=101.0,
        ema_slow=100.0,
        ema_spread_pct=1.0,
        rsi_14=50.0,
        atr_14=1.0,
        atr_pct=1.0,
        atr_expansion_ratio=1.0,
        adx_14=10.0,
        volume_sma_20=1000.0,
        volume_ratio=1.0,
        prior_range_high_20=110.0,
        prior_range_low_20=90.0,
        distance_to_range_high_pct=-9.0,
        distance_to_range_low_pct=11.0,
        regime=MarketRegime.RANGE,
        quality=FeatureQuality(warmup_complete=True, closed_candle_count=60),
    )
    data.update(overrides)
    return FeatureSnapshot(**data)


def test_low_interest_snapshot_creates_no_opportunity() -> None:
    result = DeterministicScanner().scan(feature(), system_id="balanced_v1")
    assert result.score == 0
    assert result.opportunity is None


def test_range_break_alone_reaches_default_threshold() -> None:
    result = DeterministicScanner().scan(
        feature(distance_to_range_high_pct=0.2), system_id="balanced_v1"
    )
    assert ScannerTrigger.RANGE_BREAK in result.triggers
    assert result.opportunity is not None
    assert result.opportunity.priority_score == 35


def test_volume_and_volatility_expansion_are_scored() -> None:
    result = DeterministicScanner().scan(
        feature(volume_ratio=2.1, atr_expansion_ratio=1.5), system_id="balanced_v1"
    )
    assert result.score == 40
    assert result.opportunity is not None
    assert set(result.triggers) == {
        ScannerTrigger.VOLUME_EXPANSION,
        ScannerTrigger.VOLATILITY_EXPANSION,
    }


def test_scanner_output_contains_no_direction_field() -> None:
    result = DeterministicScanner().scan(
        feature(distance_to_range_high_pct=0.2), system_id="balanced_v1"
    )
    assert result.opportunity is not None
    dumped = result.opportunity.model_dump()
    assert "side" not in dumped
    assert "direction" not in dumped


def test_regime_change_requires_same_symbol_and_timeframe() -> None:
    scanner = DeterministicScanner(ScannerConfig(min_priority_score=1))
    previous = feature(regime=MarketRegime.RANGE)
    current = feature(snapshot_id="snap-2", regime=MarketRegime.BULLISH_TREND)
    changed = scanner.scan(current, system_id="balanced_v1", previous=previous)
    assert ScannerTrigger.REGIME_CHANGE in changed.triggers

    other_symbol = feature(snapshot_id="snap-3", symbol="ETHUSDT", regime=MarketRegime.BULLISH_TREND)
    unchanged = scanner.scan(other_symbol, system_id="balanced_v1", previous=previous)
    assert ScannerTrigger.REGIME_CHANGE not in unchanged.triggers


def test_same_input_produces_same_opportunity_id() -> None:
    scanner = DeterministicScanner()
    current = feature(distance_to_range_high_pct=0.2)
    first = scanner.scan(current, system_id="balanced_v1").opportunity
    second = scanner.scan(current, system_id="balanced_v1").opportunity
    assert first is not None and second is not None
    assert first.model_dump() == second.model_dump()


def test_score_is_capped_at_100() -> None:
    scanner = DeterministicScanner(ScannerConfig(min_priority_score=1))
    previous = feature(regime=MarketRegime.RANGE)
    current = feature(
        snapshot_id="snap-hot",
        distance_to_range_high_pct=1.0,
        volume_ratio=3.0,
        atr_expansion_ratio=2.0,
        adx_14=50.0,
        ema_spread_pct=2.0,
        rsi_14=90.0,
        regime=MarketRegime.BULLISH_TREND,
    )
    result = scanner.scan(current, system_id="balanced_v1", previous=previous)
    assert result.score == 100
