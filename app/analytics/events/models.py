from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from types import MappingProxyType
from typing import Any

from app.analytics.provenance import as_utc, normalize_identifier, normalize_sha256
from app.common.canonical import stable_digest, stable_uuid

from .registry import TechnicalEventDirection, TechnicalEventFamily

TECHNICAL_EVENT_OBSERVATION_SCHEMA_VERSION = "money-heist.analytics-technical-event.v1"


def _freeze_numeric_mapping(values: Mapping[str, float]) -> Mapping[str, float]:
    normalized: dict[str, float] = {}
    for key, value in values.items():
        name = normalize_identifier(str(key), field_name="evidence key")
        number = float(value)
        if not isfinite(number):
            raise ValueError("event evidence values must be finite")
        normalized[name] = number
    return MappingProxyType(dict(sorted(normalized.items())))


def _freeze_parameter_mapping(
    values: Mapping[str, float | int | str | bool],
) -> Mapping[str, float | int | str | bool]:
    normalized: dict[str, float | int | str | bool] = {}
    for key, value in values.items():
        name = normalize_identifier(str(key), field_name="evidence parameter key")
        if isinstance(value, float) and not isfinite(value):
            raise ValueError("event evidence parameters must be finite")
        if not isinstance(value, (float, int, str, bool)):
            raise TypeError("event evidence parameters must be scalar and serializable")
        normalized[name] = value
    return MappingProxyType(dict(sorted(normalized.items())))


@dataclass(frozen=True, slots=True)
class TechnicalEventEvidence:
    previous_values: Mapping[str, float]
    current_values: Mapping[str, float]
    parameters: Mapping[str, float | int | str | bool]

    def __post_init__(self) -> None:
        previous = _freeze_numeric_mapping(self.previous_values)
        current = _freeze_numeric_mapping(self.current_values)
        parameters = _freeze_parameter_mapping(self.parameters)
        if tuple(previous) != tuple(current):
            raise ValueError(
                "previous_values and current_values must expose the same evidence keys"
            )
        object.__setattr__(self, "previous_values", previous)
        object.__setattr__(self, "current_values", current)
        object.__setattr__(self, "parameters", parameters)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "previous_values": self.previous_values,
            "current_values": self.current_values,
            "parameters": self.parameters,
        }


