from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite
from typing import Any

from app.analytics.provenance import normalize_identifier, normalize_sha256
from app.common.canonical import stable_digest, stable_uuid
from app.market.models import Candle

from .registry import (
    CAUSAL_ZIGZAG_REGISTRY_FINGERPRINT,
    CAUSAL_ZIGZAG_VERSION,
)

CAUSAL_ZIGZAG_PIVOT_SCHEMA_VERSION = "money-heist.analytics-causal-zigzag-pivot.v1"


def _as_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _finite_decimal(value: Decimal | float | str, *, field: str) -> Decimal:
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


class ZigZagPivotKind(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


@dataclass(frozen=True, slots=True)
class CausalZigZagInputBar:
    candle: Candle
    atr_at_candle: float | None
    source_cursor_fingerprint: str
    source_indicator_snapshot_fingerprint: str

    def __post_init__(self) -> None:
        if not self.candle.is_closed:
            raise ValueError("causal ZigZag accepts closed candles only")
        if self.atr_at_candle is not None:
            atr = float(self.atr_at_candle)
            if not isfinite(atr) or atr <= 0.0:
                raise ValueError("atr_at_candle must be finite and > 0")
            object.__setattr__(self, "atr_at_candle", atr)
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
            "source_indicator_snapshot_fingerprint",
            normalize_sha256(
                self.source_indicator_snapshot_fingerprint,
                field_name="source_indicator_snapshot_fingerprint",
            ),
        )


