from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.portfolio.allocation_advisory import MasterAllocationAdvisoryAction
from app.portfolio.allocation_advisory_review_closure import (
    MasterProfessorAdvisoryAuditStatus,
    MasterProfessorAdvisoryClosureStatus,
    MasterProfessorOperatorReviewAction,
    MasterProfessorOperatorReviewStatus,
    audit_master_professor_advisory_review,
    build_master_professor_operator_review_decision,
    seal_master_professor_advisory_review,
)
from app.portfolio.allocation_master_professor_shadow import (
    run_master_professor_shadow_advisory,
)
from tests.portfolio.test_master_professor_shadow_gateway import (
    USAGE_TIME,
    _candidate,
    _context,
    _Gateway,
    _output,
)

REVIEW_TIME = datetime(2026, 2, 1, 13, 0, tzinfo=UTC)


def _shadow_bundle(
    *,
    recommendation_action: MasterAllocationAdvisoryAction = (
        MasterAllocationAdvisoryAction.KEEP_CURRENT
    ),
):
    policy, evidence, analysis, candidates, config = _context()
    selected_candidate_id = None
    if recommendation_action is MasterAllocationAdvisoryAction.PROPOSE_CHANGE:
        selected_candidate_id = candidates[0].candidate_id
    output = _output(
        analysis,
        policy,
        action=recommendation_action,
        selected_candidate_id=selected_candidate_id,
    )
    gateway = _Gateway(output)
    shadow_result = asyncio.run(
        run_master_professor_shadow_advisory(
            gateway=gateway,
            current_allocation_policy=policy,
            evidence=evidence,
            analysis=analysis,
            candidates=candidates,
            config=config,
        )
    )
    return policy, analysis, shadow_result


def _decision(
    analysis,
    shadow_result,
    *,
    action: MasterProfessorOperatorReviewAction = MasterProfessorOperatorReviewAction.ACCEPT,
    operator_ref: str = "operator-review:ticket-21f-4",
    decided_at: datetime = REVIEW_TIME,
):
    return build_master_professor_operator_review_decision(
        analysis=analysis,
        shadow_result=shadow_result,
        action=action,
        operator_ref=operator_ref,
        rationale_codes=("HUMAN_REVIEW_COMPLETED", "SHADOW_EVIDENCE_REVIEWED"),
        decided_at=decided_at,
    )


def test_accept_review_records_human_acceptance_without_application() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(analysis, shadow_result)

    assert decision.action is MasterProfessorOperatorReviewAction.ACCEPT
    assert decision.status is MasterProfessorOperatorReviewStatus.ACCEPTED
    assert decision.human_operator_required is True
    assert decision.operator_decision_recorded is True
    assert decision.advisory_acceptance_only is True
    assert decision.allocation_application_performed is False
    assert decision.allocation_application_authority is False
    assert decision.policy_mutation is False


def test_reject_review_is_a_terminal_record_not_a_policy_action() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(
        analysis,
        shadow_result,
        action=MasterProfessorOperatorReviewAction.REJECT,
    )

    assert decision.status is MasterProfessorOperatorReviewStatus.REJECTED
    assert decision.policy_mutation is False
    assert decision.reservation_authority is False
    assert decision.live_authority is False


def test_defer_review_is_explicit_and_non_executing() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(
        analysis,
        shadow_result,
        action=MasterProfessorOperatorReviewAction.DEFER,
    )

    assert decision.status is MasterProfessorOperatorReviewStatus.DEFERRED
    assert decision.auto_execute is False
    assert decision.broker_authority is False


def test_review_binds_exact_step2_and_step3_fingerprints() -> None:
    policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(analysis, shadow_result)

    assert decision.master_portfolio_id == policy.master_portfolio_id
    assert decision.analysis_fingerprint_sha256 == analysis.fingerprint_sha256
    assert decision.shadow_result_fingerprint_sha256 == shadow_result.fingerprint_sha256
    assert decision.advisory_report_fingerprint_sha256 == (
        shadow_result.advisory_report.fingerprint_sha256
    )
    assert decision.recommendation_fingerprint_sha256 == (
        shadow_result.recommendation_fingerprint_sha256
    )
    assert decision.current_policy_fingerprint_sha256 == policy.fingerprint_sha256


def test_review_is_deterministic_for_same_operator_input() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    first = _decision(analysis, shadow_result)
    second = _decision(analysis, shadow_result)

    assert first == second
    assert first.decision_id == second.decision_id
    assert first.fingerprint_sha256 == second.fingerprint_sha256


def test_review_rationale_codes_are_canonicalized() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = build_master_professor_operator_review_decision(
        analysis=analysis,
        shadow_result=shadow_result,
        action=MasterProfessorOperatorReviewAction.ACCEPT,
        operator_ref="operator-review:test",
        rationale_codes=("Z_REASON", "A_REASON"),
        decided_at=REVIEW_TIME,
    )

    assert decision.rationale_codes == ("A_REASON", "Z_REASON")


