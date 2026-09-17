from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import Any

from app.analytics.models import AnalyticsLabRun, AnalyticsPeriodRole
from app.analytics.patterns import PatternStatus, PatternType
from app.analytics.provenance import as_utc, normalize_identifier, normalize_sha256
from app.analytics.zigzag import ZigZagPivotKind
from app.common.canonical import stable_digest, stable_uuid

from .registry import (
    ANALYTICS_CONTEXT_MATCH_SCHEMA_VERSION,
    ANALYTICS_CONTEXT_SCHEMA_VERSION,
    ANALYTICS_RESEARCH_RUN_SCHEMA_VERSION,
    ANALYTICS_SEQUENCE_MATCH_SCHEMA_VERSION,
    ANALYTICS_SEQUENCE_SCHEMA_VERSION,
    CONTEXT_RESOLVER_VERSION,
    SEQUENCE_RESOLVER_VERSION,
    AnalyticsAnchorType,
    AnalyticsConditionType,
    IndicatorOperator,
    PatternConditionMode,
    StructureField,
    TemporalScope,
)


def _enum(value: Any, enum_type: type[StrEnum], field_name: str) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise ValueError(f"invalid {field_name}: {value!r}") from exc


def _freeze_mapping(values: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(sorted((values or {}).items())))


def _finite(value: float | int | None, field_name: str) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


@dataclass(frozen=True, slots=True)
class AnalyticsAnchorSpec:
    anchor_type: AnalyticsAnchorType
    timeframe: str
    event_type: str | None = None
    pattern_type: PatternType | None = None
    pattern_status: PatternStatus | None = None
    pivot_kind: ZigZagPivotKind | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "anchor_type",
            _enum(self.anchor_type, AnalyticsAnchorType, "anchor_type")
        )
        object.__setattr__(
            self,
            "timeframe",
            normalize_identifier(self.timeframe, field_name="timeframe")
        )
        if self.event_type is not None:
            object.__setattr__(
                self,
                "event_type",
                normalize_identifier(self.event_type, field_name="event_type")
            )
        if self.pattern_type is not None and not isinstance(self.pattern_type, PatternType):
            object.__setattr__(self, "pattern_type", PatternType(str(self.pattern_type)))
        if self.pattern_status is not None and not isinstance(self.pattern_status, PatternStatus):
            object.__setattr__(self, "pattern_status", PatternStatus(str(self.pattern_status)))
        if self.pivot_kind is not None and not isinstance(self.pivot_kind, ZigZagPivotKind):
            object.__setattr__(self, "pivot_kind", ZigZagPivotKind(str(self.pivot_kind)))
        if self.anchor_type is AnalyticsAnchorType.TECHNICAL_EVENT:
            if (
                self.event_type is None
                or any((self.pattern_type, self.pattern_status, self.pivot_kind))
            ):
                raise ValueError("technical-event anchor requires only event_type")
        elif self.anchor_type is AnalyticsAnchorType.PATTERN_TRANSITION:
            if (
                self.pattern_type is None
                or self.pattern_status is None
                or self.event_type
                or self.pivot_kind
            ):
                raise ValueError(
                    "pattern-transition anchor requires only pattern_type and pattern_status"
                )
        elif self.pivot_kind is None or self.event_type or self.pattern_type or self.pattern_status:
            raise ValueError("zigzag-pivot anchor requires only pivot_kind")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "anchor_type": self.anchor_type,
            "timeframe": self.timeframe,
            "event_type": self.event_type,
            "pattern_type": self.pattern_type,
            "pattern_status": self.pattern_status,
            "pivot_kind": self.pivot_kind,
        }


