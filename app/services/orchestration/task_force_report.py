from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.market.features.models import FeatureSnapshot
from app.market.scanner.models import CandidateOpportunity
from app.task_force.aggregation import TaskForceReport


class TaskForceReportIntegration(BaseModel):
    """Validated advisory payload exposed to the Professor finalization only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["batch20d.task-force-report-integration.v1"] = (
        "batch20d.task-force-report-integration.v1"
    )
    task_force_id: str = Field(min_length=1, max_length=200)
    execution_run_id: str = Field(min_length=1, max_length=200)
    report_fingerprint_sha256: str = Field(min_length=64, max_length=64)
    integrated_at: datetime
    payload: dict[str, Any]
    advisory_only: Literal[True] = True
    trade_proposal_authority: Literal[False] = False
    registry_mutation: Literal[False] = False
    risk_authority: Literal[False] = False
    live_authority: Literal[False] = False

    @field_validator("report_fingerprint_sha256")
    @classmethod
    def _validate_sha(cls, value: str) -> str:
        return _validate_sha256(value)

    @field_validator("integrated_at")
    @classmethod
    def _validate_integrated_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value, field_name="integrated_at")


def task_force_report_fingerprint(report: TaskForceReport) -> str:
    """Recompute the immutable report fingerprint created by Batch 20c Step 3."""

    material = report.model_dump(
        mode="json",
        exclude={"aggregated_at", "report_fingerprint_sha256"},
    )
    return _canonical_sha256(material)


def prepare_task_force_report_for_orchestration(
    report: TaskForceReport,
    *,
    opportunity: CandidateOpportunity,
    market_context: FeatureSnapshot,
    now: datetime | None = None,
) -> TaskForceReportIntegration:
    """Validate one report against the current opportunity before Professor grounding."""

    integrated_at = _ensure_utc(now or datetime.now(UTC), field_name="now")
    _validate_context(
        report=report,
        opportunity=opportunity,
        market_context=market_context,
        integrated_at=integrated_at,
    )
    expected = task_force_report_fingerprint(report)
    if report.report_fingerprint_sha256 != expected:
        raise ValueError("Task Force report fingerprint is stale or inconsistent")

    return TaskForceReportIntegration(
        task_force_id=report.task_force_id,
        execution_run_id=report.execution_run_id,
        report_fingerprint_sha256=report.report_fingerprint_sha256,
        integrated_at=integrated_at,
        payload=report.model_dump(mode="json"),
    )


def _validate_context(
    *,
    report: TaskForceReport,
    opportunity: CandidateOpportunity,
    market_context: FeatureSnapshot,
    integrated_at: datetime,
) -> None:
    opportunity_created_at = _ensure_utc(
        opportunity.created_at,
        field_name="opportunity.created_at",
    )
    opportunity_expires_at = _ensure_utc(
        opportunity.expires_at,
        field_name="opportunity.expires_at",
    )
    observed_at = _ensure_utc(market_context.observed_at, field_name="market_context.observed_at")

    if report.system_id != opportunity.system_id:
        raise ValueError("Task Force report system_id does not match opportunity")
    if report.opportunity_id is None:
        raise ValueError("main orchestration accepts only opportunity-scoped Task Force reports")
    if report.opportunity_id != opportunity.opportunity_id:
        raise ValueError("Task Force report opportunity_id does not match opportunity")
    if opportunity.snapshot_id != market_context.snapshot_id:
        raise ValueError("opportunity snapshot_id does not match market context")
    if opportunity.symbol != market_context.symbol:
        raise ValueError("opportunity symbol does not match market context")
    if opportunity.timeframe != market_context.timeframe:
        raise ValueError("opportunity timeframe does not match market context")
    if not market_context.quality.warmup_complete:
        raise ValueError("feature warmup is incomplete")
    if report.aggregated_at < opportunity_created_at:
        raise ValueError("Task Force report cannot predate the opportunity")
    if report.aggregated_at < observed_at:
        raise ValueError("Task Force report cannot predate its market snapshot")
    if report.aggregated_at > integrated_at:
        raise ValueError("Task Force report cannot come from the future")
    if report.aggregated_at >= opportunity_expires_at:
        raise PermissionError("Task Force report was produced after opportunity expiry")
    if integrated_at >= opportunity_expires_at:
        raise PermissionError("expired opportunity cannot consume a Task Force report")


def _canonical_sha256(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_sha256(value: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise ValueError("fingerprint must be lowercase hexadecimal SHA-256")
    return normalized


def _ensure_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
