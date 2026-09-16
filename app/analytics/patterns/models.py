from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from app.analytics.provenance import normalize_identifier, normalize_sha256
from app.analytics.structure import StructureSource
from app.common.canonical import stable_digest, stable_uuid

from .registry import ANALYTICS_PATTERN_REGISTRY_VERSION, PatternFamily, PatternType

PATTERN_SCHEMA_VERSION = "money-heist.analytics-pattern-occurrence.v1"


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _decimal(value: Decimal | float | str, field: str) -> Decimal:
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _freeze_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(sorted(values.items())))


class PatternDirection(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class PatternStatus(StrEnum):
    FORMING = "FORMING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True, slots=True)
class PatternPivot:
    pivot_id: str
    kind: str
    price: Decimal
    pivot_at: datetime
    confirmed_at: datetime
    symbol: str
    timeframe: str
    source: StructureSource
    source_fingerprint: str
    source_cursor_fingerprint: str
    atr_at_pivot: Decimal
    candle_index: int
    confirmed_index: int

    def __post_init__(self) -> None:
        if self.kind not in {"HIGH", "LOW"}:
            raise ValueError("kind must be HIGH or LOW")
        object.__setattr__(self, "pivot_at", _utc(self.pivot_at, "pivot_at"))
        object.__setattr__(self, "confirmed_at", _utc(self.confirmed_at, "confirmed_at"))
        if self.confirmed_at < self.pivot_at:
            raise ValueError("confirmed_at cannot precede pivot_at")
        if self.candle_index < 0 or self.confirmed_index < self.candle_index:
            raise ValueError("invalid candle indexes")
        object.__setattr__(
            self,
            "pivot_id",
            normalize_identifier(self.pivot_id, field_name="pivot_id"),
        )
        object.__setattr__(
            self,
            "symbol",
            normalize_identifier(self.symbol, field_name="symbol"),
        )
        object.__setattr__(
            self,
            "timeframe",
            normalize_identifier(self.timeframe, field_name="timeframe"),
        )
        object.__setattr__(
            self,
            "source_fingerprint",
            normalize_sha256(self.source_fingerprint, field_name="source_fingerprint"),
        )
        object.__setattr__(
            self,
            "source_cursor_fingerprint",
            normalize_sha256(
                self.source_cursor_fingerprint,
                field_name="source_cursor_fingerprint",
            ),
        )
        atr = _decimal(self.atr_at_pivot, "atr_at_pivot")
        if atr <= 0:
            raise ValueError("atr_at_pivot must be > 0")
        object.__setattr__(self, "atr_at_pivot", atr)
        object.__setattr__(self, "price", _decimal(self.price, "price"))


@dataclass(frozen=True, slots=True)
class PatternPoint:
    role: str
    pivot_id: str
    kind: str
    price: Decimal
    pivot_at: datetime
    confirmed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", normalize_identifier(self.role, field_name="role"))
        object.__setattr__(
            self,
            "pivot_id",
            normalize_identifier(self.pivot_id, field_name="pivot_id"),
        )
        if self.kind not in {"HIGH", "LOW"}:
            raise ValueError("pattern point kind must be HIGH or LOW")
        object.__setattr__(self, "price", _decimal(self.price, "price"))
        object.__setattr__(self, "pivot_at", _utc(self.pivot_at, "pivot_at"))
        object.__setattr__(self, "confirmed_at", _utc(self.confirmed_at, "confirmed_at"))
        if self.confirmed_at < self.pivot_at:
            raise ValueError("point confirmed_at cannot precede pivot_at")


@dataclass(frozen=True, slots=True)
class PatternSegment:
    role: str
    start_at: datetime
    start_price: Decimal
    end_at: datetime
    end_price: Decimal
    slope_per_bar: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", normalize_identifier(self.role, field_name="role"))
        object.__setattr__(self, "start_at", _utc(self.start_at, "start_at"))
        object.__setattr__(self, "end_at", _utc(self.end_at, "end_at"))
        if self.end_at < self.start_at:
            raise ValueError("segment end_at cannot precede start_at")
        object.__setattr__(self, "start_price", _decimal(self.start_price, "start_price"))
        object.__setattr__(self, "end_price", _decimal(self.end_price, "end_price"))
        object.__setattr__(
            self,
            "slope_per_bar",
            _decimal(self.slope_per_bar, "slope_per_bar"),
        )


@dataclass(frozen=True, slots=True)
class PatternTransition:
    status: PatternStatus
    occurred_at: datetime
    available_at: datetime
    reason: str
    evidence: Mapping[str, Any]
    fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, PatternStatus):
            object.__setattr__(self, "status", PatternStatus(str(self.status)))
        occurred_at = _utc(self.occurred_at, "occurred_at")
        available_at = _utc(self.available_at, "available_at")
        if available_at < occurred_at:
            raise ValueError("transition available_at cannot precede occurred_at")
        object.__setattr__(self, "occurred_at", occurred_at)
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(
            self,
            "reason",
            normalize_identifier(self.reason, field_name="reason"),
        )
        object.__setattr__(self, "evidence", _freeze_mapping(self.evidence))
        object.__setattr__(
            self,
            "fingerprint",
            normalize_sha256(self.fingerprint, field_name="fingerprint"),
        )
        payload = {
            "status": self.status,
            "occurred_at": self.occurred_at,
            "available_at": self.available_at,
            "reason": self.reason,
            "evidence": self.evidence,
        }
        if self.fingerprint != stable_digest(payload):
            raise ValueError("transition fingerprint mismatch")

    @classmethod
    def create(
        cls,
        status: PatternStatus,
        occurred_at: datetime,
        *,
        reason: str,
        evidence: Mapping[str, Any] | None = None,
    ) -> PatternTransition:
        occurred_at = _utc(occurred_at, "occurred_at")
        normalized_reason = normalize_identifier(reason, field_name="reason")
        frozen_evidence = _freeze_mapping(evidence or {})
        payload = {
            "status": status,
            "occurred_at": occurred_at,
            "available_at": occurred_at,
            "reason": normalized_reason,
            "evidence": frozen_evidence,
        }
        return cls(
            status=status,
            occurred_at=occurred_at,
            available_at=occurred_at,
            reason=normalized_reason,
            evidence=frozen_evidence,
            fingerprint=stable_digest(payload),
        )


