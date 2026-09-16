from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .ids import analytics_identity_sha256, analytics_run_id, analytics_snapshot_id
from .provenance import as_utc, normalize_identifier, normalize_sha256

ANALYTICS_RUN_SCHEMA_VERSION = "money-heist.analytics-run.v1"
ANALYTICS_SNAPSHOT_SCHEMA_VERSION = "money-heist.analytics-snapshot.v1"
ANALYTICS_AUTHORITY_POLICY_VERSION = "analytics-observation-only-v1"


class AnalyticsPeriodRole(StrEnum):
    DESIGN = "DESIGN"
    VALIDATION = "VALIDATION"
    OOS = "OOS"


def _normalize_version(value: str, *, field_name: str) -> str:
    return normalize_identifier(value, field_name=field_name)


def _normalize_period_role(value: AnalyticsPeriodRole | str) -> AnalyticsPeriodRole:
    if isinstance(value, AnalyticsPeriodRole):
        return value
    raw = getattr(value, "value", value)
    try:
        return AnalyticsPeriodRole(str(raw))
    except ValueError as exc:
        raise ValueError("period_role must be DESIGN, VALIDATION, or OOS") from exc


def _freeze_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in values.items():
        key_text = normalize_identifier(str(key), field_name="component key")
        normalized[key_text] = _freeze_value(value)
    return MappingProxyType(dict(sorted(normalized.items())))


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class AnalyticsComponentVersions:
    analytics_bundle_version: str
    indicator_registry_version: str
    event_registry_version: str
    structure_version: str
    zigzag_version: str
    pattern_registry_version: str
    context_engine_version: str
    sequence_engine_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "analytics_bundle_version",
            "indicator_registry_version",
            "event_registry_version",
            "structure_version",
            "zigzag_version",
            "pattern_registry_version",
            "context_engine_version",
            "sequence_engine_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_version(getattr(self, field_name), field_name=field_name),
            )

    @classmethod
    def foundation(
        cls,
        *,
        analytics_bundle_version: str = "analytics-lab-foundation-v1",
    ) -> AnalyticsComponentVersions:
        not_installed = "not-installed"
        return cls(
            analytics_bundle_version=analytics_bundle_version,
            indicator_registry_version=not_installed,
            event_registry_version=not_installed,
            structure_version=not_installed,
            zigzag_version=not_installed,
            pattern_registry_version=not_installed,
            context_engine_version=not_installed,
            sequence_engine_version=not_installed,
        )

    def canonical_payload(self) -> dict[str, str]:
        return {
            "analytics_bundle_version": self.analytics_bundle_version,
            "indicator_registry_version": self.indicator_registry_version,
            "event_registry_version": self.event_registry_version,
            "structure_version": self.structure_version,
            "zigzag_version": self.zigzag_version,
            "pattern_registry_version": self.pattern_registry_version,
            "context_engine_version": self.context_engine_version,
            "sequence_engine_version": self.sequence_engine_version,
        }