@dataclass(frozen=True, slots=True)
class AnalyticsConditionSpec:
    condition_id: str
    condition_type: AnalyticsConditionType
    timeframe: str
    scope: TemporalScope = TemporalScope.AT_ANCHOR
    within_previous_bars: int = 0
    indicator_id: str | None = None
    operator: IndicatorOperator | None = None
    value: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    event_type: str | None = None
    pattern_type: PatternType | None = None
    pattern_status: PatternStatus | None = None
    pattern_mode: PatternConditionMode = PatternConditionMode.TRANSITION_OCCURRED
    structure_field: StructureField | None = None
    expected_state: str | None = None
    pivot_kind: ZigZagPivotKind | None = None
    max_bars_since: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "condition_id",
            normalize_identifier(self.condition_id, field_name="condition_id")
        )
        object.__setattr__(
            self,
            "condition_type",
            _enum(self.condition_type, AnalyticsConditionType, "condition_type")
        )
        object.__setattr__(self, "scope", _enum(self.scope, TemporalScope, "scope"))
        object.__setattr__(
            self,
            "timeframe",
            normalize_identifier(self.timeframe, field_name="timeframe")
        )
        if self.within_previous_bars < 0:
            raise ValueError("within_previous_bars must be >= 0")
        if self.scope is TemporalScope.WITHIN_PREVIOUS_BARS and self.within_previous_bars < 1:
            raise ValueError("WITHIN_PREVIOUS_BARS requires within_previous_bars >= 1")
        if self.scope is TemporalScope.AT_ANCHOR and self.within_previous_bars != 0:
            raise ValueError("AT_ANCHOR requires within_previous_bars=0")
        if self.max_bars_since is not None and self.max_bars_since < 0:
            raise ValueError("max_bars_since must be >= 0")
        for name in ("value", "min_value", "max_value"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.indicator_id is not None:
            object.__setattr__(
                self,
                "indicator_id",
                normalize_identifier(self.indicator_id, field_name="indicator_id")
            )
        if self.operator is not None:
            object.__setattr__(
                self,
                "operator",
                _enum(self.operator, IndicatorOperator, "operator")
            )
        if self.event_type is not None:
            object.__setattr__(
                self,
                "event_type",
                normalize_identifier(self.event_type, field_name="event_type")
            )
        if self.pattern_type is not None and not isinstance(self.pattern_type, PatternType):
            object.__setattr__(self, "pattern_type", PatternType(str(self.pattern_type)))
        if self.pattern_status is not None and not isinstance(self.pattern_status, PatternStatus):
            object.__setattr__(self, "pattern_status", PatternStatus(str(self.pattern_status)))
        object.__setattr__(
            self,
            "pattern_mode",
            _enum(self.pattern_mode, PatternConditionMode, "pattern_mode")
        )
        if self.structure_field is not None:
            object.__setattr__(
                self,
                "structure_field",
                _enum(self.structure_field, StructureField, "structure_field")
            )
        if self.expected_state is not None:
            object.__setattr__(
                self,
                "expected_state",
                normalize_identifier(self.expected_state, field_name="expected_state")
            )
        if self.pivot_kind is not None and not isinstance(self.pivot_kind, ZigZagPivotKind):
            object.__setattr__(self, "pivot_kind", ZigZagPivotKind(str(self.pivot_kind)))
        self._validate_shape()

    def _validate_shape(self) -> None:
        if self.condition_type is AnalyticsConditionType.INDICATOR:
            if self.indicator_id is None or self.operator is None:
                raise ValueError("indicator condition requires indicator_id and operator")
            if self.scope is not TemporalScope.AT_ANCHOR:
                raise ValueError("indicator conditions are evaluated AT_ANCHOR")
            if self.operator is IndicatorOperator.BETWEEN:
                if (
                    self.min_value is None
                    or self.max_value is None
                    or self.min_value > self.max_value
                ):
                    raise ValueError("BETWEEN requires min_value <= max_value")
            elif self.value is None:
                raise ValueError(f"{self.operator.value} requires value")
        elif self.condition_type is AnalyticsConditionType.TECHNICAL_EVENT:
            if self.event_type is None:
                raise ValueError("technical-event condition requires event_type")
        elif self.condition_type is AnalyticsConditionType.PATTERN_TRANSITION:
            if self.pattern_type is None or self.pattern_status is None:
                raise ValueError("pattern condition requires pattern_type and pattern_status")
            if (
                self.pattern_mode is PatternConditionMode.CURRENT_STATUS
                and self.scope is not TemporalScope.AT_ANCHOR
            ):
                raise ValueError("CURRENT_STATUS pattern conditions are evaluated AT_ANCHOR")
        elif self.condition_type is AnalyticsConditionType.STRUCTURE:
            if self.structure_field is None or self.expected_state is None:
                raise ValueError("structure condition requires structure_field and expected_state")
            if self.scope is not TemporalScope.AT_ANCHOR:
                raise ValueError("structure conditions are evaluated AT_ANCHOR")
        elif self.pivot_kind is None:
            raise ValueError("zigzag condition requires pivot_kind")

    def canonical_payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class ConditionEvaluation:
    condition_id: str
    matched: bool
    observed_value: Any
    operator: str | None
    expected_value: Any
    source_ref: str | None
    source_available_at: datetime | None
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "condition_id",
            normalize_identifier(self.condition_id, field_name="condition_id")
        )
        if self.source_ref is not None:
            object.__setattr__(
                self,
                "source_ref",
                normalize_identifier(self.source_ref, field_name="source_ref")
            )
        if self.source_available_at is not None:
            object.__setattr__(
                self,
                "source_available_at",
                as_utc(self.source_available_at, field_name="source_available_at")
            )
        object.__setattr__(self, "evidence", _freeze_mapping(self.evidence))

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "matched": self.matched,
            "observed_value": self.observed_value,
            "operator": self.operator,
            "expected_value": self.expected_value,
            "source_ref": self.source_ref,
            "source_available_at": self.source_available_at,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class AnalyticsContextDefinition:
    definition_id: str
    revision_id: str
    revision_number: int
    name: str
    description: str
    anchor: AnalyticsAnchorSpec
    conditions: tuple[AnalyticsConditionSpec, ...]
    timeframe: str
    origin_period_role: AnalyticsPeriodRole
    definition_fingerprint: str
    resolver_version: str = CONTEXT_RESOLVER_VERSION
    schema_version: str = ANALYTICS_CONTEXT_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        definition_id: str,
        revision_number: int,
        name: str,
        description: str,
        anchor: AnalyticsAnchorSpec,
        conditions: Sequence[AnalyticsConditionSpec],
        timeframe: str,
        origin_period_role: AnalyticsPeriodRole,
    ) -> AnalyticsContextDefinition:
        if revision_number < 1:
            raise ValueError("revision_number must be >= 1")
        did = normalize_identifier(definition_id, field_name="definition_id")
        tf = normalize_identifier(timeframe, field_name="timeframe")
        nm = name.strip()
        if not nm:
            raise ValueError("name must not be empty")
        conds = tuple(conditions)
        ids = tuple(item.condition_id for item in conds)
        if len(set(ids)) != len(ids):
            raise ValueError("condition IDs must be unique")
        role = origin_period_role if isinstance(
            origin_period_role,
            AnalyticsPeriodRole
        ) else AnalyticsPeriodRole(str(origin_period_role))
        material = {
            "schema_version": ANALYTICS_CONTEXT_SCHEMA_VERSION,
            "definition_id": did,
            "revision_number": revision_number,
            "name": nm,
            "description": description.strip(),
            "anchor": anchor.canonical_payload(),
            "conditions": tuple(item.canonical_payload() for item in conds),
            "timeframe": tf,
            "origin_period_role": role,
            "resolver_version": CONTEXT_RESOLVER_VERSION,
        }
        rid = stable_uuid("analytics-context-revision", material)
        fp = stable_digest({**material, "revision_id": rid})
        return cls(did, rid, revision_number, nm, description.strip(), anchor, conds, tf, role, fp)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "definition_id": self.definition_id,
            "revision_id": self.revision_id,
            "revision_number": self.revision_number,
            "name": self.name,
            "description": self.description,
            "anchor": self.anchor.canonical_payload(),
            "conditions": tuple(item.canonical_payload() for item in self.conditions),
            "timeframe": self.timeframe,
            "origin_period_role": self.origin_period_role,
            "resolver_version": self.resolver_version,
            "definition_fingerprint": self.definition_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class AnalyticsSequenceStep:
    step_id: str
    anchor: AnalyticsAnchorSpec
    within_bars: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "step_id",
            normalize_identifier(self.step_id, field_name="step_id")
        )
        if self.within_bars is not None and self.within_bars < 1:
            raise ValueError("within_bars must be >= 1 when present")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "anchor": self.anchor.canonical_payload(),
            "within_bars": self.within_bars
        }


