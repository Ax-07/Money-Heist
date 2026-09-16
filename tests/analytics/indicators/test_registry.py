from dataclasses import replace

from app.analytics.indicators import (
    ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT,
    ANALYTICS_INDICATOR_REGISTRY_IDENTITY,
    ANALYTICS_INDICATOR_REGISTRY_VERSION,
    INDICATOR_BY_ID,
    INDICATOR_IDS,
    INDICATOR_REGISTRY,
    registry_payload,
)
from app.common.canonical import stable_digest


def test_registry_is_versioned_unique_and_machine_readable() -> None:
    assert ANALYTICS_INDICATOR_REGISTRY_VERSION == "money-heist.analytics-indicators.v1"
    assert len(INDICATOR_IDS) == len(set(INDICATOR_IDS)) == len(INDICATOR_REGISTRY)
    assert len(ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT) == 64
    assert ANALYTICS_INDICATOR_REGISTRY_IDENTITY.endswith(ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT)
    assert registry_payload()["registry_fingerprint"] == ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT


def test_registry_contains_required_batch_24a2_catalogue() -> None:
    required = {
        "sma_20",
        "sma_50",
        "sma_100",
        "sma_200",
        "ema_9",
        "ema_20",
        "ema_50",
        "ema_100",
        "ema_200",
        "rsi_14",
        "rsi_delta_14",
        "stoch_rsi_k_14_14_3_3",
        "stoch_rsi_d_14_14_3_3",
        "roc_12",
        "macd_12_26_9",
        "macd_signal_12_26_9",
        "macd_hist_12_26_9",
        "atr_14",
        "atr_pct_14",
        "bb_mid_20_2",
        "bb_upper_20_2",
        "bb_lower_20_2",
        "bb_width_pct_20_2",
        "bb_position_20_2",
        "adx_14",
        "plus_di_14",
        "minus_di_14",
        "volume_sma_20",
        "volume_ratio_20",
        "obv",
        "mfi_14",
        "cmf_20",
        "rolling_vwap_20",
        "rolling_high_prev_20",
        "rolling_low_prev_20",
        "rolling_high_prev_50",
        "rolling_low_prev_50",
        "rolling_high_prev_100",
        "rolling_low_prev_100",
        "donchian_upper_20",
        "donchian_lower_20",
        "donchian_position_20",
    }
    assert required <= set(INDICATOR_BY_ID)


def test_definition_or_parameter_change_changes_registry_fingerprint() -> None:
    changed = list(INDICATOR_REGISTRY)
    changed[0] = replace(changed[0], definition_version="v2")
    changed_digest = stable_digest(
        {
            "registry_version": ANALYTICS_INDICATOR_REGISTRY_VERSION,
            "definitions": tuple(item.canonical_payload() for item in changed),
        }
    )
    assert changed_digest != ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT


def test_explicit_warmup_contracts_are_not_zero_filled() -> None:
    assert INDICATOR_BY_ID["ema_200"].warmup_bars == 200
    assert INDICATOR_BY_ID["ema_200_slope_pct"].warmup_bars == 201
    assert INDICATOR_BY_ID["rsi_14"].warmup_bars == 15
    assert INDICATOR_BY_ID["macd_signal_12_26_9"].warmup_bars == 34
    assert INDICATOR_BY_ID["adx_14"].warmup_bars == 28
    assert INDICATOR_BY_ID["donchian_upper_20"].warmup_bars == 21