@dataclass(frozen=True, slots=True)
class PatternOccurrence:
    pattern_id: str
    analytics_run_id: str
    pattern_type: PatternType
    family: PatternFamily
    direction: PatternDirection
    experimental: bool
    pivot_source: StructureSource
    symbol: str
    timeframe: str
    start_at: datetime
    detected_at: datetime
    end_at: datetime
    confirmed_at: datetime | None
    failed_at: datetime | None
    invalidated_at: datetime | None
    current_status: PatternStatus
    points: tuple[PatternPoint, ...]
    segments: tuple[PatternSegment, ...]
    breakout_level: Decimal | None
    metrics: Mapping[str, Any]
    diagnostic_flags: tuple[str, ...]
    transitions: tuple[PatternTransition, ...]
    definition_version: str
    source_cursor_fingerprint: str
    source_pivot_fingerprints: tuple[str, ...]
    pattern_fingerprint: str
    schema_version: str = PATTERN_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        analytics_run_id: str,
        pattern_type: PatternType,
        family: PatternFamily,
        direction: PatternDirection,
        pivot_source: StructureSource,
        symbol: str,
        timeframe: str,
        points: tuple[PatternPoint, ...],
        segments: tuple[PatternSegment, ...],
        transitions: tuple[PatternTransition, ...],
        breakout_level: Decimal | None,
        metrics: Mapping[str, Any],
        diagnostic_flags: tuple[str, ...],
        source_cursor_fingerprint: str,
        source_pivot_fingerprints: tuple[str, ...],
    ) -> PatternOccurrence:
        if not points or not transitions:
            raise ValueError("pattern requires points and transitions")
        if len(source_pivot_fingerprints) != len(points):
            raise ValueError("source_pivot_fingerprints must match pattern points")
        if transitions[0].status != PatternStatus.FORMING:
            raise ValueError("pattern lifecycle must start with FORMING")
        allowed = {
            PatternStatus.FORMING: {PatternStatus.CONFIRMED, PatternStatus.FAILED},
            PatternStatus.CONFIRMED: {PatternStatus.INVALIDATED},
            PatternStatus.FAILED: set(),
            PatternStatus.INVALIDATED: set(),
        }
        for previous, current in zip(transitions, transitions[1:], strict=False):
            if current.status not in allowed[previous.status]:
                raise ValueError(
                    f"invalid pattern transition {previous.status.value} -> {current.status.value}"
                )
            if current.available_at < previous.available_at:
                raise ValueError("pattern transition timestamps must be monotonic")

        normalized_run_id = normalize_identifier(
            analytics_run_id,
            field_name="analytics_run_id",
        )
        normalized_symbol = normalize_identifier(symbol, field_name="symbol")
        normalized_timeframe = normalize_identifier(timeframe, field_name="timeframe")
        normalized_cursor = normalize_sha256(
            source_cursor_fingerprint,
            field_name="source_cursor_fingerprint",
        )
        normalized_pivot_fingerprints = tuple(
            normalize_sha256(value, field_name="source_pivot_fingerprint")
            for value in source_pivot_fingerprints
        )
        frozen_metrics = _freeze_mapping(metrics)
        normalized_flags = tuple(
            normalize_identifier(value, field_name="diagnostic_flag") for value in diagnostic_flags
        )
        normalized_breakout = (
            None if breakout_level is None else _decimal(breakout_level, "breakout_level")
        )
        identity = {
            "analytics_run_id": normalized_run_id,
            "pattern_type": pattern_type,
            "symbol": normalized_symbol,
            "timeframe": normalized_timeframe,
            "pivot_source": pivot_source,
            "pivot_ids": [point.pivot_id for point in points],
            "definition_version": ANALYTICS_PATTERN_REGISTRY_VERSION,
            "detected_at": transitions[0].available_at,
        }
        pattern_id = stable_uuid("analytics-pattern-occurrence", identity)
        status = transitions[-1].status
        confirmed_at = next(
            (
                transition.available_at
                for transition in transitions
                if transition.status == PatternStatus.CONFIRMED
            ),
            None,
        )
        failed_at = next(
            (
                transition.available_at
                for transition in transitions
                if transition.status == PatternStatus.FAILED
            ),
            None,
        )
        invalidated_at = next(
            (
                transition.available_at
                for transition in transitions
                if transition.status == PatternStatus.INVALIDATED
            ),
            None,
        )
        payload = {
            "identity": identity,
            "family": family,
            "direction": direction,
            "experimental": True,
            "pivot_source": pivot_source,
            "symbol": normalized_symbol,
            "timeframe": normalized_timeframe,
            "status": status,
            "transitions": transitions,
            "points": points,
            "segments": segments,
            "breakout_level": normalized_breakout,
            "metrics": frozen_metrics,
            "diagnostic_flags": normalized_flags,
            "definition_version": ANALYTICS_PATTERN_REGISTRY_VERSION,
            "source_cursor_fingerprint": normalized_cursor,
            "source_pivot_fingerprints": normalized_pivot_fingerprints,
        }
        return cls(
            pattern_id=pattern_id,
            analytics_run_id=normalized_run_id,
            pattern_type=pattern_type,
            family=family,
            direction=direction,
            experimental=True,
            pivot_source=pivot_source,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            start_at=min(point.pivot_at for point in points),
            detected_at=transitions[0].available_at,
            end_at=transitions[-1].available_at,
            confirmed_at=confirmed_at,
            failed_at=failed_at,
            invalidated_at=invalidated_at,
            current_status=status,
            points=points,
            segments=segments,
            breakout_level=normalized_breakout,
            metrics=frozen_metrics,
            diagnostic_flags=normalized_flags,
            transitions=transitions,
            definition_version=ANALYTICS_PATTERN_REGISTRY_VERSION,
            source_cursor_fingerprint=normalized_cursor,
            source_pivot_fingerprints=normalized_pivot_fingerprints,
            pattern_fingerprint=stable_digest(payload),
        )