def test_review_rejects_blank_operator_reference() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()

    with pytest.raises(ValueError, match="operator_ref"):
        _decision(analysis, shadow_result, operator_ref="  ")


def test_review_rejects_timestamp_before_gateway_usage() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()

    with pytest.raises(ValueError, match="predate"):
        _decision(
            analysis,
            shadow_result,
            decided_at=USAGE_TIME - timedelta(seconds=1),
        )


def test_review_rejects_tampered_shadow_result() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    object.__setattr__(shadow_result, "gateway_model_id", "tampered-model")

    with pytest.raises(ValueError, match="SHADOW result fingerprint integrity"):
        _decision(analysis, shadow_result)


def test_review_rejects_wrong_analysis_binding() -> None:
    policy, _analysis, shadow_result = _shadow_bundle()
    evidence = _context()[1]
    from app.portfolio.allocation_evidence_analysis import (
        build_master_allocation_evidence_analysis,
    )

    other_analysis = build_master_allocation_evidence_analysis(
        current_allocation_policy=policy,
        evidence=evidence,
    )
    object.__setattr__(other_analysis, "analysis_id", "other-analysis")

    with pytest.raises(ValueError, match="analysis fingerprint integrity"):
        _decision(other_analysis, shadow_result)


def test_propose_change_review_preserves_selected_operator_candidate() -> None:
    _policy, analysis, shadow_result = _shadow_bundle(
        recommendation_action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE
    )
    decision = _decision(analysis, shadow_result)

    assert decision.recommendation_action is MasterAllocationAdvisoryAction.PROPOSE_CHANGE
    assert decision.selected_candidate_id == _candidate().candidate_id
    assert decision.allocation_application_performed is False


def test_keep_current_review_has_no_candidate_identity() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(analysis, shadow_result)

    assert decision.recommendation_action is MasterAllocationAdvisoryAction.KEEP_CURRENT
    assert decision.selected_candidate_id is None


def test_audit_verifies_complete_step1_to_operator_chain() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(analysis, shadow_result)
    audit = audit_master_professor_advisory_review(
        analysis=analysis,
        shadow_result=shadow_result,
        operator_decision=decision,
    )

    assert audit.status is MasterProfessorAdvisoryAuditStatus.VERIFIED
    assert audit.step1_evidence_chain_verified is True
    assert audit.step2_analysis_verified is True
    assert audit.step3_shadow_gateway_verified is True
    assert audit.operator_review_verified is True
    assert audit.no_policy_application_verified is True
    assert audit.no_trading_authority_verified is True


def test_audit_binds_operator_decision_and_review_time() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(analysis, shadow_result)
    audit = audit_master_professor_advisory_review(
        analysis=analysis,
        shadow_result=shadow_result,
        operator_decision=decision,
    )

    assert audit.operator_decision_fingerprint_sha256 == decision.fingerprint_sha256
    assert audit.operator_review_action is decision.action
    assert audit.operator_review_status is decision.status
    assert audit.reviewed_at == decision.decided_at


def test_audit_rejects_tampered_operator_decision() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(analysis, shadow_result)
    object.__setattr__(decision, "operator_ref", "tampered-review")

    with pytest.raises(ValueError, match="operator decision fingerprint integrity"):
        audit_master_professor_advisory_review(
            analysis=analysis,
            shadow_result=shadow_result,
            operator_decision=decision,
        )


def test_audit_rejects_decision_from_other_shadow_result() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(analysis, shadow_result)
    object.__setattr__(decision, "shadow_result_fingerprint_sha256", "a" * 64)
    object.__setattr__(
        decision,
        "fingerprint_sha256",
        decision.fingerprint_sha256,
    )

    with pytest.raises(ValueError, match="operator decision fingerprint integrity"):
        audit_master_professor_advisory_review(
            analysis=analysis,
            shadow_result=shadow_result,
            operator_decision=decision,
        )


def test_audit_has_no_policy_or_trading_authority() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(analysis, shadow_result)
    audit = audit_master_professor_advisory_review(
        analysis=analysis,
        shadow_result=shadow_result,
        operator_decision=decision,
    )

    assert audit.audit_only is True
    assert audit.policy_mutation is False
    assert audit.allocation_application_authority is False
    assert audit.reservation_authority is False
    assert audit.risk_authority is False
    assert audit.admission_authority is False
    assert audit.local_risk_override is False
    assert audit.resize_authority is False
    assert audit.registry_mutation is False
    assert audit.broker_authority is False
    assert audit.live_authority is False
    assert audit.auto_execute is False


def test_closure_seals_verified_operator_review() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(analysis, shadow_result)
    audit = audit_master_professor_advisory_review(
        analysis=analysis,
        shadow_result=shadow_result,
        operator_decision=decision,
    )
    seal = seal_master_professor_advisory_review(
        audit=audit,
        operator_decision=decision,
    )

    assert seal.status is MasterProfessorAdvisoryClosureStatus.SEALED
    assert seal.audit_fingerprint_sha256 == audit.fingerprint_sha256
    assert seal.operator_decision_fingerprint_sha256 == decision.fingerprint_sha256
    assert seal.sealed_at == decision.decided_at