@dataclass(frozen=True, slots=True)
class TechnicalEventObservation:
    event_id: str
    analytics_run_id: str
    event_type: str
    family: TechnicalEventFamily
    direction: TechnicalEventDirection
    symbol: str
    timeframe: str
    event_at: datetime
    available_at: datetime
    source_indicator_snapshot_id: str
    source_indicator_snapshot_fingerprint: str
    source_cursor_fingerprint: str
    evidence: TechnicalEventEvidence
    definition_version: str
    event_fingerprint: str
    schema_version: str = TECHNICAL_EVENT_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TECHNICAL_EVENT_OBSERVATION_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {TECHNICAL_EVENT_OBSERVATION_SCHEMA_VERSION!r}"
            )
        for field_name in (
            "event_id",
            "analytics_run_id",
            "event_type",
            "symbol",
            "timeframe",
            "source_indicator_snapshot_id",
            "definition_version",
            "schema_version",
        ):
            object.__setattr__(
                self,
                field_name,
                normalize_identifier(getattr(self, field_name), field_name=field_name),
            )
        try:
            family = (
                self.family
                if isinstance(self.family, TechnicalEventFamily)
                else TechnicalEventFamily(str(self.family))
            )
        except ValueError as exc:
            raise ValueError("invalid technical event family") from exc
        try:
            direction = (
                self.direction
                if isinstance(self.direction, TechnicalEventDirection)
                else TechnicalEventDirection(str(self.direction))
            )
        except ValueError as exc:
            raise ValueError("invalid technical event direction") from exc
        object.__setattr__(self, "family", family)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(
            self,
            "source_indicator_snapshot_fingerprint",
            normalize_sha256(
                self.source_indicator_snapshot_fingerprint,
                field_name="source_indicator_snapshot_fingerprint",
            ),
        )
        object.__setattr__(
            self,
            "source_cursor_fingerprint",
            normalize_sha256(
                self.source_cursor_fingerprint,
                field_name="source_cursor_fingerprint",
            ),
        )
        object.__setattr__(
            self,
            "event_fingerprint",
            normalize_sha256(self.event_fingerprint, field_name="event_fingerprint"),
        )
        event_at = as_utc(self.event_at, field_name="event_at")
        available_at = as_utc(self.available_at, field_name="available_at")
        if event_at > available_at:
            raise ValueError("event_at cannot be later than available_at")
        object.__setattr__(self, "event_at", event_at)
        object.__setattr__(self, "available_at", available_at)

        if self.event_id != stable_uuid("analytics-technical-event", self.identity_payload()):
            raise ValueError("event_id does not match technical event identity")
        if self.event_fingerprint != stable_digest(self.fingerprint_payload()):
            raise ValueError("event_fingerprint does not match technical event payload")

    @classmethod
    def create(
        cls,
        *,
        analytics_run_id: str,
        event_type: str,
        family: TechnicalEventFamily,
        direction: TechnicalEventDirection,
        symbol: str,
        timeframe: str,
        event_at: datetime,
        available_at: datetime,
        source_indicator_snapshot_fingerprint: str,
        source_cursor_fingerprint: str,
        evidence: TechnicalEventEvidence,
        definition_version: str,
    ) -> TechnicalEventObservation:
        normalized_run_id = normalize_identifier(analytics_run_id, field_name="analytics_run_id")
        normalized_event_type = normalize_identifier(event_type, field_name="event_type")
        normalized_symbol = normalize_identifier(symbol, field_name="symbol")
        normalized_timeframe = normalize_identifier(timeframe, field_name="timeframe")
        normalized_definition_version = normalize_identifier(
            definition_version,
            field_name="definition_version",
        )
        normalized_cursor = normalize_sha256(
            source_cursor_fingerprint,
            field_name="source_cursor_fingerprint",
        )
        normalized_event_at = as_utc(event_at, field_name="event_at")
        normalized_available_at = as_utc(available_at, field_name="available_at")
        snapshot_fingerprint = normalize_sha256(
            source_indicator_snapshot_fingerprint,
            field_name="source_indicator_snapshot_fingerprint",
        )
        source_snapshot_id = stable_uuid(
            "analytics-indicator-snapshot",
            {"snapshot_fingerprint": snapshot_fingerprint},
        )
        identity = {
            "schema_version": TECHNICAL_EVENT_OBSERVATION_SCHEMA_VERSION,
            "analytics_run_id": normalized_run_id,
            "event_type": normalized_event_type,
            "symbol": normalized_symbol,
            "timeframe": normalized_timeframe,
            "event_at": normalized_event_at,
            "definition_version": normalized_definition_version,
            "source_indicator_snapshot_fingerprint": snapshot_fingerprint,
        }
        event_id = stable_uuid("analytics-technical-event", identity)
        fingerprint_payload = {
            "schema_version": TECHNICAL_EVENT_OBSERVATION_SCHEMA_VERSION,
            "event_id": event_id,
            "analytics_run_id": normalized_run_id,
            "event_type": normalized_event_type,
            "family": family,
            "direction": direction,
            "symbol": normalized_symbol,
            "timeframe": normalized_timeframe,
            "event_at": normalized_event_at,
            "available_at": normalized_available_at,
            "source_indicator_snapshot_id": source_snapshot_id,
            "source_indicator_snapshot_fingerprint": snapshot_fingerprint,
            "source_cursor_fingerprint": normalized_cursor,
            "evidence": evidence.canonical_payload(),
            "definition_version": normalized_definition_version,
        }
        return cls(
            event_id=event_id,
            analytics_run_id=normalized_run_id,
            event_type=normalized_event_type,
            family=family,
            direction=direction,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            event_at=normalized_event_at,
            available_at=normalized_available_at,
            source_indicator_snapshot_id=source_snapshot_id,
            source_indicator_snapshot_fingerprint=snapshot_fingerprint,
            source_cursor_fingerprint=normalized_cursor,
            evidence=evidence,
            definition_version=normalized_definition_version,
            event_fingerprint=stable_digest(fingerprint_payload),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "analytics_run_id": self.analytics_run_id,
            "event_type": self.event_type,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "event_at": self.event_at,
            "definition_version": self.definition_version,
            "source_indicator_snapshot_fingerprint": self.source_indicator_snapshot_fingerprint,
        }

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "analytics_run_id": self.analytics_run_id,
            "event_type": self.event_type,
            "family": self.family,
            "direction": self.direction,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "event_at": self.event_at,
            "available_at": self.available_at,
            "source_indicator_snapshot_id": self.source_indicator_snapshot_id,
            "source_indicator_snapshot_fingerprint": self.source_indicator_snapshot_fingerprint,
            "source_cursor_fingerprint": self.source_cursor_fingerprint,
            "evidence": self.evidence.canonical_payload(),
            "definition_version": self.definition_version,
        }

    def canonical_payload(self) -> dict[str, Any]:
        payload = self.fingerprint_payload()
        payload["event_fingerprint"] = self.event_fingerprint
        return payload


__all__ = [
    "TECHNICAL_EVENT_OBSERVATION_SCHEMA_VERSION",
    "TechnicalEventEvidence",
    "TechnicalEventObservation",
]
