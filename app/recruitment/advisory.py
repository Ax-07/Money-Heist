from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .evidence_gate import RecruitmentEvidencePurpose
from .evidence_package import RecruitmentCandidateEvidencePackage
from .lifecycle import RecruitmentLifecycleRecord
from .models import (
    RecruitmentCandidateState,
    RecruitmentMetricDirection,
    RecruitmentSuccessCriterion,
)


class RecruitmentCriterionEvaluationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"


class RecruitmentAdvisoryAction(StrEnum):
    REJECT = "REJECT"
    EXTEND = "EXTEND"
    PROBATION = "PROBATION"
    RECOMMEND_PROMOTION = "RECOMMEND_PROMOTION"


RECRUITMENT_ADVISORY_METRIC_KEYS: tuple[str, ...] = (
    "average_confidence",
    "average_cost_eur",
    "average_latency_ms",
    "call_count",
    "candidate_budget_utilization_ratio",
    "candidate_direct_ai_cost_eur",
    "candidate_direct_cost_share_ratio",
    "directional_agreement",
    "drawdown_increase_pct",
    "drawdown_reduction_pct",
    "marginal_economic_net_eur",
    "marginal_total_ai_cost_eur",
    "marginal_trading_net_eur",
    "oos_ablation_comparison_count",
    "participation_frequency",
)


@dataclass(frozen=True, slots=True)
class RecruitmentCriterionEvaluation:
    criterion: RecruitmentSuccessCriterion
    observed_value: Decimal | None
    status: RecruitmentCriterionEvaluationStatus
    reason_code: str

    def __post_init__(self) -> None:
        if not self.reason_code.strip():
            raise ValueError("criterion evaluation reason_code must not be blank")
        if self.status in {
            RecruitmentCriterionEvaluationStatus.PASS,
            RecruitmentCriterionEvaluationStatus.FAIL,
        }:
            if self.observed_value is None:
                raise ValueError("PASS/FAIL criterion evaluation requires observed_value")
        elif self.observed_value is not None:
            raise ValueError("UNAVAILABLE/UNSUPPORTED criterion evaluation cannot carry a value")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "criterion": self.criterion.model_dump(mode="json"),
            "observed_value": self.observed_value,
            "status": self.status,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class RecruitmentAdvisoryReport:
    recruitment_id: str
    candidate_agent_id: str
    lifecycle_revision: int
    current_state: RecruitmentCandidateState
    evidence_package_fingerprint_sha256: str
    criteria: tuple[RecruitmentCriterionEvaluation, ...]
    action: RecruitmentAdvisoryAction
    evidence_sufficient: bool
    criteria_all_passed: bool
    reason_codes: tuple[str, ...]
    audit_fingerprint_sha256: str
    policy_version: str = "batch19.recruitment-advisory.v1"
    criteria_evaluation_performed: bool = True
    recommendation_generated: bool = True
    auto_apply: bool = False
    registry_mutation: bool = False
    lifecycle_transition_applied: bool = False
    promotion_applied: bool = False
    live_authority: bool = False

    def __post_init__(self) -> None:
        if not self.recruitment_id.strip():
            raise ValueError("recruitment_id must not be blank")
        if not self.candidate_agent_id.strip():
            raise ValueError("candidate_agent_id must not be blank")
        if self.lifecycle_revision < 0:
            raise ValueError("lifecycle_revision must be >= 0")
        _require_sha256(
            self.evidence_package_fingerprint_sha256,
            field_name="evidence_package_fingerprint_sha256",
        )
        _require_sha256(self.audit_fingerprint_sha256, field_name="audit_fingerprint_sha256")
        if not self.criteria:
            raise ValueError("recruitment advisory requires criterion evaluations")
        if not self.reason_codes:
            raise ValueError("recruitment advisory requires reason_codes")
        normalized = tuple(sorted(code.strip() for code in self.reason_codes))
        if any(not code for code in normalized):
            raise ValueError("reason_codes must not contain blanks")
        if len(set(normalized)) != len(normalized):
            raise ValueError("reason_codes must not contain duplicates")
        object.__setattr__(self, "reason_codes", normalized)
        if not self.criteria_evaluation_performed or not self.recommendation_generated:
            raise ValueError("Batch 19d advisory must record criteria evaluation and recommendation")
        if (
            self.auto_apply
            or self.registry_mutation
            or self.lifecycle_transition_applied
            or self.promotion_applied
            or self.live_authority
        ):
            raise ValueError("recruitment advisory cannot apply operational changes")
        expected = _advisory_fingerprint(
            recruitment_id=self.recruitment_id,
            candidate_agent_id=self.candidate_agent_id,
            lifecycle_revision=self.lifecycle_revision,
            current_state=self.current_state,
            evidence_package_fingerprint_sha256=self.evidence_package_fingerprint_sha256,
            criteria=self.criteria,
            action=self.action,
            evidence_sufficient=self.evidence_sufficient,
            criteria_all_passed=self.criteria_all_passed,
            reason_codes=self.reason_codes,
        )
        if expected != self.audit_fingerprint_sha256:
            raise ValueError("recruitment advisory fingerprint does not match payload")