@dataclass(frozen=True, slots=True)
class AnalyticsSequenceDefinition:
    definition_id: str
    revision_id: str
    revision_number: int
    name: str
    description: str
    steps: tuple[AnalyticsSequenceStep, ...]
    final_conditions: tuple[AnalyticsConditionSpec, ...]
    timeframe: str
    origin_period_role: AnalyticsPeriodRole
    definition_fingerprint: str
    resolver_version: str = SEQUENCE_RESOLVER_VERSION
    schema_version: str = ANALYTICS_SEQUENCE_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        definition_id: str,
        revision_number: int,
        name: str,
        description: str,
        steps: Sequence[AnalyticsSequenceStep],
        final_conditions: Sequence[AnalyticsConditionSpec],
        timeframe: str,
        origin_period_role: AnalyticsPeriodRole,
    ) -> AnalyticsSequenceDefinition:
        items = tuple(steps)
        if not 2 <= len(items) <= 10:
            raise ValueError("sequence requires 2 to 10 steps")
        if items[0].within_bars is not None:
            raise ValueError("first sequence step must not define within_bars")
        if any(item.within_bars is None for item in items[1:]):
            raise ValueError("every sequence step after the first requires within_bars")
        tf = normalize_identifier(timeframe, field_name="timeframe")
        if any(item.anchor.timeframe != tf for item in items):
            raise ValueError("sequence step anchors must use the sequence timeframe in v1")
        did = normalize_identifier(definition_id, field_name="definition_id")
        role = origin_period_role if isinstance(
            origin_period_role,
            AnalyticsPeriodRole
        ) else AnalyticsPeriodRole(str(origin_period_role))
        conditions = tuple(final_conditions)
        material = {
            "schema_version": ANALYTICS_SEQUENCE_SCHEMA_VERSION,
            "definition_id": did,
            "revision_number": revision_number,
            "name": name.strip(),
            "description": description.strip(),
            "steps": tuple(item.canonical_payload() for item in items),
            "final_conditions": tuple(item.canonical_payload() for item in conditions),
            "timeframe": tf,
            "origin_period_role": role,
            "resolver_version": SEQUENCE_RESOLVER_VERSION,
        }
        rid = stable_uuid("analytics-sequence-revision", material)
        fp = stable_digest({**material, "revision_id": rid})
        return cls(
            did,
            rid,
            revision_number,
            name.strip(),
            description.strip(),
            items,
            conditions,
            tf,
            role,
            fp
        )