@dataclass(frozen=True, slots=True)
class CausalZigZagPivot:
    pivot_id: str
    analytics_run_id: str
    symbol: str
    timeframe: str
    kind: ZigZagPivotKind
    pivot_at: datetime
    confirmed_at: datetime
    price: Decimal
    atr_at_pivot: Decimal
    reversal_multiple: Decimal
    reversal_threshold: Decimal
    amplitude_pct: Decimal | None
    amplitude_atr: Decimal | None
    bars_from_previous: int | None
    source_cursor_fingerprint: str
    source_indicator_snapshot_fingerprint: str
    confirmation_indicator_snapshot_fingerprint: str
    definition_version: str
    definition_fingerprint: str
    pivot_fingerprint: str
    candle_index: int
    confirmed_index: int
    schema_version: str = CAUSAL_ZIGZAG_PIVOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CAUSAL_ZIGZAG_PIVOT_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {CAUSAL_ZIGZAG_PIVOT_SCHEMA_VERSION!r}"
            )
        for field_name in (
            "pivot_id",
            "analytics_run_id",
            "symbol",
            "timeframe",
            "definition_version",
            "schema_version",
        ):
            object.__setattr__(
                self,
                field_name,
                normalize_identifier(getattr(self, field_name), field_name=field_name),
            )
        if not isinstance(self.kind, ZigZagPivotKind):
            object.__setattr__(self, "kind", ZigZagPivotKind(str(self.kind)))
        pivot_at = _as_utc(self.pivot_at, field="pivot_at")
        confirmed_at = _as_utc(self.confirmed_at, field="confirmed_at")
        if confirmed_at < pivot_at:
            raise ValueError("confirmed_at cannot precede pivot_at")
        object.__setattr__(self, "pivot_at", pivot_at)
        object.__setattr__(self, "confirmed_at", confirmed_at)
        for field_name in (
            "price",
            "atr_at_pivot",
            "reversal_multiple",
            "reversal_threshold",
        ):
            value = _finite_decimal(getattr(self, field_name), field=field_name)
            if field_name != "price" and value <= 0:
                raise ValueError(f"{field_name} must be > 0")
            object.__setattr__(self, field_name, value)
        for field_name in ("amplitude_pct", "amplitude_atr"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _finite_decimal(value, field=field_name),
                )
        if self.bars_from_previous is not None and self.bars_from_previous <= 0:
            raise ValueError("bars_from_previous must be > 0 when present")
        if self.candle_index < 0 or self.confirmed_index < self.candle_index:
            raise ValueError("invalid pivot/confirmation candle indexes")
        for field_name in (
            "source_cursor_fingerprint",
            "source_indicator_snapshot_fingerprint",
            "confirmation_indicator_snapshot_fingerprint",
            "definition_fingerprint",
            "pivot_fingerprint",
        ):
            object.__setattr__(
                self,
                field_name,
                normalize_sha256(getattr(self, field_name), field_name=field_name),
            )
        if self.definition_version != CAUSAL_ZIGZAG_VERSION:
            raise ValueError("unexpected causal ZigZag definition_version")
        if self.definition_fingerprint != CAUSAL_ZIGZAG_REGISTRY_FINGERPRINT:
            raise ValueError("unexpected causal ZigZag definition_fingerprint")
        expected = stable_digest(self.identity_payload())
        if self.pivot_fingerprint != expected:
            raise ValueError("pivot_fingerprint does not match pivot payload")
        if self.pivot_id != stable_uuid("analytics-zigzag-pivot", self.identity_payload()):
            raise ValueError("pivot_id does not match pivot payload")

    @classmethod
    def create(
        cls,
        *,
        analytics_run_id: str,
        symbol: str,
        timeframe: str,
        kind: ZigZagPivotKind,
        pivot_at: datetime,
        confirmed_at: datetime,
        price: Decimal,
        atr_at_pivot: Decimal,
        reversal_multiple: Decimal,
        reversal_threshold: Decimal,
        amplitude_pct: Decimal | None,
        amplitude_atr: Decimal | None,
        bars_from_previous: int | None,
        source_cursor_fingerprint: str,
        source_indicator_snapshot_fingerprint: str,
        confirmation_indicator_snapshot_fingerprint: str,
        candle_index: int,
        confirmed_index: int,
    ) -> CausalZigZagPivot:
        payload = {
            "schema_version": CAUSAL_ZIGZAG_PIVOT_SCHEMA_VERSION,
            "analytics_run_id": analytics_run_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "kind": kind,
            "pivot_at": _as_utc(pivot_at, field="pivot_at"),
            "confirmed_at": _as_utc(confirmed_at, field="confirmed_at"),
            "price": _finite_decimal(price, field="price"),
            "atr_at_pivot": _finite_decimal(atr_at_pivot, field="atr_at_pivot"),
            "reversal_multiple": _finite_decimal(
                reversal_multiple, field="reversal_multiple"
            ),
            "reversal_threshold": _finite_decimal(
                reversal_threshold, field="reversal_threshold"
            ),
            "amplitude_pct": (
                None
                if amplitude_pct is None
                else _finite_decimal(amplitude_pct, field="amplitude_pct")
            ),
            "amplitude_atr": (
                None
                if amplitude_atr is None
                else _finite_decimal(amplitude_atr, field="amplitude_atr")
            ),
            "bars_from_previous": bars_from_previous,
            "source_cursor_fingerprint": source_cursor_fingerprint,
            "source_indicator_snapshot_fingerprint": (
                source_indicator_snapshot_fingerprint
            ),
            "confirmation_indicator_snapshot_fingerprint": (
                confirmation_indicator_snapshot_fingerprint
            ),
            "definition_version": CAUSAL_ZIGZAG_VERSION,
            "definition_fingerprint": CAUSAL_ZIGZAG_REGISTRY_FINGERPRINT,
            "candle_index": candle_index,
            "confirmed_index": confirmed_index,
        }
        fingerprint = stable_digest(payload)
        pivot_id = stable_uuid("analytics-zigzag-pivot", payload)
        return cls(
            pivot_id=pivot_id,
            pivot_fingerprint=fingerprint,
            **payload,
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "analytics_run_id": self.analytics_run_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "kind": self.kind,
            "pivot_at": self.pivot_at,
            "confirmed_at": self.confirmed_at,
            "price": self.price,
            "atr_at_pivot": self.atr_at_pivot,
            "reversal_multiple": self.reversal_multiple,
            "reversal_threshold": self.reversal_threshold,
            "amplitude_pct": self.amplitude_pct,
            "amplitude_atr": self.amplitude_atr,
            "bars_from_previous": self.bars_from_previous,
            "source_cursor_fingerprint": self.source_cursor_fingerprint,
            "source_indicator_snapshot_fingerprint": (
                self.source_indicator_snapshot_fingerprint
            ),
            "confirmation_indicator_snapshot_fingerprint": (
                self.confirmation_indicator_snapshot_fingerprint
            ),
            "definition_version": self.definition_version,
            "definition_fingerprint": self.definition_fingerprint,
            "candle_index": self.candle_index,
            "confirmed_index": self.confirmed_index,
        }


__all__ = [
    "CAUSAL_ZIGZAG_PIVOT_SCHEMA_VERSION",
    "CausalZigZagInputBar",
    "CausalZigZagPivot",
    "ZigZagPivotKind",
]