def _require_sha256(value: str, *, field_name: str) -> None:
    normalized = value.lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")


def _metric_value(metric: object) -> tuple[Decimal | None, str | None]:
    status = getattr(metric, "status", None)
    status_value = getattr(status, "value", status)
    value = getattr(metric, "value", None)
    if status_value != "AVAILABLE" or value is None:
        return None, str(getattr(metric, "reason", None) or "METRIC_UNAVAILABLE")
    result = Decimal(str(value))
    if not result.is_finite():
        return None, "METRIC_NON_FINITE"
    return result, None


def _resolve_metric(
    package: RecruitmentCandidateEvidencePackage,
    metric_key: str,
) -> tuple[Decimal | None, str | None, bool]:
    reputation = package.reputation_evidence.reputation
    costs = package.reputation_evidence.costs

    metric_fields = {
        "average_confidence": reputation.average_confidence,
        "average_cost_eur": reputation.average_cost_eur,
        "average_latency_ms": reputation.average_latency_ms,
        "directional_agreement": reputation.directional_agreement,
        "drawdown_reduction_pct": reputation.drawdown_reduction_pct,
        "marginal_economic_net_eur": reputation.marginal_economic_net,
        "marginal_trading_net_eur": reputation.marginal_trading_net,
        "participation_frequency": reputation.participation_frequency,
    }
    if metric_key in metric_fields:
        value, reason = _metric_value(metric_fields[metric_key])
        return value, reason, True

    if metric_key == "drawdown_increase_pct":
        reduction, reason = _metric_value(reputation.drawdown_reduction_pct)
        if reduction is None:
            return None, reason, True
        return -reduction, None, True

    scalar_fields = {
        "call_count": Decimal(reputation.call_count),
        "candidate_budget_utilization_ratio": costs.candidate_budget_utilization_ratio,
        "candidate_direct_ai_cost_eur": costs.candidate_direct_ai_cost_eur,
        "candidate_direct_cost_share_ratio": costs.candidate_direct_cost_share_ratio,
        "marginal_total_ai_cost_eur": costs.marginal_total_ai_cost_eur,
        "oos_ablation_comparison_count": Decimal(reputation.oos_ablation_comparison_count),
    }
    if metric_key in scalar_fields:
        value = Decimal(str(scalar_fields[metric_key]))
        if not value.is_finite():
            return None, "METRIC_NON_FINITE", True
        return value, None, True

    return None, "UNSUPPORTED_METRIC_KEY", False


def _evaluate_criterion(
    package: RecruitmentCandidateEvidencePackage,
    criterion: RecruitmentSuccessCriterion,
    *,
    promotion_grade_oos: bool,
) -> RecruitmentCriterionEvaluation:
    if not promotion_grade_oos:
        return RecruitmentCriterionEvaluation(
            criterion=criterion,
            observed_value=None,
            status=RecruitmentCriterionEvaluationStatus.UNAVAILABLE,
            reason_code="OOS_PROMOTION_EVIDENCE_REQUIRED",
        )

    value, reason, supported = _resolve_metric(package, criterion.metric_key)
    if not supported:
        return RecruitmentCriterionEvaluation(
            criterion=criterion,
            observed_value=None,
            status=RecruitmentCriterionEvaluationStatus.UNSUPPORTED,
            reason_code=reason or "UNSUPPORTED_METRIC_KEY",
        )
    if value is None:
        return RecruitmentCriterionEvaluation(
            criterion=criterion,
            observed_value=None,
            status=RecruitmentCriterionEvaluationStatus.UNAVAILABLE,
            reason_code=reason or "METRIC_UNAVAILABLE",
        )

    if criterion.direction is RecruitmentMetricDirection.AT_LEAST:
        passed = value >= criterion.threshold
    elif criterion.direction is RecruitmentMetricDirection.AT_MOST:
        passed = value <= criterion.threshold
    else:  # defensive: enum currently has exactly two directions
        raise ValueError(f"unsupported recruitment metric direction: {criterion.direction}")

    return RecruitmentCriterionEvaluation(
        criterion=criterion,
        observed_value=value,
        status=(
            RecruitmentCriterionEvaluationStatus.PASS
            if passed
            else RecruitmentCriterionEvaluationStatus.FAIL
        ),
        reason_code="CRITERION_THRESHOLD_MET" if passed else "CRITERION_THRESHOLD_NOT_MET",
    )


