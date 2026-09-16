from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from types import MappingProxyType
from typing import Any

from app.analytics.provenance import normalize_identifier, normalize_sha256
from app.common.canonical import stable_digest

from .registry import (
    ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT,
    ANALYTICS_INDICATOR_REGISTRY_VERSION,
    INDICATOR_IDS,
)

ANALYTICS_INDICATOR_SNAPSHOT_SCHEMA_VERSION = "money-heist.analytics-indicator-snapshot.v1"


def _as_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class IndicatorValue:
    indicator_id: str
    value: float | None
    available: bool
    warmup_complete: bool
    definition_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "indicator_id",
            normalize_identifier(self.indicator_id, field_name="indicator_id"),
        )
        object.__setattr__(
            self,
            "definition_version",
            normalize_identifier(self.definition_version, field_name="definition_version"),
        )
        if self.value is not None:
            number = float(self.value)
            if not isfinite(number):
                raise ValueError("indicator value must be finite")
            object.__setattr__(self, "value", number)
        if self.available != (self.value is not None):
            raise ValueError("available must exactly reflect whether value is present")
        if self.available and not self.warmup_complete:
            raise ValueError("an indicator cannot be available before warmup is complete")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "indicator_id": self.indicator_id,
            "value": self.value,
            "available": self.available,
            "warmup_complete": self.warmup_complete,
            "definition_version": self.definition_version,
        }


@dataclass(frozen=True, slots=True)
class AnalyticsIndicatorSnapshot:
    symbol: str
    timeframe: str
    as_of: datetime
    source_cursor_fingerprint: str
    registry_version: str
    registry_fingerprint: str
    candle_count: int
    values: tuple[IndicatorValue, ...]
    snapshot_fingerprint: str
    schema_version: str = ANALYTICS_INDICATOR_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_INDICATOR_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {ANALYTICS_INDICATOR_SNAPSHOT_SCHEMA_VERSION!r}"
            )
        object.__setattr__(self, "symbol", normalize_identifier(self.symbol, field_name="symbol"))
        object.__setattr__(
            self,
            "timeframe",
            normalize_identifier(self.timeframe, field_name="timeframe"),
        )
        object.__setattr__(self, "as_of", _as_utc(self.as_of, field="as_of"))
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
            "registry_version",
            normalize_identifier(self.registry_version, field_name="registry_version"),
        )
        object.__setattr__(
            self,
            "registry_fingerprint",
            normalize_sha256(self.registry_fingerprint, field_name="registry_fingerprint"),
        )
        object.__setattr__(
            self,
            "snapshot_fingerprint",
            normalize_sha256(self.snapshot_fingerprint, field_name="snapshot_fingerprint"),
        )
        if self.candle_count < 0:
            raise ValueError("candle_count must be >= 0")
        ids = tuple(item.indicator_id for item in self.values)
        if ids != INDICATOR_IDS:
            raise ValueError("indicator values must exactly match canonical registry order")
        expected = stable_digest(self.identity_payload())
        if expected != self.snapshot_fingerprint:
            raise ValueError("snapshot_fingerprint does not match indicator snapshot payload")

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        timeframe: str,
        as_of: datetime,
        source_cursor_fingerprint: str,
        candle_count: int,
        values: tuple[IndicatorValue, ...],
        registry_version: str = ANALYTICS_INDICATOR_REGISTRY_VERSION,
        registry_fingerprint: str = ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT,
    ) -> AnalyticsIndicatorSnapshot:
        payload = {
            "schema_version": ANALYTICS_INDICATOR_SNAPSHOT_SCHEMA_VERSION,
            "symbol": symbol,
            "timeframe": timeframe,
            "as_of": _as_utc(as_of, field="as_of"),
            "source_cursor_fingerprint": source_cursor_fingerprint,
            "registry_version": registry_version,
            "registry_fingerprint": registry_fingerprint,
            "candle_count": candle_count,
            "values": tuple(item.canonical_payload() for item in values),
        }
        return cls(
            symbol=symbol,
            timeframe=timeframe,
            as_of=payload["as_of"],
            source_cursor_fingerprint=source_cursor_fingerprint,
            registry_version=registry_version,
            registry_fingerprint=registry_fingerprint,
            candle_count=candle_count,
            values=values,
            snapshot_fingerprint=stable_digest(payload),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "as_of": self.as_of,
            "source_cursor_fingerprint": self.source_cursor_fingerprint,
            "registry_version": self.registry_version,
            "registry_fingerprint": self.registry_fingerprint,
            "candle_count": self.candle_count,
            "values": tuple(item.canonical_payload() for item in self.values),
        }

    @property
    def by_id(self) -> Mapping[str, IndicatorValue]:
        return MappingProxyType({item.indicator_id: item for item in self.values})

    def value(self, indicator_id: str) -> IndicatorValue:
        try:
            return self.by_id[indicator_id]
        except KeyError as exc:
            raise KeyError(f"unknown analytics indicator {indicator_id!r}") from exc


__all__ = [
    "ANALYTICS_INDICATOR_SNAPSHOT_SCHEMA_VERSION",
    "AnalyticsIndicatorSnapshot",
    "IndicatorValue",
]