def test_closure_is_deterministic_and_has_no_wall_clock() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(analysis, shadow_result)
    audit = audit_master_professor_advisory_review(
        analysis=analysis,
        shadow_result=shadow_result,
        operator_decision=decision,
    )

    first = seal_master_professor_advisory_review(
        audit=audit,
        operator_decision=decision,
    )
    second = seal_master_professor_advisory_review(
        audit=audit,
        operator_decision=decision,
    )

    assert first == second
    assert first.closure_id == second.closure_id
    assert first.closure_fingerprint_sha256 == second.closure_fingerprint_sha256


def test_closure_rejects_tampered_audit() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(analysis, shadow_result)
    audit = audit_master_professor_advisory_review(
        analysis=analysis,
        shadow_result=shadow_result,
        operator_decision=decision,
    )
    object.__setattr__(audit, "analysis_id", "tampered-analysis")

    with pytest.raises(ValueError, match="audit fingerprint integrity"):
        seal_master_professor_advisory_review(
            audit=audit,
            operator_decision=decision,
        )


def test_closure_rejects_mismatched_decision() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    accepted = _decision(analysis, shadow_result)
    rejected = _decision(
        analysis,
        shadow_result,
        action=MasterProfessorOperatorReviewAction.REJECT,
    )
    audit = audit_master_professor_advisory_review(
        analysis=analysis,
        shadow_result=shadow_result,
        operator_decision=accepted,
    )

    with pytest.raises(ValueError, match="provenance mismatch"):
        seal_master_professor_advisory_review(
            audit=audit,
            operator_decision=rejected,
        )


def test_closure_exposes_no_policy_application_or_execution_authority() -> None:
    _policy, analysis, shadow_result = _shadow_bundle(
        recommendation_action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE
    )
    decision = _decision(analysis, shadow_result)
    audit = audit_master_professor_advisory_review(
        analysis=analysis,
        shadow_result=shadow_result,
        operator_decision=decision,
    )
    seal = seal_master_professor_advisory_review(
        audit=audit,
        operator_decision=decision,
    )

    assert seal.operator_review_completed is True
    assert seal.allocation_application_performed is False
    assert seal.allocation_application_authority is False
    assert seal.policy_mutation is False
    assert seal.reservation_authority is False
    assert seal.risk_authority is False
    assert seal.admission_authority is False
    assert seal.broker_authority is False
    assert seal.live_authority is False
    assert seal.auto_execute is False


def test_accepting_propose_change_does_not_mutate_current_policy() -> None:
    policy, analysis, shadow_result = _shadow_bundle(
        recommendation_action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE
    )
    before = policy.fingerprint_sha256
    decision = _decision(analysis, shadow_result)
    audit = audit_master_professor_advisory_review(
        analysis=analysis,
        shadow_result=shadow_result,
        operator_decision=decision,
    )
    seal_master_professor_advisory_review(audit=audit, operator_decision=decision)

    assert policy.fingerprint_sha256 == before
    assert shadow_result.advisory_report.current_allocation_policy is policy


def test_reject_and_defer_can_also_be_sealed_for_audit_history() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    for action in (
        MasterProfessorOperatorReviewAction.REJECT,
        MasterProfessorOperatorReviewAction.DEFER,
    ):
        decision = _decision(analysis, shadow_result, action=action)
        audit = audit_master_professor_advisory_review(
            analysis=analysis,
            shadow_result=shadow_result,
            operator_decision=decision,
        )
        seal = seal_master_professor_advisory_review(
            audit=audit,
            operator_decision=decision,
        )
        assert seal.operator_review_action is action
        assert seal.operator_review_status is decision.status


def test_direct_status_mismatch_fails_closed() -> None:
    _policy, analysis, shadow_result = _shadow_bundle()
    decision = _decision(analysis, shadow_result)

    with pytest.raises(ValueError, match="status does not match action"):
        replace(decision, status=MasterProfessorOperatorReviewStatus.REJECTED)


def test_closure_contains_fingerprints_not_a_replacement_policy() -> None:
    _policy, analysis, shadow_result = _shadow_bundle(
        recommendation_action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE
    )
    decision = _decision(analysis, shadow_result)
    audit = audit_master_professor_advisory_review(
        analysis=analysis,
        shadow_result=shadow_result,
        operator_decision=decision,
    )
    seal = seal_master_professor_advisory_review(
        audit=audit,
        operator_decision=decision,
    )

    assert not hasattr(seal, "allocation_policy")
    assert not hasattr(seal, "proposed_policy")
    assert seal.current_policy_fingerprint_sha256 == (
        shadow_result.current_policy_fingerprint_sha256
    )