def _reason_codes(
    criteria: tuple[RecruitmentCriterionEvaluation, ...],
    *,
    promotion_grade_oos: bool,
    budget_within_limit: bool,
    action: RecruitmentAdvisoryAction,
    current_state: RecruitmentCandidateState,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    if not promotion_grade_oos:
        reasons.add("PROMOTION_GRADE_OOS_EVIDENCE_REQUIRED")
    if promotion_grade_oos and not budget_within_limit:
        reasons.add("CANDIDATE_BUDGET_EXCEEDED")
    for item in criteria:
        if item.status is RecruitmentCriterionEvaluationStatus.FAIL:
            reasons.add(f"CRITERION_FAILED:{item.criterion.metric_key}")
        elif item.status is RecruitmentCriterionEvaluationStatus.UNAVAILABLE:
            reasons.add(f"CRITERION_UNAVAILABLE:{item.criterion.metric_key}")
        elif item.status is RecruitmentCriterionEvaluationStatus.UNSUPPORTED:
            reasons.add(f"CRITERION_UNSUPPORTED:{item.criterion.metric_key}")

    if action is RecruitmentAdvisoryAction.PROBATION:
        reasons.add("ALL_SUCCESS_CRITERIA_PASSED_OOS")
        reasons.add("SHADOW_EVIDENCE_SUPPORTS_PROBATION")
    elif action is RecruitmentAdvisoryAction.RECOMMEND_PROMOTION:
        reasons.add("ALL_SUCCESS_CRITERIA_PASSED_OOS")
        reasons.add("PROBATION_EVIDENCE_SUPPORTS_PROMOTION_RECOMMENDATION")
    elif action is RecruitmentAdvisoryAction.REJECT and not reasons:
        reasons.add("RECRUITMENT_EVIDENCE_REJECTED")
    elif action is RecruitmentAdvisoryAction.EXTEND and current_state is RecruitmentCandidateState.CANDIDATE:
        reasons.add("SHADOW_STAGE_REQUIRED_BEFORE_PROBATION")
    elif action is RecruitmentAdvisoryAction.EXTEND and not reasons:
        reasons.add("MORE_RECRUITMENT_EVIDENCE_REQUIRED")

    return tuple(sorted(reasons))


def _advisory_fingerprint(
    *,
    recruitment_id: str,
    candidate_agent_id: str,
    lifecycle_revision: int,
    current_state: RecruitmentCandidateState,
    evidence_package_fingerprint_sha256: str,
    criteria: tuple[RecruitmentCriterionEvaluation, ...],
    action: RecruitmentAdvisoryAction,
    evidence_sufficient: bool,
    criteria_all_passed: bool,
    reason_codes: tuple[str, ...],
) -> str:
    return stable_digest(
        {
            "schema": "money-heist.recruitment-advisory.v1",
            "recruitment_id": recruitment_id,
            "candidate_agent_id": candidate_agent_id,
            "lifecycle_revision": lifecycle_revision,
            "current_state": current_state,
            "evidence_package_fingerprint_sha256": evidence_package_fingerprint_sha256,
            "criteria": [item.canonical_payload() for item in criteria],
            "action": action,
            "evidence_sufficient": evidence_sufficient,
            "criteria_all_passed": criteria_all_passed,
            "reason_codes": reason_codes,
            "criteria_evaluation_performed": True,
            "recommendation_generated": True,
            "auto_apply": False,
            "registry_mutation": False,
            "lifecycle_transition_applied": False,
            "promotion_applied": False,
            "live_authority": False,
        }
    )


def evaluate_recruitment_advisory(
    package: RecruitmentCandidateEvidencePackage,
    lifecycle: RecruitmentLifecycleRecord,
) -> RecruitmentAdvisoryReport:
    """Evaluate frozen candidate evidence into a non-applying recruitment recommendation.

    Every pre-registered success criterion is required. Unsupported or unavailable
    metrics fail closed to EXTEND rather than being guessed. Promotion-grade criteria
    are never evaluated from DESIGN/VALIDATION evidence. A candidate must progress
    through SHADOW then PROBATION; a successful SHADOW evaluation therefore recommends
    PROBATION, while only successful PROBATION evidence can recommend promotion.
    """

    if lifecycle.recruitment_id != package.recruitment_id:
        raise ValueError("lifecycle record and evidence package target different recruitment ids")
    if lifecycle.current_state in {
        RecruitmentCandidateState.PROPOSED,
        RecruitmentCandidateState.REJECTED,
        RecruitmentCandidateState.PROMOTION_RECOMMENDED,
    }:
        raise ValueError("recruitment advisory requires CANDIDATE, SHADOW, or PROBATION state")

    promotion_grade_oos = (
        package.purpose is RecruitmentEvidencePurpose.PROMOTION
        and package.evidence_gate.is_out_of_sample
    )
    criteria = tuple(
        _evaluate_criterion(
            package,
            criterion,
            promotion_grade_oos=promotion_grade_oos,
        )
        for criterion in package.success_criteria_snapshot
    )
    complete = promotion_grade_oos and all(
        item.status
        in {
            RecruitmentCriterionEvaluationStatus.PASS,
            RecruitmentCriterionEvaluationStatus.FAIL,
        }
        for item in criteria
    )
    all_passed = complete and all(
        item.status is RecruitmentCriterionEvaluationStatus.PASS for item in criteria
    )
    any_failed = complete and any(
        item.status is RecruitmentCriterionEvaluationStatus.FAIL for item in criteria
    )
    budget_within_limit = package.reputation_evidence.costs.candidate_direct_cost_within_budget

    if not promotion_grade_oos or not complete:
        action = RecruitmentAdvisoryAction.EXTEND
    elif not budget_within_limit or any_failed:
        action = RecruitmentAdvisoryAction.REJECT
    elif lifecycle.current_state is RecruitmentCandidateState.CANDIDATE:
        action = RecruitmentAdvisoryAction.EXTEND
    elif lifecycle.current_state is RecruitmentCandidateState.SHADOW:
        action = RecruitmentAdvisoryAction.PROBATION
    elif lifecycle.current_state is RecruitmentCandidateState.PROBATION:
        action = RecruitmentAdvisoryAction.RECOMMEND_PROMOTION
    else:  # guarded above; keeps state handling explicit if enum grows later
        raise ValueError(f"unsupported recruitment advisory state: {lifecycle.current_state}")

    reasons = _reason_codes(
        criteria,
        promotion_grade_oos=promotion_grade_oos,
        budget_within_limit=budget_within_limit,
        action=action,
        current_state=lifecycle.current_state,
    )
    fingerprint = _advisory_fingerprint(
        recruitment_id=package.recruitment_id,
        candidate_agent_id=package.candidate_agent_id,
        lifecycle_revision=lifecycle.revision,
        current_state=lifecycle.current_state,
        evidence_package_fingerprint_sha256=package.audit_fingerprint_sha256,
        criteria=criteria,
        action=action,
        evidence_sufficient=complete,
        criteria_all_passed=all_passed,
        reason_codes=reasons,
    )
    return RecruitmentAdvisoryReport(
        recruitment_id=package.recruitment_id,
        candidate_agent_id=package.candidate_agent_id,
        lifecycle_revision=lifecycle.revision,
        current_state=lifecycle.current_state,
        evidence_package_fingerprint_sha256=package.audit_fingerprint_sha256,
        criteria=criteria,
        action=action,
        evidence_sufficient=complete,
        criteria_all_passed=all_passed,
        reason_codes=reasons,
        audit_fingerprint_sha256=fingerprint,
    )


__all__ = [
    "RECRUITMENT_ADVISORY_METRIC_KEYS",
    "RecruitmentAdvisoryAction",
    "RecruitmentAdvisoryReport",
    "RecruitmentCriterionEvaluation",
    "RecruitmentCriterionEvaluationStatus",
    "evaluate_recruitment_advisory",
]
