from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest

from app.analytics.events import (
    TechnicalEventDirection,
    TechnicalEventEvidence,
    TechnicalEventFamily,
    TechnicalEventObservation,
)


def _event(**overrides):
    values = {
        "analytics_run_id": "analytics-run",
        "event_type": "RSI_14_ENTER_OVERSOLD",
        "family": TechnicalEventFamily.MOMENTUM,
        "direction": TechnicalEventDirection.BEARISH,
        "symbol": "BTC/EUR",
        "timeframe": "1h",
        "event_at": datetime(2026, 1, 1, 1, tzinfo=UTC),
        "available_at": datetime(2026, 1, 1, 1, tzinfo=UTC),
        "source_indicator_snapshot_fingerprint": "a" * 64,
        "source_cursor_fingerprint": "b" * 64,
        "evidence": TechnicalEventEvidence(
            previous_values={"rsi_14": 31.0},
            current_values={"rsi_14": 29.0},
            parameters={"threshold": 30.0, "condition": "enter_below"},
        ),
        "definition_version": "v1",
    }
    values.update(overrides)
    return TechnicalEventObservation.create(**values)


def test_event_is_immutable_and_evidence_is_exactly_serializable() -> None:
    event = _event()
    assert event.evidence.previous_values == {"rsi_14": 31.0}
    assert event.evidence.current_values == {"rsi_14": 29.0}
    assert event.evidence.parameters["threshold"] == 30.0
    assert event.canonical_payload()["event_fingerprint"] == event.event_fingerprint
    with pytest.raises(FrozenInstanceError):
        event.event_type = "OTHER"  # type: ignore[misc]
    with pytest.raises(TypeError):
        event.evidence.current_values["rsi_14"] = 1.0  # type: ignore[index]


def test_same_inputs_produce_same_event_id_and_fingerprint() -> None:
    first = _event()
    second = _event()
    assert first.event_id == second.event_id
    assert first.event_fingerprint == second.event_fingerprint


def test_material_identity_changes_change_event_id() -> None:
    base = _event()
    changed_type = _event(event_type="RSI_14_CROSS_BELOW_50")
    changed_time = _event(
        event_at=base.event_at + timedelta(hours=1),
        available_at=base.available_at + timedelta(hours=1),
    )
    changed_definition = _event(definition_version="v2")
    changed_snapshot = _event(source_indicator_snapshot_fingerprint="c" * 64)
    changed_timeframe = _event(timeframe="4h")

    assert changed_type.event_id != base.event_id
    assert changed_time.event_id != base.event_id
    assert changed_definition.event_id != base.event_id
    assert changed_snapshot.event_id != base.event_id
    assert changed_timeframe.event_id != base.event_id


def test_available_at_cannot_precede_event_at() -> None:
    with pytest.raises(ValueError, match="event_at cannot be later"):
        _event(available_at=datetime(2025, 12, 31, 23, tzinfo=UTC))


def test_replacing_fingerprint_with_wrong_value_is_rejected() -> None:
    event = _event()
    with pytest.raises(ValueError, match="event_fingerprint"):
        replace(event, event_fingerprint="0" * 64)