@dataclass(frozen=True, slots=True)
class AnalyticsResearchRun:
    research_run_id: str
    analytics_run_id: str
    definition_id: str
    revision_id: str
    definition_fingerprint: str
    resolver_version: str
    origin_period_role: AnalyticsPeriodRole
    identity_fingerprint: str
    schema_version: str = ANALYTICS_RESEARCH_RUN_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        analytics_run: AnalyticsLabRun,
        definition: AnalyticsContextDefinition | AnalyticsSequenceDefinition
    ) -> AnalyticsResearchRun:
        payload = {
            "schema_version": ANALYTICS_RESEARCH_RUN_SCHEMA_VERSION,
            "analytics_run_id": analytics_run.analytics_run_id,
            "definition_id": definition.definition_id,
            "revision_id": definition.revision_id,
            "definition_fingerprint": definition.definition_fingerprint,
            "resolver_version": definition.resolver_version,
            "origin_period_role": definition.origin_period_role,
        }
        return cls(
            research_run_id=stable_uuid("analytics-research-run", payload),
            analytics_run_id=analytics_run.analytics_run_id,
            definition_id=definition.definition_id,
            revision_id=definition.revision_id,
            definition_fingerprint=definition.definition_fingerprint,
            resolver_version=definition.resolver_version,
            origin_period_role=definition.origin_period_role,
            identity_fingerprint=stable_digest(payload),
        )


@dataclass(frozen=True, slots=True)
class ResolvedAnchor:
    source_type: AnalyticsAnchorType
    source_ref: str
    symbol: str
    timeframe: str
    anchor_at: datetime
    source_fingerprint: str
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "anchor_at", as_utc(self.anchor_at, field_name="anchor_at"))
        object.__setattr__(
            self,
            "source_ref",
            normalize_identifier(self.source_ref, field_name="source_ref")
        )
        object.__setattr__(
            self,
            "source_fingerprint",
            normalize_sha256(self.source_fingerprint, field_name="source_fingerprint")
        )
        object.__setattr__(self, "evidence", _freeze_mapping(self.evidence))


