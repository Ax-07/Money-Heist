from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .ids import canonical_json, stable_digest
from .models import (
    ANALYTICS_AUTHORITY_POLICY_VERSION,
    AnalyticsComponentVersions,
    AnalyticsLabRun,
    AnalyticsPeriodRole,
    AnalyticsSnapshot,
)
from .provenance import as_utc, normalize_identifier, normalize_sha256

ANALYTICS_MANIFEST_SCHEMA_VERSION = "money-heist.analytics-manifest.v1"


@dataclass(frozen=True, slots=True)
class AnalyticsLabManifest:
    schema_version: str
    policy_version: str
    analytics_run_id: str
    source_backtest_run_id: str
    dataset_id: str
    dataset_version: str
    dataset_content_sha256: str
    dataset_source: str
    system_id: str
    source_timeframe: str
    decision_timeframe: str
    period_start: datetime
    period_end: datetime
    period_role: AnalyticsPeriodRole
    mtf_policy_version: str
    component_versions: AnalyticsComponentVersions
    snapshot_count: int
    analytics_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != ANALYTICS_MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {ANALYTICS_MANIFEST_SCHEMA_VERSION!r}")
        if self.policy_version != ANALYTICS_AUTHORITY_POLICY_VERSION:
            raise ValueError(f"policy_version must be {ANALYTICS_AUTHORITY_POLICY_VERSION!r}")
        for field_name in (
            "schema_version",
            "policy_version",
            "analytics_run_id",
            "source_backtest_run_id",
            "dataset_id",
            "dataset_version",
            "dataset_source",
            "system_id",
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
            normalize_sha256(self.dataset_content_sha256, field_name="dataset_content_sha256"),
        )
        object.__setattr__(
            self,
            "analytics_sha256",
            normalize_sha256(self.analytics_sha256, field_name="analytics_sha256"),
        )
        raw_role = getattr(self.period_role, "value", self.period_role)
        try:
            role = AnalyticsPeriodRole(str(raw_role))
        except ValueError as exc:
            raise ValueError("period_role must be DESIGN, VALIDATION, or OOS") from exc
        object.__setattr__(self, "period_role", role)
        start = as_utc(self.period_start, field_name="period_start")
        end = as_utc(self.period_end, field_name="period_end")
        if end < start:
            raise ValueError("period_end cannot precede period_start")
        if self.snapshot_count < 0:
            raise ValueError("snapshot_count must be >= 0")
        object.__setattr__(self, "period_start", start)
        object.__setattr__(self, "period_end", end)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "analytics_run_id": self.analytics_run_id,
            "source_backtest_run_id": self.source_backtest_run_id,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_content_sha256": self.dataset_content_sha256,
            "dataset_source": self.dataset_source,
            "system_id": self.system_id,
            "source_timeframe": self.source_timeframe,
            "decision_timeframe": self.decision_timeframe,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "period_role": self.period_role,
            "mtf_policy_version": self.mtf_policy_version,
            "component_versions": self.component_versions.canonical_payload(),
            "snapshot_count": self.snapshot_count,
            "analytics_sha256": self.analytics_sha256,
        }


def build_analytics_manifest(
    analytics_run: AnalyticsLabRun,
    snapshots: Iterable[AnalyticsSnapshot],
) -> AnalyticsLabManifest:
    ordered = tuple(sorted(snapshots, key=lambda item: (item.as_of, item.snapshot_id)))
    seen_ids: set[str] = set()
    for snapshot in ordered:
        if snapshot.analytics_run_id != analytics_run.analytics_run_id:
            raise ValueError("all snapshots must belong to the analytics run")
        if snapshot.snapshot_id in seen_ids:
            raise ValueError("duplicate analytics snapshot_id")
        seen_ids.add(snapshot.snapshot_id)

    digest_payload = {
        "schema": ANALYTICS_MANIFEST_SCHEMA_VERSION,
        "run": analytics_run.identity_payload(),
        "snapshots": tuple(snapshot.identity_payload() for snapshot in ordered),
    }
    analytics_sha256 = stable_digest(digest_payload)
    return AnalyticsLabManifest(
        schema_version=ANALYTICS_MANIFEST_SCHEMA_VERSION,
        policy_version=analytics_run.policy_version,
        analytics_run_id=analytics_run.analytics_run_id,
        source_backtest_run_id=analytics_run.source_backtest_run_id,
        dataset_id=analytics_run.dataset_id,
        dataset_version=analytics_run.dataset_version,
        dataset_content_sha256=analytics_run.dataset_content_sha256,
        dataset_source=analytics_run.dataset_source,
        system_id=analytics_run.system_id,
        source_timeframe=analytics_run.source_timeframe,
        decision_timeframe=analytics_run.decision_timeframe,
        period_start=analytics_run.period_start,
        period_end=analytics_run.period_end,
        period_role=analytics_run.period_role,
        mtf_policy_version=analytics_run.mtf_policy_version,
        component_versions=analytics_run.component_versions,
        snapshot_count=len(ordered),
        analytics_sha256=analytics_sha256,
    )


def manifest_to_json(manifest: AnalyticsLabManifest) -> str:
    return canonical_json(manifest.canonical_payload())


__all__ = [
    "ANALYTICS_MANIFEST_SCHEMA_VERSION",
    "AnalyticsLabManifest",
    "build_analytics_manifest",
    "manifest_to_json",
]
