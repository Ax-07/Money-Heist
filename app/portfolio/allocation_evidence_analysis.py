from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from itertools import combinations
from typing import Protocol

from app.services.backtest.ids import stable_digest

from .allocation import MasterAllocationPolicy, master_allocation_policy_fingerprint
from .allocation_advisory import (
    MasterAllocationAdvisoryEvidence,
    build_master_allocation_advisory_evidence,
)
from .historical_replay_master_runner import MasterHistoricalCrewEvaluation

ZERO = Decimal("0")


class _MetricLike(Protocol):
    status: object
    value: Decimal | None
    reason: str | None


class MasterAllocationAnalysisMetricStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNBOUNDED = "UNBOUNDED"


class MasterAllocationAnalysisScope(StrEnum):
    ALL_EVIDENCE = "ALL_EVIDENCE"
    REGIME = "REGIME"


class MasterAllocationEvidenceAnalysisStatus(StrEnum):
    ANALYZED = "ANALYZED"


def _required_text(value: object, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank when provided")
    return normalized


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _sha256(value: str, *, field_name: str) -> str:
    normalized = str(value).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return normalized


def _decimal(value: Decimal, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal")
    return value


def _non_negative_decimal(value: Decimal, *, field_name: str) -> Decimal:
    normalized = _decimal(value, field_name=field_name)
    if normalized < ZERO:
        raise ValueError(f"{field_name} must be >= 0")
    return normalized


def _policy_fingerprint(policy: MasterAllocationPolicy) -> str:
    return master_allocation_policy_fingerprint(
        master_portfolio_id=policy.master_portfolio_id,
        policy_id=policy.policy_id,
        members=policy.members,
        envelopes=policy.envelopes,
        status=policy.status,
        reason_codes=policy.reason_codes,
        source=policy.source,
        source_ref=policy.source_ref,
        schema_version=policy.schema_version,
    )


@dataclass(frozen=True, slots=True)
class MasterAllocationAnalysisMetric:
    status: MasterAllocationAnalysisMetricStatus
    value: Decimal | None
    reason: str | None

    def __post_init__(self) -> None:
        if self.status is MasterAllocationAnalysisMetricStatus.AVAILABLE:
            if self.value is None:
                raise ValueError("AVAILABLE analysis metric requires value")
            object.__setattr__(
                self,
                "value",
                _decimal(self.value, field_name="value"),
            )
            if self.reason is not None:
                raise ValueError("AVAILABLE analysis metric cannot carry reason")
            return
        if self.value is not None:
            raise ValueError("non-AVAILABLE analysis metric cannot carry numeric value")
        object.__setattr__(
            self,
            "reason",
            _required_text(self.reason, field_name="reason"),
        )

    @classmethod
    def available(cls, value: Decimal) -> MasterAllocationAnalysisMetric:
        return cls(
            status=MasterAllocationAnalysisMetricStatus.AVAILABLE,
            value=value,
            reason=None,
        )

    @classmethod
    def unavailable(cls, reason: str) -> MasterAllocationAnalysisMetric:
        return cls(
            status=MasterAllocationAnalysisMetricStatus.UNAVAILABLE,
            value=None,
            reason=reason,
        )

    @classmethod
    def unbounded(cls, reason: str) -> MasterAllocationAnalysisMetric:
        return cls(
            status=MasterAllocationAnalysisMetricStatus.UNBOUNDED,
            value=None,
            reason=reason,
        )

    def canonical_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "value": self.value,
            "reason": self.reason,
        }


def _metric_snapshot(
    metric: _MetricLike,
    *,
    field_name: str,
) -> MasterAllocationAnalysisMetric:
    source_status = metric.status
    status_value = source_status.value if isinstance(source_status, StrEnum) else source_status
    source_value = metric.value
    source_reason = metric.reason
    if status_value == MasterAllocationAnalysisMetricStatus.AVAILABLE.value:
        if not isinstance(source_value, Decimal):
            raise ValueError(f"{field_name} AVAILABLE metric requires Decimal value")
        return MasterAllocationAnalysisMetric.available(source_value)
    if status_value == MasterAllocationAnalysisMetricStatus.UNAVAILABLE.value:
        return MasterAllocationAnalysisMetric.unavailable(
            _required_text(source_reason, field_name=f"{field_name}.reason")
        )
    if status_value == MasterAllocationAnalysisMetricStatus.UNBOUNDED.value:
        return MasterAllocationAnalysisMetric.unbounded(
            _required_text(source_reason, field_name=f"{field_name}.reason")
        )
    raise ValueError(f"unsupported {field_name} metric status: {source_status}")


def master_allocation_crew_observation_payload(
    observation: MasterAllocationCrewEvidenceObservation,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-crew-evidence-observation.v1",
        "schema_version": observation.schema_version,
        "evidence_id": observation.evidence_id,
        "evidence_fingerprint_sha256": observation.evidence_fingerprint_sha256,
        "historical_allocation_policy_fingerprint_sha256": (
            observation.historical_allocation_policy_fingerprint_sha256
        ),
        "evaluation_fingerprint_sha256": observation.evaluation_fingerprint_sha256,
        "system_id": observation.system_id,
        "sealed_at": observation.sealed_at,
        "regime_label": observation.regime_label,
        "regime_source_ref": observation.regime_source_ref,
        "entry_count": observation.entry_count,
        "closed_lot_count": observation.closed_lot_count,
        "open_lot_count": observation.open_lot_count,
        "winning_lots": observation.winning_lots,
        "losing_lots": observation.losing_lots,
        "breakeven_lots": observation.breakeven_lots,
        "realized_net_pnl": observation.realized_net_pnl,
        "final_open_risk_amount": observation.final_open_risk_amount,
        "final_gross_exposure_amount": observation.final_gross_exposure_amount,
        "win_rate": observation.win_rate.canonical_payload(),
        "profit_factor": observation.profit_factor.canonical_payload(),
        "expectancy": observation.expectancy.canonical_payload(),
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationCrewEvidenceObservation:
    evidence_id: str
    evidence_fingerprint_sha256: str
    historical_allocation_policy_fingerprint_sha256: str
    evaluation_fingerprint_sha256: str
    system_id: str
    sealed_at: datetime
    regime_label: str | None
    regime_source_ref: str | None
    entry_count: int
    closed_lot_count: int
    open_lot_count: int
    winning_lots: int
    losing_lots: int
    breakeven_lots: int
    realized_net_pnl: Decimal
    final_open_risk_amount: Decimal
    final_gross_exposure_amount: Decimal
    win_rate: MasterAllocationAnalysisMetric
    profit_factor: MasterAllocationAnalysisMetric
    expectancy: MasterAllocationAnalysisMetric
    fingerprint_sha256: str
    advisory_only: bool = field(default=True, init=False)
    physical_capital: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in ("evidence_id", "system_id"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "evidence_fingerprint_sha256",
            "historical_allocation_policy_fingerprint_sha256",
            "evaluation_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(self, "sealed_at", _utc(self.sealed_at, field_name="sealed_at"))
        object.__setattr__(
            self,
            "regime_label",
            _optional_text(self.regime_label, field_name="regime_label"),
        )
        object.__setattr__(
            self,
            "regime_source_ref",
            _optional_text(self.regime_source_ref, field_name="regime_source_ref"),
        )
        if (self.regime_label is None) != (self.regime_source_ref is None):
            raise ValueError("observation regime_label and regime_source_ref must travel together")
        for field_name in (
            "entry_count",
            "closed_lot_count",
            "open_lot_count",
            "winning_lots",
            "losing_lots",
            "breakeven_lots",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be an integer >= 0")
        if self.entry_count != self.closed_lot_count + self.open_lot_count:
            raise ValueError("crew observation entry_count must equal closed + open lots")
        if self.closed_lot_count != (
            self.winning_lots + self.losing_lots + self.breakeven_lots
        ):
            raise ValueError("crew observation closed-lot outcomes are inconsistent")
        object.__setattr__(
            self,
            "realized_net_pnl",
            _decimal(self.realized_net_pnl, field_name="realized_net_pnl"),
        )
        for field_name in ("final_open_risk_amount", "final_gross_exposure_amount"):
            object.__setattr__(
                self,
                field_name,
                _non_negative_decimal(getattr(self, field_name), field_name=field_name),
            )
        if self.schema_version != "1.0":
            raise ValueError("unsupported crew evidence observation schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_allocation_crew_observation_payload(self))
        if normalized != expected:
            raise ValueError("crew evidence observation fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_crew_observation_payload(self)


def _build_observation(
    *,
    evidence: MasterAllocationAdvisoryEvidence,
    crew: MasterHistoricalCrewEvaluation,
) -> MasterAllocationCrewEvidenceObservation:
    body = {
        "schema": "money-heist.master-allocation-crew-evidence-observation.v1",
        "schema_version": "1.0",
        "evidence_id": evidence.evidence_id,
        "evidence_fingerprint_sha256": evidence.fingerprint_sha256,
        "historical_allocation_policy_fingerprint_sha256": (
            evidence.audit_report.allocation_policy_fingerprint_sha256
        ),
        "evaluation_fingerprint_sha256": evidence.evaluation.fingerprint_sha256,
        "system_id": crew.system_id,
        "sealed_at": evidence.sealed_at,
        "regime_label": evidence.regime_label,
        "regime_source_ref": evidence.regime_source_ref,
        "entry_count": crew.entry_count,
        "closed_lot_count": crew.closed_lot_count,
        "open_lot_count": crew.open_lot_count,
        "winning_lots": crew.winning_lots,
        "losing_lots": crew.losing_lots,
        "breakeven_lots": crew.breakeven_lots,
        "realized_net_pnl": crew.realized_net_pnl,
        "final_open_risk_amount": crew.final_open_risk_amount,
        "final_gross_exposure_amount": crew.final_gross_exposure_amount,
        "win_rate": _metric_snapshot(crew.win_rate, field_name="win_rate")
        .canonical_payload(),
        "profit_factor": _metric_snapshot(
            crew.profit_factor,
            field_name="profit_factor",
        ).canonical_payload(),
        "expectancy": _metric_snapshot(
            crew.expectancy,
            field_name="expectancy",
        ).canonical_payload(),
    }
    return MasterAllocationCrewEvidenceObservation(
        evidence_id=evidence.evidence_id,
        evidence_fingerprint_sha256=evidence.fingerprint_sha256,
        historical_allocation_policy_fingerprint_sha256=(
            evidence.audit_report.allocation_policy_fingerprint_sha256
        ),
        evaluation_fingerprint_sha256=evidence.evaluation.fingerprint_sha256,
        system_id=crew.system_id,
        sealed_at=evidence.sealed_at,
        regime_label=evidence.regime_label,
        regime_source_ref=evidence.regime_source_ref,
        entry_count=crew.entry_count,
        closed_lot_count=crew.closed_lot_count,
        open_lot_count=crew.open_lot_count,
        winning_lots=crew.winning_lots,
        losing_lots=crew.losing_lots,
        breakeven_lots=crew.breakeven_lots,
        realized_net_pnl=crew.realized_net_pnl,
        final_open_risk_amount=crew.final_open_risk_amount,
        final_gross_exposure_amount=crew.final_gross_exposure_amount,
        win_rate=_metric_snapshot(crew.win_rate, field_name="win_rate"),
        profit_factor=_metric_snapshot(
            crew.profit_factor,
            field_name="profit_factor",
        ),
        expectancy=_metric_snapshot(
            crew.expectancy,
            field_name="expectancy",
        ),
        fingerprint_sha256=stable_digest(body),
    )


def master_allocation_crew_analysis_payload(
    analysis: MasterAllocationCrewAnalysis,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-crew-analysis.v1",
        "schema_version": analysis.schema_version,
        "scope": analysis.scope,
        "regime_label": analysis.regime_label,
        "regime_source_ref": analysis.regime_source_ref,
        "system_id": analysis.system_id,
        "evidence_ids": analysis.evidence_ids,
        "evidence_count": analysis.evidence_count,
        "entry_count": analysis.entry_count,
        "closed_lot_count": analysis.closed_lot_count,
        "open_lot_count": analysis.open_lot_count,
        "winning_lots": analysis.winning_lots,
        "losing_lots": analysis.losing_lots,
        "breakeven_lots": analysis.breakeven_lots,
        "replay_realized_net_pnl_sum": analysis.replay_realized_net_pnl_sum,
        "mean_replay_realized_net_pnl": analysis.mean_replay_realized_net_pnl,
        "pooled_win_rate": analysis.pooled_win_rate.canonical_payload(),
        "pooled_expectancy": analysis.pooled_expectancy.canonical_payload(),
        "open_position_evidence_count": analysis.open_position_evidence_count,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationCrewAnalysis:
    scope: MasterAllocationAnalysisScope
    regime_label: str | None
    regime_source_ref: str | None
    system_id: str
    evidence_ids: tuple[str, ...]
    evidence_count: int
    entry_count: int
    closed_lot_count: int
    open_lot_count: int
    winning_lots: int
    losing_lots: int
    breakeven_lots: int
    replay_realized_net_pnl_sum: Decimal
    mean_replay_realized_net_pnl: Decimal
    pooled_win_rate: MasterAllocationAnalysisMetric
    pooled_expectancy: MasterAllocationAnalysisMetric
    open_position_evidence_count: int
    fingerprint_sha256: str
    advisory_only: bool = field(default=True, init=False)
    score_generated: bool = field(default=False, init=False)
    physical_capital_aggregation: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        object.__setattr__(
            self,
            "regime_label",
            _optional_text(self.regime_label, field_name="regime_label"),
        )
        object.__setattr__(
            self,
            "regime_source_ref",
            _optional_text(self.regime_source_ref, field_name="regime_source_ref"),
        )
        if self.scope not in {
            MasterAllocationAnalysisScope.ALL_EVIDENCE,
            MasterAllocationAnalysisScope.REGIME,
        }:
            raise ValueError(f"unsupported allocation analysis scope: {self.scope}")
        if (
            self.scope is MasterAllocationAnalysisScope.ALL_EVIDENCE
            and (self.regime_label is not None or self.regime_source_ref is not None)
        ):
            raise ValueError("ALL_EVIDENCE analysis cannot carry regime metadata")
        if (
            self.scope is MasterAllocationAnalysisScope.REGIME
            and (self.regime_label is None or self.regime_source_ref is None)
        ):
            raise ValueError("REGIME analysis requires exact regime provenance")
        if not self.evidence_ids:
            raise ValueError("crew analysis requires evidence_ids")
        if self.evidence_ids != tuple(sorted(self.evidence_ids)):
            raise ValueError("crew analysis evidence_ids must be sorted")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("crew analysis evidence_ids must be unique")
        if self.evidence_count != len(self.evidence_ids):
            raise ValueError("crew analysis evidence_count mismatch")
        for field_name in (
            "entry_count",
            "closed_lot_count",
            "open_lot_count",
            "winning_lots",
            "losing_lots",
            "breakeven_lots",
            "open_position_evidence_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be an integer >= 0")
        if self.entry_count != self.closed_lot_count + self.open_lot_count:
            raise ValueError("crew analysis entry_count must equal closed + open lots")
        if self.closed_lot_count != (
            self.winning_lots + self.losing_lots + self.breakeven_lots
        ):
            raise ValueError("crew analysis closed-lot outcomes are inconsistent")
        if self.open_position_evidence_count > self.evidence_count:
            raise ValueError("open_position_evidence_count cannot exceed evidence_count")
        object.__setattr__(
            self,
            "replay_realized_net_pnl_sum",
            _decimal(
                self.replay_realized_net_pnl_sum,
                field_name="replay_realized_net_pnl_sum",
            ),
        )
        object.__setattr__(
            self,
            "mean_replay_realized_net_pnl",
            _decimal(
                self.mean_replay_realized_net_pnl,
                field_name="mean_replay_realized_net_pnl",
            ),
        )
        expected_mean = self.replay_realized_net_pnl_sum / Decimal(self.evidence_count)
        if self.mean_replay_realized_net_pnl != expected_mean:
            raise ValueError("crew analysis mean replay PnL mismatch")
        if self.schema_version != "1.0":
            raise ValueError("unsupported crew analysis schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_allocation_crew_analysis_payload(self))
        if normalized != expected:
            raise ValueError("crew analysis fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_crew_analysis_payload(self)


def _pooled_metric(
    *,
    numerator: Decimal,
    denominator: int,
    unavailable_reason: str,
) -> MasterAllocationAnalysisMetric:
    if denominator == 0:
        return MasterAllocationAnalysisMetric.unavailable(unavailable_reason)
    return MasterAllocationAnalysisMetric.available(numerator / Decimal(denominator))


def _build_crew_analysis(
    *,
    scope: MasterAllocationAnalysisScope,
    regime_label: str | None,
    regime_source_ref: str | None,
    observations: tuple[MasterAllocationCrewEvidenceObservation, ...],
) -> MasterAllocationCrewAnalysis:
    if not observations:
        raise ValueError("cannot build crew analysis without observations")
    system_ids = {item.system_id for item in observations}
    if len(system_ids) != 1:
        raise ValueError("crew analysis observations must target one system_id")
    evidence_ids = tuple(sorted(item.evidence_id for item in observations))
    entry_count = sum(item.entry_count for item in observations)
    closed_lot_count = sum(item.closed_lot_count for item in observations)
    open_lot_count = sum(item.open_lot_count for item in observations)
    winning_lots = sum(item.winning_lots for item in observations)
    losing_lots = sum(item.losing_lots for item in observations)
    breakeven_lots = sum(item.breakeven_lots for item in observations)
    replay_pnl_sum = sum((item.realized_net_pnl for item in observations), ZERO)
    mean_replay_pnl = replay_pnl_sum / Decimal(len(observations))
    pooled_win_rate = _pooled_metric(
        numerator=Decimal(winning_lots),
        denominator=closed_lot_count,
        unavailable_reason="NO_CLOSED_LOTS_IN_ANALYSIS_SCOPE",
    )
    pooled_expectancy = _pooled_metric(
        numerator=replay_pnl_sum,
        denominator=closed_lot_count,
        unavailable_reason="NO_CLOSED_LOTS_IN_ANALYSIS_SCOPE",
    )
    open_position_evidence_count = sum(item.open_lot_count > 0 for item in observations)
    provisional = MasterAllocationCrewAnalysis.__new__(MasterAllocationCrewAnalysis)
    for name, value in {
        "scope": scope,
        "regime_label": regime_label,
        "regime_source_ref": regime_source_ref,
        "system_id": next(iter(system_ids)),
        "evidence_ids": evidence_ids,
        "evidence_count": len(observations),
        "entry_count": entry_count,
        "closed_lot_count": closed_lot_count,
        "open_lot_count": open_lot_count,
        "winning_lots": winning_lots,
        "losing_lots": losing_lots,
        "breakeven_lots": breakeven_lots,
        "replay_realized_net_pnl_sum": replay_pnl_sum,
        "mean_replay_realized_net_pnl": mean_replay_pnl,
        "pooled_win_rate": pooled_win_rate,
        "pooled_expectancy": pooled_expectancy,
        "open_position_evidence_count": open_position_evidence_count,
        "schema_version": "1.0",
    }.items():
        object.__setattr__(provisional, name, value)
    fingerprint = stable_digest(master_allocation_crew_analysis_payload(provisional))
    return MasterAllocationCrewAnalysis(
        scope=scope,
        regime_label=regime_label,
        regime_source_ref=regime_source_ref,
        system_id=next(iter(system_ids)),
        evidence_ids=evidence_ids,
        evidence_count=len(observations),
        entry_count=entry_count,
        closed_lot_count=closed_lot_count,
        open_lot_count=open_lot_count,
        winning_lots=winning_lots,
        losing_lots=losing_lots,
        breakeven_lots=breakeven_lots,
        replay_realized_net_pnl_sum=replay_pnl_sum,
        mean_replay_realized_net_pnl=mean_replay_pnl,
        pooled_win_rate=pooled_win_rate,
        pooled_expectancy=pooled_expectancy,
        open_position_evidence_count=open_position_evidence_count,
        fingerprint_sha256=fingerprint,
    )


def master_allocation_pairwise_comparison_payload(
    comparison: MasterAllocationPairwiseComparison,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-pairwise-comparison.v1",
        "schema_version": comparison.schema_version,
        "scope": comparison.scope,
        "regime_label": comparison.regime_label,
        "regime_source_ref": comparison.regime_source_ref,
        "left_system_id": comparison.left_system_id,
        "right_system_id": comparison.right_system_id,
        "evidence_ids": comparison.evidence_ids,
        "evidence_count": comparison.evidence_count,
        "realized_pnl_left_better_count": comparison.realized_pnl_left_better_count,
        "realized_pnl_right_better_count": comparison.realized_pnl_right_better_count,
        "realized_pnl_tie_count": comparison.realized_pnl_tie_count,
        "mean_realized_net_pnl_delta": comparison.mean_realized_net_pnl_delta,
        "win_rate_comparison_count": comparison.win_rate_comparison_count,
        "win_rate_left_better_count": comparison.win_rate_left_better_count,
        "win_rate_right_better_count": comparison.win_rate_right_better_count,
        "win_rate_tie_count": comparison.win_rate_tie_count,
        "mean_win_rate_delta": comparison.mean_win_rate_delta.canonical_payload(),
        "expectancy_comparison_count": comparison.expectancy_comparison_count,
        "expectancy_left_better_count": comparison.expectancy_left_better_count,
        "expectancy_right_better_count": comparison.expectancy_right_better_count,
        "expectancy_tie_count": comparison.expectancy_tie_count,
        "mean_expectancy_delta": comparison.mean_expectancy_delta.canonical_payload(),
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationPairwiseComparison:
    scope: MasterAllocationAnalysisScope
    regime_label: str | None
    regime_source_ref: str | None
    left_system_id: str
    right_system_id: str
    evidence_ids: tuple[str, ...]
    evidence_count: int
    realized_pnl_left_better_count: int
    realized_pnl_right_better_count: int
    realized_pnl_tie_count: int
    mean_realized_net_pnl_delta: Decimal
    win_rate_comparison_count: int
    win_rate_left_better_count: int
    win_rate_right_better_count: int
    win_rate_tie_count: int
    mean_win_rate_delta: MasterAllocationAnalysisMetric
    expectancy_comparison_count: int
    expectancy_left_better_count: int
    expectancy_right_better_count: int
    expectancy_tie_count: int
    mean_expectancy_delta: MasterAllocationAnalysisMetric
    fingerprint_sha256: str
    advisory_only: bool = field(default=True, init=False)
    ranking_generated: bool = field(default=False, init=False)
    score_generated: bool = field(default=False, init=False)
    allocation_generated: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "left_system_id",
            _required_text(self.left_system_id, field_name="left_system_id"),
        )
        object.__setattr__(
            self,
            "right_system_id",
            _required_text(self.right_system_id, field_name="right_system_id"),
        )
        if self.left_system_id >= self.right_system_id:
            raise ValueError("pairwise comparison system ids must be canonical and distinct")
        object.__setattr__(
            self,
            "regime_label",
            _optional_text(self.regime_label, field_name="regime_label"),
        )
        object.__setattr__(
            self,
            "regime_source_ref",
            _optional_text(self.regime_source_ref, field_name="regime_source_ref"),
        )
        if self.scope not in {
            MasterAllocationAnalysisScope.ALL_EVIDENCE,
            MasterAllocationAnalysisScope.REGIME,
        }:
            raise ValueError(f"unsupported pairwise comparison scope: {self.scope}")
        if (
            self.scope is MasterAllocationAnalysisScope.ALL_EVIDENCE
            and (self.regime_label is not None or self.regime_source_ref is not None)
        ):
            raise ValueError("ALL_EVIDENCE comparison cannot carry regime metadata")
        if (
            self.scope is MasterAllocationAnalysisScope.REGIME
            and (self.regime_label is None or self.regime_source_ref is None)
        ):
            raise ValueError("REGIME comparison requires exact regime provenance")
        if not self.evidence_ids:
            raise ValueError("pairwise comparison requires evidence_ids")
        if self.evidence_ids != tuple(sorted(self.evidence_ids)):
            raise ValueError("pairwise evidence_ids must be sorted")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("pairwise evidence_ids must be unique")
        if self.evidence_count != len(self.evidence_ids):
            raise ValueError("pairwise evidence_count mismatch")
        for field_name in (
            "realized_pnl_left_better_count",
            "realized_pnl_right_better_count",
            "realized_pnl_tie_count",
            "win_rate_comparison_count",
            "win_rate_left_better_count",
            "win_rate_right_better_count",
            "win_rate_tie_count",
            "expectancy_comparison_count",
            "expectancy_left_better_count",
            "expectancy_right_better_count",
            "expectancy_tie_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be an integer >= 0")
        if self.evidence_count != (
            self.realized_pnl_left_better_count
            + self.realized_pnl_right_better_count
            + self.realized_pnl_tie_count
        ):
            raise ValueError("realized PnL pairwise outcome counts are inconsistent")
        if self.win_rate_comparison_count != (
            self.win_rate_left_better_count
            + self.win_rate_right_better_count
            + self.win_rate_tie_count
        ):
            raise ValueError("win-rate pairwise outcome counts are inconsistent")
        if self.expectancy_comparison_count != (
            self.expectancy_left_better_count
            + self.expectancy_right_better_count
            + self.expectancy_tie_count
        ):
            raise ValueError("expectancy pairwise outcome counts are inconsistent")
        object.__setattr__(
            self,
            "mean_realized_net_pnl_delta",
            _decimal(
                self.mean_realized_net_pnl_delta,
                field_name="mean_realized_net_pnl_delta",
            ),
        )
        if self.schema_version != "1.0":
            raise ValueError("unsupported pairwise comparison schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_allocation_pairwise_comparison_payload(self))
        if normalized != expected:
            raise ValueError("pairwise comparison fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_pairwise_comparison_payload(self)


def _available_value(metric: MasterAllocationAnalysisMetric) -> Decimal | None:
    if metric.status is not MasterAllocationAnalysisMetricStatus.AVAILABLE:
        return None
    return metric.value


def _outcome_counts(deltas: tuple[Decimal, ...]) -> tuple[int, int, int]:
    left = sum(value > ZERO for value in deltas)
    right = sum(value < ZERO for value in deltas)
    ties = len(deltas) - left - right
    return left, right, ties


def _mean_delta_metric(
    deltas: tuple[Decimal, ...],
    *,
    unavailable_reason: str,
) -> MasterAllocationAnalysisMetric:
    if not deltas:
        return MasterAllocationAnalysisMetric.unavailable(unavailable_reason)
    return MasterAllocationAnalysisMetric.available(sum(deltas, ZERO) / Decimal(len(deltas)))


def _build_pairwise_comparison(
    *,
    scope: MasterAllocationAnalysisScope,
    regime_label: str | None,
    regime_source_ref: str | None,
    left_system_id: str,
    right_system_id: str,
    observations: tuple[MasterAllocationCrewEvidenceObservation, ...],
) -> MasterAllocationPairwiseComparison:
    by_evidence: dict[str, dict[str, MasterAllocationCrewEvidenceObservation]] = {}
    for observation in observations:
        by_evidence.setdefault(observation.evidence_id, {})[observation.system_id] = observation
    pairs = []
    for evidence_id, values in by_evidence.items():
        if set(values) != {left_system_id, right_system_id}:
            raise ValueError("pairwise comparison requires both crews in every evidence item")
        pairs.append((evidence_id, values[left_system_id], values[right_system_id]))
    pairs.sort(key=lambda item: item[0])
    evidence_ids = tuple(item[0] for item in pairs)
    realized_deltas = tuple(
        left.realized_net_pnl - right.realized_net_pnl
        for _, left, right in pairs
    )
    realized_left, realized_right, realized_ties = _outcome_counts(realized_deltas)
    win_rate_deltas = tuple(
        left_value - right_value
        for _, left, right in pairs
        if (left_value := _available_value(left.win_rate)) is not None
        and (right_value := _available_value(right.win_rate)) is not None
    )
    win_left, win_right, win_ties = _outcome_counts(win_rate_deltas)
    expectancy_deltas = tuple(
        left_value - right_value
        for _, left, right in pairs
        if (left_value := _available_value(left.expectancy)) is not None
        and (right_value := _available_value(right.expectancy)) is not None
    )
    exp_left, exp_right, exp_ties = _outcome_counts(expectancy_deltas)
    mean_realized = sum(realized_deltas, ZERO) / Decimal(len(realized_deltas))
    mean_win_rate = _mean_delta_metric(
        win_rate_deltas,
        unavailable_reason="NO_PAIRED_AVAILABLE_WIN_RATE",
    )
    mean_expectancy = _mean_delta_metric(
        expectancy_deltas,
        unavailable_reason="NO_PAIRED_AVAILABLE_EXPECTANCY",
    )
    provisional = MasterAllocationPairwiseComparison.__new__(MasterAllocationPairwiseComparison)
    values = {
        "scope": scope,
        "regime_label": regime_label,
        "regime_source_ref": regime_source_ref,
        "left_system_id": left_system_id,
        "right_system_id": right_system_id,
        "evidence_ids": evidence_ids,
        "evidence_count": len(evidence_ids),
        "realized_pnl_left_better_count": realized_left,
        "realized_pnl_right_better_count": realized_right,
        "realized_pnl_tie_count": realized_ties,
        "mean_realized_net_pnl_delta": mean_realized,
        "win_rate_comparison_count": len(win_rate_deltas),
        "win_rate_left_better_count": win_left,
        "win_rate_right_better_count": win_right,
        "win_rate_tie_count": win_ties,
        "mean_win_rate_delta": mean_win_rate,
        "expectancy_comparison_count": len(expectancy_deltas),
        "expectancy_left_better_count": exp_left,
        "expectancy_right_better_count": exp_right,
        "expectancy_tie_count": exp_ties,
        "mean_expectancy_delta": mean_expectancy,
        "schema_version": "1.0",
    }
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    fingerprint = stable_digest(master_allocation_pairwise_comparison_payload(provisional))
    return MasterAllocationPairwiseComparison(
        **{name: value for name, value in values.items() if name != "schema_version"},
        fingerprint_sha256=fingerprint,
    )


def master_allocation_evidence_analysis_payload(
    report: MasterAllocationEvidenceAnalysisReport,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-evidence-analysis.v1",
        "schema_version": report.schema_version,
        "analysis_id": report.analysis_id,
        "status": report.status,
        "master_portfolio_id": report.master_portfolio_id,
        "current_policy_fingerprint_sha256": report.current_policy_fingerprint_sha256,
        "evidence_through": report.evidence_through,
        "evidence_fingerprints_sha256": report.evidence_fingerprints_sha256,
        "historical_allocation_policy_fingerprints_sha256": (
            report.historical_allocation_policy_fingerprints_sha256
        ),
        "regime_keys": report.regime_keys,
        "unlabeled_evidence_count": report.unlabeled_evidence_count,
        "reason_codes": report.reason_codes,
        "observation_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in report.observations
        ),
        "crew_analysis_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in report.crew_analyses
        ),
        "pairwise_comparison_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in report.pairwise_comparisons
        ),
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationEvidenceAnalysisReport:
    analysis_id: str
    status: MasterAllocationEvidenceAnalysisStatus
    master_portfolio_id: str
    current_policy_fingerprint_sha256: str
    evidence_through: datetime
    evidence_fingerprints_sha256: tuple[str, ...]
    historical_allocation_policy_fingerprints_sha256: tuple[str, ...]
    regime_keys: tuple[tuple[str, str], ...]
    unlabeled_evidence_count: int
    reason_codes: tuple[str, ...]
    observations: tuple[MasterAllocationCrewEvidenceObservation, ...]
    crew_analyses: tuple[MasterAllocationCrewAnalysis, ...]
    pairwise_comparisons: tuple[MasterAllocationPairwiseComparison, ...]
    fingerprint_sha256: str
    advisor_role: str = field(default="MASTER_PROFESSOR", init=False)
    mode: str = field(default="SHADOW", init=False)
    advisory_only: bool = field(default=True, init=False)
    descriptive_analysis_only: bool = field(default=True, init=False)
    recommendation_generated: bool = field(default=False, init=False)
    allocation_generated: bool = field(default=False, init=False)
    score_generated: bool = field(default=False, init=False)
    ranking_generated: bool = field(default=False, init=False)
    optimization_performed: bool = field(default=False, init=False)
    statistical_correlation_inferred: bool = field(default=False, init=False)
    kelly_sizing: bool = field(default=False, init=False)
    policy_mutation: bool = field(default=False, init=False)
    reservation_authority: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    physical_capital_aggregation: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in ("analysis_id", "master_portfolio_id"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "current_policy_fingerprint_sha256",
            _sha256(
                self.current_policy_fingerprint_sha256,
                field_name="current_policy_fingerprint_sha256",
            ),
        )
        object.__setattr__(
            self,
            "evidence_through",
            _utc(self.evidence_through, field_name="evidence_through"),
        )
        if self.status is not MasterAllocationEvidenceAnalysisStatus.ANALYZED:
            raise ValueError("Master allocation evidence analysis status must be ANALYZED")
        if not self.evidence_fingerprints_sha256:
            raise ValueError("Master allocation evidence analysis requires evidence")
        normalized_evidence_fingerprints = tuple(
            _sha256(value, field_name="evidence_fingerprints_sha256")
            for value in self.evidence_fingerprints_sha256
        )
        if len(set(normalized_evidence_fingerprints)) != len(normalized_evidence_fingerprints):
            raise ValueError("analysis evidence fingerprints must be unique")
        object.__setattr__(
            self,
            "evidence_fingerprints_sha256",
            normalized_evidence_fingerprints,
        )
        normalized_policy_fingerprints = tuple(
            _sha256(value, field_name="historical_allocation_policy_fingerprints_sha256")
            for value in self.historical_allocation_policy_fingerprints_sha256
        )
        if normalized_policy_fingerprints != tuple(sorted(normalized_policy_fingerprints)):
            raise ValueError("historical allocation policy fingerprints must be sorted")
        if len(set(normalized_policy_fingerprints)) != len(normalized_policy_fingerprints):
            raise ValueError("historical allocation policy fingerprints must be unique")
        object.__setattr__(
            self,
            "historical_allocation_policy_fingerprints_sha256",
            normalized_policy_fingerprints,
        )
        if self.regime_keys != tuple(sorted(self.regime_keys)):
            raise ValueError("regime_keys must be canonical")
        if len(set(self.regime_keys)) != len(self.regime_keys):
            raise ValueError("regime_keys must be unique")
        for label, source_ref in self.regime_keys:
            _required_text(label, field_name="regime_label")
            _required_text(source_ref, field_name="regime_source_ref")
        if isinstance(self.unlabeled_evidence_count, bool) or self.unlabeled_evidence_count < 0:
            raise ValueError("unlabeled_evidence_count must be an integer >= 0")
        if self.unlabeled_evidence_count > len(self.evidence_fingerprints_sha256):
            raise ValueError("unlabeled_evidence_count cannot exceed evidence count")
        normalized_reasons = tuple(
            _required_text(value, field_name="reason_codes") for value in self.reason_codes
        )
        if normalized_reasons != tuple(sorted(normalized_reasons)):
            raise ValueError("analysis reason_codes must be sorted")
        if len(set(normalized_reasons)) != len(normalized_reasons):
            raise ValueError("analysis reason_codes must be unique")
        object.__setattr__(self, "reason_codes", normalized_reasons)
        observation_keys = tuple(
            (item.system_id, item.sealed_at, item.evidence_id) for item in self.observations
        )
        if observation_keys != tuple(sorted(observation_keys)):
            raise ValueError("analysis observations must be canonical")
        if not self.observations:
            raise ValueError("analysis requires crew observations")
        analysis_keys = tuple(
            (
                item.scope.value,
                item.regime_label or "",
                item.regime_source_ref or "",
                item.system_id,
            )
            for item in self.crew_analyses
        )
        if analysis_keys != tuple(sorted(analysis_keys)):
            raise ValueError("crew analyses must be canonical")
        pairwise_keys = tuple(
            (
                item.scope.value,
                item.regime_label or "",
                item.regime_source_ref or "",
                item.left_system_id,
                item.right_system_id,
            )
            for item in self.pairwise_comparisons
        )
        if pairwise_keys != tuple(sorted(pairwise_keys)):
            raise ValueError("pairwise comparisons must be canonical")
        if self.schema_version != "1.0":
            raise ValueError("unsupported evidence analysis schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = stable_digest(master_allocation_evidence_analysis_payload(self))
        if normalized != expected:
            raise ValueError("Master allocation evidence analysis fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_evidence_analysis_payload(self)


def _validate_and_order_evidence(
    *,
    current_allocation_policy: MasterAllocationPolicy,
    evidence: tuple[MasterAllocationAdvisoryEvidence, ...],
) -> tuple[MasterAllocationAdvisoryEvidence, ...]:
    if _policy_fingerprint(current_allocation_policy) != (
        current_allocation_policy.fingerprint_sha256
    ):
        raise ValueError("evidence analysis current policy fingerprint integrity failure")
    if not evidence:
        raise ValueError("evidence analysis requires at least one sealed evidence item")
    ordered = tuple(sorted(evidence, key=lambda item: (item.sealed_at, item.evidence_id)))
    fingerprints = tuple(item.fingerprint_sha256 for item in ordered)
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("evidence analysis requires unique evidence fingerprints")
    policy_system_ids = tuple(member.system_id for member in current_allocation_policy.members)
    for item in ordered:
        rebuilt = build_master_allocation_advisory_evidence(
            audit_report=item.audit_report,
            closure_seal=item.closure_seal,
            evaluation=item.evaluation,
            regime_label=item.regime_label,
            regime_source_ref=item.regime_source_ref,
        )
        if rebuilt.evidence_id != item.evidence_id or (
            rebuilt.fingerprint_sha256 != item.fingerprint_sha256
        ):
            raise ValueError("evidence analysis source evidence integrity failure")
        if item.master_portfolio_id != current_allocation_policy.master_portfolio_id:
            raise ValueError("evidence analysis spans multiple Master Portfolios")
        if item.crew_system_ids != policy_system_ids:
            raise ValueError("evidence analysis membership mismatch")
    return ordered


def _build_observations(
    evidence: tuple[MasterAllocationAdvisoryEvidence, ...],
) -> tuple[MasterAllocationCrewEvidenceObservation, ...]:
    values = []
    for item in evidence:
        for crew in item.evaluation.crew_evaluations:
            values.append(_build_observation(evidence=item, crew=crew))
    return tuple(
        sorted(
            values,
            key=lambda item: (item.system_id, item.sealed_at, item.evidence_id),
        )
    )


def _regime_keys(
    evidence: tuple[MasterAllocationAdvisoryEvidence, ...],
) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            {
                (item.regime_label, item.regime_source_ref)
                for item in evidence
                if item.regime_label is not None and item.regime_source_ref is not None
            }
        )
    )


def _crew_analyses(
    *,
    system_ids: tuple[str, ...],
    observations: tuple[MasterAllocationCrewEvidenceObservation, ...],
    regime_keys: tuple[tuple[str, str], ...],
) -> tuple[MasterAllocationCrewAnalysis, ...]:
    analyses = []
    for system_id in system_ids:
        crew_observations = tuple(item for item in observations if item.system_id == system_id)
        analyses.append(
            _build_crew_analysis(
                scope=MasterAllocationAnalysisScope.ALL_EVIDENCE,
                regime_label=None,
                regime_source_ref=None,
                observations=crew_observations,
            )
        )
        for regime_label, regime_source_ref in regime_keys:
            regime_observations = tuple(
                item
                for item in crew_observations
                if item.regime_label == regime_label
                and item.regime_source_ref == regime_source_ref
            )
            if regime_observations:
                analyses.append(
                    _build_crew_analysis(
                        scope=MasterAllocationAnalysisScope.REGIME,
                        regime_label=regime_label,
                        regime_source_ref=regime_source_ref,
                        observations=regime_observations,
                    )
                )
    return tuple(
        sorted(
            analyses,
            key=lambda item: (
                item.scope.value,
                item.regime_label or "",
                item.regime_source_ref or "",
                item.system_id,
            ),
        )
    )


def _pairwise_comparisons(
    *,
    system_ids: tuple[str, ...],
    observations: tuple[MasterAllocationCrewEvidenceObservation, ...],
    regime_keys: tuple[tuple[str, str], ...],
) -> tuple[MasterAllocationPairwiseComparison, ...]:
    results = []
    for left_system_id, right_system_id in combinations(system_ids, 2):
        pair_observations = tuple(
            item
            for item in observations
            if item.system_id in {left_system_id, right_system_id}
        )
        results.append(
            _build_pairwise_comparison(
                scope=MasterAllocationAnalysisScope.ALL_EVIDENCE,
                regime_label=None,
                regime_source_ref=None,
                left_system_id=left_system_id,
                right_system_id=right_system_id,
                observations=pair_observations,
            )
        )
        for regime_label, regime_source_ref in regime_keys:
            regime_observations = tuple(
                item
                for item in pair_observations
                if item.regime_label == regime_label
                and item.regime_source_ref == regime_source_ref
            )
            if regime_observations:
                results.append(
                    _build_pairwise_comparison(
                        scope=MasterAllocationAnalysisScope.REGIME,
                        regime_label=regime_label,
                        regime_source_ref=regime_source_ref,
                        left_system_id=left_system_id,
                        right_system_id=right_system_id,
                        observations=regime_observations,
                    )
                )
    return tuple(
        sorted(
            results,
            key=lambda item: (
                item.scope.value,
                item.regime_label or "",
                item.regime_source_ref or "",
                item.left_system_id,
                item.right_system_id,
            ),
        )
    )


def _reason_codes(
    evidence: tuple[MasterAllocationAdvisoryEvidence, ...],
) -> tuple[str, ...]:
    reasons = []
    if len(evidence) == 1:
        reasons.append("SINGLE_EVIDENCE_ONLY")
    if any(item.regime_label is None for item in evidence):
        reasons.append("UNLABELED_EVIDENCE_PRESENT")
    historical_policies = {
        item.audit_report.allocation_policy_fingerprint_sha256 for item in evidence
    }
    if len(historical_policies) > 1:
        reasons.append("MULTIPLE_HISTORICAL_ALLOCATION_POLICIES")
    if any(
        item.evaluation.ai_cost_eur.status.value != "AVAILABLE"
        or item.evaluation.economic_net.status.value != "AVAILABLE"
        for item in evidence
    ):
        reasons.append("AI_ECONOMICS_NOT_FULLY_AVAILABLE")
    return tuple(sorted(reasons))


def build_master_allocation_evidence_analysis(
    *,
    current_allocation_policy: MasterAllocationPolicy,
    evidence: tuple[MasterAllocationAdvisoryEvidence, ...],
) -> MasterAllocationEvidenceAnalysisReport:
    ordered_evidence = _validate_and_order_evidence(
        current_allocation_policy=current_allocation_policy,
        evidence=evidence,
    )
    observations = _build_observations(ordered_evidence)
    regime_keys = _regime_keys(ordered_evidence)
    system_ids = tuple(member.system_id for member in current_allocation_policy.members)
    crew_analyses = _crew_analyses(
        system_ids=system_ids,
        observations=observations,
        regime_keys=regime_keys,
    )
    pairwise_comparisons = _pairwise_comparisons(
        system_ids=system_ids,
        observations=observations,
        regime_keys=regime_keys,
    )
    evidence_fingerprints = tuple(item.fingerprint_sha256 for item in ordered_evidence)
    historical_policy_fingerprints = tuple(
        sorted(
            {
                item.audit_report.allocation_policy_fingerprint_sha256
                for item in ordered_evidence
            }
        )
    )
    evidence_through = max(item.sealed_at for item in ordered_evidence)
    unlabeled_count = sum(item.regime_label is None for item in ordered_evidence)
    reason_codes = _reason_codes(ordered_evidence)
    master_portfolio_id = current_allocation_policy.master_portfolio_id
    analysis_id = "master-allocation-evidence-analysis:" + stable_digest(
        {
            "schema": "money-heist.master-allocation-evidence-analysis-id.v1",
            "master_portfolio_id": master_portfolio_id,
            "current_policy_fingerprint_sha256": (
                current_allocation_policy.fingerprint_sha256
            ),
            "evidence_fingerprints_sha256": evidence_fingerprints,
        }
    )
    provisional = MasterAllocationEvidenceAnalysisReport.__new__(
        MasterAllocationEvidenceAnalysisReport
    )
    values = {
        "analysis_id": analysis_id,
        "status": MasterAllocationEvidenceAnalysisStatus.ANALYZED,
        "master_portfolio_id": master_portfolio_id,
        "current_policy_fingerprint_sha256": current_allocation_policy.fingerprint_sha256,
        "evidence_through": evidence_through,
        "evidence_fingerprints_sha256": evidence_fingerprints,
        "historical_allocation_policy_fingerprints_sha256": historical_policy_fingerprints,
        "regime_keys": regime_keys,
        "unlabeled_evidence_count": unlabeled_count,
        "reason_codes": reason_codes,
        "observations": observations,
        "crew_analyses": crew_analyses,
        "pairwise_comparisons": pairwise_comparisons,
        "schema_version": "1.0",
    }
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    fingerprint = stable_digest(master_allocation_evidence_analysis_payload(provisional))
    return MasterAllocationEvidenceAnalysisReport(
        **{name: value for name, value in values.items() if name != "schema_version"},
        fingerprint_sha256=fingerprint,
    )


__all__ = [
    "MasterAllocationAnalysisMetric",
    "MasterAllocationAnalysisMetricStatus",
    "MasterAllocationAnalysisScope",
    "MasterAllocationCrewAnalysis",
    "MasterAllocationCrewEvidenceObservation",
    "MasterAllocationEvidenceAnalysisReport",
    "MasterAllocationEvidenceAnalysisStatus",
    "MasterAllocationPairwiseComparison",
    "build_master_allocation_evidence_analysis",
    "master_allocation_crew_analysis_payload",
    "master_allocation_crew_observation_payload",
    "master_allocation_evidence_analysis_payload",
    "master_allocation_pairwise_comparison_payload",
]