@dataclass(frozen=True, slots=True)
class AnalyticsContextMatch:
    match_id: str
    research_run_id: str
    analytics_run_id: str
    definition_id: str
    revision_id: str
    symbol: str
    timeframe: str
    anchor_ref: str
    anchor_at: datetime
    as_of: datetime
    condition_results: tuple[ConditionEvaluation, ...]
    source_refs: tuple[str, ...]
    match_fingerprint: str
    schema_version: str = ANALYTICS_CONTEXT_MATCH_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        research_run: AnalyticsResearchRun,
        definition: AnalyticsContextDefinition,
        anchor: ResolvedAnchor,
        as_of: datetime,
        condition_results: Sequence[ConditionEvaluation],
    ) -> AnalyticsContextMatch:
        results = tuple(condition_results)
        refs = tuple(sorted({anchor.source_ref, *(r.source_ref for r in results if r.source_ref)}))
        identity = {
            "schema_version": ANALYTICS_CONTEXT_MATCH_SCHEMA_VERSION,
            "research_run_id": research_run.research_run_id,
            "definition_id": definition.definition_id,
            "revision_id": definition.revision_id,
            "symbol": anchor.symbol,
            "timeframe": definition.timeframe,
            "anchor_ref": anchor.source_ref,
            "anchor_at": anchor.anchor_at,
        }
        mid = stable_uuid("analytics-context-match", identity)
        payload = {
            **identity,
            "as_of": as_utc(as_of, field_name="as_of"),
            "condition_results": tuple(r.canonical_payload() for r in results),
            "source_refs": refs
        }
        return cls(
            mid,
            research_run.research_run_id,
            research_run.analytics_run_id,
            definition.definition_id,
            definition.revision_id,
            anchor.symbol,
            definition.timeframe,
            anchor.source_ref,
            anchor.anchor_at,
            payload["as_of"],
            results,
            refs,
            stable_digest(payload),
        )


@dataclass(frozen=True, slots=True)
class SequenceStepMatch:
    step_id: str
    source_type: AnalyticsAnchorType
    source_ref: str
    occurred_at: datetime
    source_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", as_utc(self.occurred_at, field_name="occurred_at"))


@dataclass(frozen=True, slots=True)
class AnalyticsSequenceMatch:
    match_id: str
    research_run_id: str
    analytics_run_id: str
    definition_id: str
    revision_id: str
    symbol: str
    timeframe: str
    started_at: datetime
    completed_at: datetime
    step_matches: tuple[SequenceStepMatch, ...]
    final_condition_results: tuple[ConditionEvaluation, ...]
    source_refs: tuple[str, ...]
    match_fingerprint: str
    schema_version: str = ANALYTICS_SEQUENCE_MATCH_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        research_run: AnalyticsResearchRun,
        definition: AnalyticsSequenceDefinition,
        symbol: str,
        step_matches: Sequence[SequenceStepMatch],
        final_condition_results: Sequence[ConditionEvaluation],
    ) -> AnalyticsSequenceMatch:
        steps = tuple(step_matches)
        conditions = tuple(final_condition_results)
        refs = tuple(sorted({
            *(s.source_ref for s in steps),
            *(r.source_ref for r in conditions if r.source_ref)
        }))
        identity = {
            "schema_version": ANALYTICS_SEQUENCE_MATCH_SCHEMA_VERSION,
            "research_run_id": research_run.research_run_id,
            "definition_id": definition.definition_id,
            "revision_id": definition.revision_id,
            "symbol": symbol,
            "timeframe": definition.timeframe,
            "step_refs": tuple(s.source_ref for s in steps),
        }
        mid = stable_uuid("analytics-sequence-match", identity)
        payload = {
            **identity,
            "started_at": steps[0].occurred_at,
            "completed_at": steps[-1].occurred_at,
            "steps": steps,
            "final_conditions": tuple(r.canonical_payload() for r in conditions),
            "source_refs": refs,
        }
        return cls(
            mid,
            research_run.research_run_id,
            research_run.analytics_run_id,
            definition.definition_id,
            definition.revision_id,
            symbol,
            definition.timeframe,
            steps[0].occurred_at,
            steps[-1].occurred_at,
            steps,
            conditions,
            refs,
            stable_digest(payload),
        )


__all__ = [name for name in globals() if name.startswith("Analytics") or name in {
    "ConditionEvaluation",
    "ResolvedAnchor",
    "SequenceStepMatch"
}]