@dataclass(frozen=True, slots=True)
class AnalyticsAsOfInput:
    source_backtest_run_id: str
    dataset_id: str
    dataset_version: str
    dataset_content_sha256: str
    dataset_source: str
    system_id: str
    symbol: str
    source_timeframe: str
    decision_timeframe: str
    as_of: datetime
    mtf_policy_version: str
    source_cursor_fingerprint: str

    def __post_init__(self) -> None:
        for field_name in (
            "source_backtest_run_id",
            "dataset_id",
            "dataset_version",
            "dataset_source",
            "system_id",
            "symbol",
            "source_timeframe",
            "decision_timeframe",
            "mtf_policy_version",
        ):
            object.__setattr__(
                self,
                field_name,
                normalize_identifier(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "dataset_content_sha256",
            normalize_sha256(
                self.dataset_content_sha256,
                field_name="dataset_content_sha256",
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
        object.__setattr__(self, "as_of", as_utc(self.as_of, field_name="as_of"))

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "source_backtest_run_id": self.source_backtest_run_id,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_content_sha256": self.dataset_content_sha256,
            "dataset_source": self.dataset_source,
            "system_id": self.system_id,
            "symbol": self.symbol,
            "source_timeframe": self.source_timeframe,
            "decision_timeframe": self.decision_timeframe,
            "as_of": self.as_of,
            "mtf_policy_version": self.mtf_policy_version,
            "source_cursor_fingerprint": self.source_cursor_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class AnalyticsLabRun:
    analytics_run_id: str
    identity_sha256: str
    source_backtest_run_id: str
    dataset_id: str
    dataset_version: str
    dataset_content_sha256: str
    dataset_source: str
    system_id: str
    symbol: str
    source_timeframe: str
    decision_timeframe: str
    period_start: datetime
    period_end: datetime
    period_role: AnalyticsPeriodRole
    mtf_policy_version: str
    component_versions: AnalyticsComponentVersions
    schema_version: str = ANALYTICS_RUN_SCHEMA_VERSION
    policy_version: str = ANALYTICS_AUTHORITY_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_RUN_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {ANALYTICS_RUN_SCHEMA_VERSION!r}")
        if self.policy_version != ANALYTICS_AUTHORITY_POLICY_VERSION:
            raise ValueError(f"policy_version must be {ANALYTICS_AUTHORITY_POLICY_VERSION!r}")
        for field_name in (
            "analytics_run_id",
            "source_backtest_run_id",
            "dataset_id",
            "dataset_version",
            "dataset_source",
            "system_id",
            "symbol",
            "source_timeframe",
            "decision_timeframe",
            "mtf_policy_version",
            "schema_version",
            "policy_version",
        ):
            object.__setattr__(
                self,
                field_name,
                normalize_identifier(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "dataset_content_sha256",
            normalize_sha256(
                self.dataset_content_sha256,
                field_name="dataset_content_sha256",
            ),
        )
        object.__setattr__(
            self,
            "identity_sha256",
            normalize_sha256(self.identity_sha256, field_name="identity_sha256"),
        )
        object.__setattr__(self, "period_role", _normalize_period_role(self.period_role))
        start = as_utc(self.period_start, field_name="period_start")
        end = as_utc(self.period_end, field_name="period_end")
        if end < start:
            raise ValueError("period_end cannot precede period_start")
        object.__setattr__(self, "period_start", start)
        object.__setattr__(self, "period_end", end)
        payload = self.identity_payload()
        expected_digest = analytics_identity_sha256(payload)
        if self.identity_sha256 != expected_digest:
            raise ValueError("analytics identity_sha256 does not match run inputs")
        if self.analytics_run_id != analytics_run_id(payload):
            raise ValueError("analytics_run_id does not match run inputs")

    @classmethod
    def create(
        cls,
        *,
        source_backtest_run_id: str,
        dataset_id: str,
        dataset_version: str,
        dataset_content_sha256: str,
        dataset_source: str,
        system_id: str,
        symbol: str,
        source_timeframe: str,
        decision_timeframe: str,
        period_start: datetime,
        period_end: datetime,
        period_role: AnalyticsPeriodRole,
        mtf_policy_version: str,
        component_versions: AnalyticsComponentVersions,
    ) -> AnalyticsLabRun:
        period_role = _normalize_period_role(period_role)
        normalized_start = as_utc(period_start, field_name="period_start")
        normalized_end = as_utc(period_end, field_name="period_end")
        if normalized_end < normalized_start:
            raise ValueError("period_end cannot precede period_start")
        payload = {
            "schema": ANALYTICS_RUN_SCHEMA_VERSION,
            "policy_version": ANALYTICS_AUTHORITY_POLICY_VERSION,
            "source_backtest_run_id": normalize_identifier(
                source_backtest_run_id,
                field_name="source_backtest_run_id",
            ),
            "dataset_id": normalize_identifier(dataset_id, field_name="dataset_id"),
            "dataset_version": normalize_identifier(
                dataset_version,
                field_name="dataset_version",
            ),
            "dataset_content_sha256": normalize_sha256(
                dataset_content_sha256,
                field_name="dataset_content_sha256",
            ),
            "dataset_source": normalize_identifier(
                dataset_source,
                field_name="dataset_source",
            ),
            "system_id": normalize_identifier(system_id, field_name="system_id"),
            "symbol": normalize_identifier(symbol, field_name="symbol"),
            "source_timeframe": normalize_identifier(
                source_timeframe,
                field_name="source_timeframe",
            ),
            "decision_timeframe": normalize_identifier(
                decision_timeframe,
                field_name="decision_timeframe",
            ),
            "period_start": normalized_start,
            "period_end": normalized_end,
            "period_role": period_role,
            "mtf_policy_version": normalize_identifier(
                mtf_policy_version,
                field_name="mtf_policy_version",
            ),
            "component_versions": component_versions.canonical_payload(),
        }
        digest = analytics_identity_sha256(payload)
        return cls(
            analytics_run_id=analytics_run_id(payload),
            identity_sha256=digest,
            source_backtest_run_id=source_backtest_run_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            dataset_content_sha256=dataset_content_sha256,
            dataset_source=dataset_source,
            system_id=system_id,
            symbol=symbol,
            source_timeframe=source_timeframe,
            decision_timeframe=decision_timeframe,
            period_start=normalized_start,
            period_end=normalized_end,
            period_role=period_role,
            mtf_policy_version=mtf_policy_version,
            component_versions=component_versions,
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema_version,
            "policy_version": self.policy_version,
            "source_backtest_run_id": self.source_backtest_run_id,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_content_sha256": self.dataset_content_sha256,
            "dataset_source": self.dataset_source,
            "system_id": self.system_id,
            "symbol": self.symbol,
            "source_timeframe": self.source_timeframe,
            "decision_timeframe": self.decision_timeframe,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "period_role": self.period_role,
            "mtf_policy_version": self.mtf_policy_version,
            "component_versions": self.component_versions.canonical_payload(),
        }


@dataclass(frozen=True, slots=True)
class AnalyticsSnapshot:
    snapshot_id: str
    analytics_run_id: str
    source_backtest_run_id: str
    dataset_id: str
    dataset_version: str
    dataset_content_sha256: str
    symbol: str
    as_of: datetime
    decision_timeframe: str
    mtf_policy_version: str
    source_cursor_fingerprint: str
    component_versions: AnalyticsComponentVersions
    components: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = ANALYTICS_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {ANALYTICS_SNAPSHOT_SCHEMA_VERSION!r}")
        for field_name in (
            "snapshot_id",
            "analytics_run_id",
            "source_backtest_run_id",
            "dataset_id",
            "dataset_version",
            "symbol",
            "decision_timeframe",
            "mtf_policy_version",
            "schema_version",
        ):
            object.__setattr__(
                self,
                field_name,
                normalize_identifier(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "dataset_content_sha256",
            normalize_sha256(
                self.dataset_content_sha256,
                field_name="dataset_content_sha256",
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
        object.__setattr__(self, "as_of", as_utc(self.as_of, field_name="as_of"))
        object.__setattr__(self, "components", _freeze_mapping(self.components))
        if self.snapshot_id != analytics_snapshot_id(self.identity_payload()):
            raise ValueError("snapshot_id does not match snapshot content")

    @property
    def analytics_bundle_version(self) -> str:
        return self.component_versions.analytics_bundle_version

    @classmethod
    def create(
        cls,
        *,
        analytics_run: AnalyticsLabRun,
        as_of_input: AnalyticsAsOfInput,
        components: Mapping[str, Any] | None = None,
    ) -> AnalyticsSnapshot:
        if as_of_input.source_backtest_run_id != analytics_run.source_backtest_run_id:
            raise ValueError("as-of input source_backtest_run_id does not match analytics run")
        for name in (
            "dataset_id",
            "dataset_version",
            "dataset_content_sha256",
            "system_id",
            "symbol",
            "decision_timeframe",
            "mtf_policy_version",
        ):
            if getattr(as_of_input, name) != getattr(analytics_run, name):
                raise ValueError(f"as-of input {name} does not match analytics run")
        if as_of_input.source_timeframe != analytics_run.source_timeframe:
            raise ValueError("as-of input source_timeframe does not match analytics run")
        if not analytics_run.period_start <= as_of_input.as_of <= analytics_run.period_end:
            raise ValueError("snapshot as_of must stay within analytics run period")
        frozen_components = _freeze_mapping(components or {})
        payload = {
            "schema": ANALYTICS_SNAPSHOT_SCHEMA_VERSION,
            "analytics_run_id": analytics_run.analytics_run_id,
            "source_backtest_run_id": analytics_run.source_backtest_run_id,
            "dataset_id": analytics_run.dataset_id,
            "dataset_version": analytics_run.dataset_version,
            "dataset_content_sha256": analytics_run.dataset_content_sha256,
            "symbol": analytics_run.symbol,
            "as_of": as_of_input.as_of,
            "decision_timeframe": analytics_run.decision_timeframe,
            "mtf_policy_version": analytics_run.mtf_policy_version,
            "source_cursor_fingerprint": as_of_input.source_cursor_fingerprint,
            "component_versions": analytics_run.component_versions.canonical_payload(),
            "components": frozen_components,
        }
        return cls(
            snapshot_id=analytics_snapshot_id(payload),
            analytics_run_id=analytics_run.analytics_run_id,
            source_backtest_run_id=analytics_run.source_backtest_run_id,
            dataset_id=analytics_run.dataset_id,
            dataset_version=analytics_run.dataset_version,
            dataset_content_sha256=analytics_run.dataset_content_sha256,
            symbol=analytics_run.symbol,
            as_of=as_of_input.as_of,
            decision_timeframe=analytics_run.decision_timeframe,
            mtf_policy_version=analytics_run.mtf_policy_version,
            source_cursor_fingerprint=as_of_input.source_cursor_fingerprint,
            component_versions=analytics_run.component_versions,
            components=frozen_components,
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema_version,
            "analytics_run_id": self.analytics_run_id,
            "source_backtest_run_id": self.source_backtest_run_id,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_content_sha256": self.dataset_content_sha256,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "decision_timeframe": self.decision_timeframe,
            "mtf_policy_version": self.mtf_policy_version,
            "source_cursor_fingerprint": self.source_cursor_fingerprint,
            "component_versions": self.component_versions.canonical_payload(),
            "components": self.components,
        }


__all__ = [
    "ANALYTICS_AUTHORITY_POLICY_VERSION",
    "ANALYTICS_RUN_SCHEMA_VERSION",
    "ANALYTICS_SNAPSHOT_SCHEMA_VERSION",
    "AnalyticsAsOfInput",
    "AnalyticsComponentVersions",
    "AnalyticsLabRun",
    "AnalyticsPeriodRole",
    "AnalyticsSnapshot",
]
