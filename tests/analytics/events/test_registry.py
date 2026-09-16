from __future__ import annotations

from math import isfinite

from app.analytics.events import (
    ANALYTICS_TECHNICAL_EVENT_REGISTRY_FINGERPRINT,
    ANALYTICS_TECHNICAL_EVENT_REGISTRY_VERSION,
    TECHNICAL_EVENT_BY_TYPE,
    TECHNICAL_EVENT_REGISTRY,
    TechnicalEventCondition,
    TechnicalEventDirection,
    TechnicalEventFamily,
    registry_payload,
)
from app.analytics.indicators.registry import INDICATOR_BY_ID
from app.common.canonical import stable_digest


def test_registry_is_unique_complete_and_indicator_backed() -> None:
    assert ANALYTICS_TECHNICAL_EVENT_REGISTRY_VERSION
    assert len(TECHNICAL_EVENT_REGISTRY) == 35
    assert len(TECHNICAL_EVENT_BY_TYPE) == len(TECHNICAL_EVENT_REGISTRY)
    assert len({item.event_type for item in TECHNICAL_EVENT_REGISTRY}) == len(
        TECHNICAL_EVENT_REGISTRY
    )
    for definition in TECHNICAL_EVENT_REGISTRY:
        assert isinstance(definition.family, TechnicalEventFamily)
        assert isinstance(definition.direction, TechnicalEventDirection)
        assert isinstance(definition.condition, TechnicalEventCondition)
        assert definition.definition_version
        assert definition.required_indicators
        assert all(item in INDICATOR_BY_ID for item in definition.required_indicators)
        if "threshold" in definition.parameters:
            assert isfinite(float(definition.parameters["threshold"]))


def test_registry_thresholds_are_canonical_and_visible_in_provenance() -> None:
    expected = {
        "RSI_14_ENTER_OVERSOLD": 30.0,
        "RSI_14_CROSS_ABOVE_50": 50.0,
        "RSI_14_ENTER_OVERBOUGHT": 70.0,
        "ADX_14_CROSS_ABOVE_25": 25.0,
        "VOLUME_SPIKE_20": 1.5,
        "MFI_14_ENTER_OVERSOLD": 20.0,
        "MFI_14_ENTER_OVERBOUGHT": 80.0,
    }
    for event_type, threshold in expected.items():
        assert float(TECHNICAL_EVENT_BY_TYPE[event_type].parameters["threshold"]) == threshold


def test_registry_fingerprint_matches_canonical_payload() -> None:
    payload = registry_payload()
    assert payload["registry_version"] == ANALYTICS_TECHNICAL_EVENT_REGISTRY_VERSION
    assert payload["registry_fingerprint"] == ANALYTICS_TECHNICAL_EVENT_REGISTRY_FINGERPRINT
    expected = stable_digest(
        {
            "registry_version": ANALYTICS_TECHNICAL_EVENT_REGISTRY_VERSION,
            "definitions": tuple(item.canonical_payload() for item in TECHNICAL_EVENT_REGISTRY),
        }
    )
    assert expected == ANALYTICS_TECHNICAL_EVENT_REGISTRY_FINGERPRINT
