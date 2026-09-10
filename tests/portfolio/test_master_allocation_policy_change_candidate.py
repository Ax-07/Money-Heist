from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.portfolio.allocation_advisory import MasterAllocationAdvisoryAction
from app.portfolio.allocation_advisory_review_closure import (
    MasterProfessorOperatorReviewAction,
    audit_master_professor_advisory_review,
    build_master_professor_operator_review_decision,
    seal_master_professor_advisory_review,
)
from app.portfolio.allocation_master_professor_shadow import (
    build_master_professor_allocation_candidate,
    master_professor_shadow_result_payload,
    run_master_professor_shadow_advisory,
)
from app.portfolio.allocation_policy_change import (
    MasterAllocationPolicyChangeCandidate,
    MasterAllocationPolicyChangeCandidateSource,
    MasterAllocationPolicyChangeCandidateStatus,
    build_master_allocation_policy_change_candidate,
)
from app.services.backtest.ids import stable_digest
from tests.portfolio.test_master_professor_shadow_gateway import (
    _candidate,
    _context,
    _Gateway,
    _output,
)

REVIEW_TIME = datetime(2026, 2, 1, 13, 0, tzinfo=UTC)


def _bundle(
    *,
    recommendation_action: MasterAllocationAdvisoryAction = (
        MasterAllocationAdvisoryAction.PROPOSE_CHANGE
    ),
    operator_action: MasterProfessorOperatorReviewAction = (
        MasterProfessorOperatorReviewAction.ACCEPT
    ),
):
    policy, evidence, analysis, candidates, config = _context()
    selected = candidates[0]
    selected_id = (
        selected.candidate_id
        if recommendation_action is MasterAllocationAdvisoryAction.PROPOSE_CHANGE
        else None
    )
    output = _output(
        analysis,
        policy,
        action=recommendation_action,
        selected_candidate_id=selected_id,
    )
    shadow_result = asyncio.run(
        run_master_professor_shadow_advisory(
            gateway=_Gateway(output),
            current_allocation_policy=policy,
            evidence=evidence,
            analysis=analysis,
            candidates=candidates,
            config=config,
        )
    )
    decision = build_master_professor_operator_review_decision(
        analysis=analysis,
        shadow_result=shadow_result,
        action=operator_action,
        operator_ref="operator-review:batch21g-step1",
        rationale_codes=("HUMAN_REVIEW_COMPLETED",),
        decided_at=REVIEW_TIME,
    )
    audit = audit_master_professor_advisory_review(
        analysis=analysis,
        shadow_result=shadow_result,
        operator_decision=decision,
    )
    closure = seal_master_professor_advisory_review(
        audit=audit,
        operator_decision=decision,
    )
    return policy, selected, shadow_result, decision, audit, closure


def _build(bundle=None):
    if bundle is None:
        bundle = _bundle()
    policy, selected, shadow_result, decision, audit, closure = bundle
    return build_master_allocation_policy_change_candidate(
        current_allocation_policy=policy,
        selected_operator_candidate=selected,
        shadow_result=shadow_result,
        operator_decision=decision,
        advisory_audit=audit,
        advisory_closure=closure,
    )


def test_builds_candidate_from_accepted_sealed_change_advisory() -> None:
    candidate = _build()

    assert candidate.status is (
        MasterAllocationPolicyChangeCandidateStatus.READY_FOR_OPERATOR_AUTHORIZATION
    )
    assert candidate.source is (
        MasterAllocationPolicyChangeCandidateSource.ACCEPTED_SEALED_MASTER_PROFESSOR_ADVISORY
    )
    assert candidate.candidate_only is True


def test_candidate_preserves_exact_operator_scenario_envelopes() -> None:
    policy, selected, *_rest = _bundle()
    candidate = _build((policy, selected, *_rest))

    assert candidate.proposed_envelopes == selected.proposed_envelopes
    assert candidate.selected_operator_candidate_id == selected.candidate_id
    assert candidate.selected_operator_candidate_fingerprint_sha256 == selected.fingerprint_sha256
    assert candidate.selected_operator_candidate_source_ref == selected.source_ref


def test_candidate_binds_exact_base_policy() -> None:
    policy, *_rest = _bundle()
    candidate = _build((policy, *_rest))

    assert candidate.master_portfolio_id == policy.master_portfolio_id
    assert candidate.base_policy_id == policy.policy_id
    assert candidate.base_policy_fingerprint_sha256 == policy.fingerprint_sha256


def test_candidate_binds_complete_review_chain() -> None:
    policy, selected, shadow_result, decision, audit, closure = _bundle()
    candidate = _build((policy, selected, shadow_result, decision, audit, closure))

    assert candidate.shadow_result_fingerprint_sha256 == shadow_result.fingerprint_sha256
    assert candidate.recommendation_fingerprint_sha256 == (
        shadow_result.recommendation_fingerprint_sha256
    )
    assert candidate.operator_decision_fingerprint_sha256 == decision.fingerprint_sha256
    assert candidate.advisory_audit_fingerprint_sha256 == audit.fingerprint_sha256
    assert candidate.advisory_closure_fingerprint_sha256 == closure.closure_fingerprint_sha256
    assert candidate.reviewed_at == closure.sealed_at


def test_candidate_has_no_application_or_trading_authority() -> None:
    candidate = _build()

    assert candidate.explicit_policy_application_authorization_required is True
    assert candidate.policy_application_performed is False
    assert candidate.policy_application_authority is False
    assert candidate.auto_apply is False
    assert candidate.dynamic_allocation_enabled is False
    assert candidate.reservation_authority is False
    assert candidate.risk_authority is False
    assert candidate.admission_authority is False
    assert candidate.local_risk_override is False
    assert candidate.resize_authority is False
    assert candidate.registry_mutation is False
    assert candidate.broker_authority is False
    assert candidate.live_authority is False
    assert candidate.auto_execute is False


def test_candidate_is_deterministic() -> None:
    bundle = _bundle()

    first = _build(bundle)
    second = _build(bundle)

    assert first == second
    assert first.change_candidate_id == second.change_candidate_id
    assert first.fingerprint_sha256 == second.fingerprint_sha256


def test_candidate_source_is_operator_review_reference() -> None:
    candidate = _build()

    assert candidate.operator_ref == "operator-review:batch21g-step1"


def test_rejects_keep_current_advisory() -> None:
    bundle = _bundle(recommendation_action=MasterAllocationAdvisoryAction.KEEP_CURRENT)

    with pytest.raises(ValueError, match="PROPOSE_CHANGE"):
        _build(bundle)


def test_rejects_abstain_advisory() -> None:
    bundle = _bundle(recommendation_action=MasterAllocationAdvisoryAction.ABSTAIN)

    with pytest.raises(ValueError, match="PROPOSE_CHANGE"):
        _build(bundle)


def test_rejects_operator_reject() -> None:
    bundle = _bundle(operator_action=MasterProfessorOperatorReviewAction.REJECT)

    with pytest.raises(ValueError, match="operator ACCEPT"):
        _build(bundle)


def test_rejects_operator_defer() -> None:
    bundle = _bundle(operator_action=MasterProfessorOperatorReviewAction.DEFER)

    with pytest.raises(ValueError, match="operator ACCEPT"):
        _build(bundle)


def test_rejects_tampered_base_policy() -> None:
    bundle = list(_bundle())
    object.__setattr__(bundle[0], "policy_id", "tampered-policy")

    with pytest.raises(ValueError, match="base policy fingerprint integrity"):
        _build(tuple(bundle))


def test_rejects_tampered_selected_operator_candidate() -> None:
    bundle = list(_bundle())
    object.__setattr__(bundle[1], "source_ref", "tampered-source")

    with pytest.raises(ValueError, match="candidate fingerprint integrity"):
        _build(tuple(bundle))


def test_rejects_selected_candidate_identity_mismatch() -> None:
    policy, selected, shadow_result, decision, audit, closure = _bundle()
    other = _candidate(candidate_id="other-candidate", crew_a_capital="60", crew_b_capital="40")

    with pytest.raises(ValueError, match="identity mismatch"):
        _build((policy, other, shadow_result, decision, audit, closure))


def test_rejects_candidate_outside_step3_candidate_set() -> None:
    bundle = list(_bundle())
    selected = bundle[1]
    object.__setattr__(bundle[2], "candidate_fingerprints_sha256", ("f" * 64,))
    object.__setattr__(
        bundle[2],
        "fingerprint_sha256",
        stable_digest(master_professor_shadow_result_payload(bundle[2])),
    )
    object.__setattr__(bundle[3], "shadow_result_fingerprint_sha256", bundle[2].fingerprint_sha256)
    object.__setattr__(bundle[4], "shadow_result_fingerprint_sha256", bundle[2].fingerprint_sha256)
    object.__setattr__(bundle[5], "shadow_result_fingerprint_sha256", bundle[2].fingerprint_sha256)

    with pytest.raises(ValueError):
        _build(tuple(bundle))
    assert selected.fingerprint_sha256 not in bundle[2].candidate_fingerprints_sha256


def test_rejects_candidate_envelopes_mismatch_recommendation() -> None:
    policy, _selected, shadow_result, decision, audit, closure = _bundle()
    other = build_master_professor_allocation_candidate(
        candidate_id=shadow_result.output.selected_candidate_id,
        proposed_envelopes=_candidate(
            candidate_id="other-values",
            crew_a_capital="60",
            crew_b_capital="40",
        ).proposed_envelopes,
        source_ref="operator-scenario:other-values",
    )

    with pytest.raises(ValueError):
        _build((policy, other, shadow_result, decision, audit, closure))


def test_rejects_tampered_shadow_result() -> None:
    bundle = list(_bundle())
    object.__setattr__(bundle[2], "gateway_model_id", "tampered-model")

    with pytest.raises(ValueError, match="SHADOW result fingerprint integrity"):
        _build(tuple(bundle))


def test_rejects_tampered_nested_recommendation() -> None:
    bundle = list(_bundle())
    recommendation = bundle[2].advisory_report.recommendation
    object.__setattr__(recommendation, "rationale_codes", ("TAMPERED",))

    with pytest.raises(ValueError, match="recommendation fingerprint integrity"):
        _build(tuple(bundle))


def test_rejects_tampered_operator_decision() -> None:
    bundle = list(_bundle())
    object.__setattr__(bundle[3], "operator_ref", "tampered-operator")

    with pytest.raises(ValueError, match="operator decision fingerprint integrity"):
        _build(tuple(bundle))


def test_rejects_non_verified_audit() -> None:
    bundle = list(_bundle())
    object.__setattr__(bundle[4], "status", "BROKEN")

    with pytest.raises(ValueError, match="VERIFIED"):
        _build(tuple(bundle))


def test_rejects_tampered_advisory_audit() -> None:
    bundle = list(_bundle())
    object.__setattr__(bundle[4], "audit_id", "tampered-audit")

    with pytest.raises(ValueError, match="audit fingerprint integrity"):
        _build(tuple(bundle))


def test_rejects_non_sealed_closure() -> None:
    bundle = list(_bundle())
    object.__setattr__(bundle[5], "status", "BROKEN")

    with pytest.raises(ValueError):
        _build(tuple(bundle))


def test_rejects_tampered_advisory_closure() -> None:
    bundle = list(_bundle())
    object.__setattr__(bundle[5], "closure_id", "tampered-closure")

    with pytest.raises(ValueError, match="closure fingerprint integrity"):
        _build(tuple(bundle))


def test_change_candidate_does_not_create_master_allocation_policy() -> None:
    from app.portfolio.allocation import MasterAllocationPolicy

    candidate = _build()

    assert not isinstance(candidate, MasterAllocationPolicy)
    assert not hasattr(candidate, "source_ref")


def test_public_contract_exposes_candidate_builder() -> None:
    import app.portfolio as portfolio

    assert portfolio.MasterAllocationPolicyChangeCandidate is MasterAllocationPolicyChangeCandidate
    assert (
        portfolio.build_master_allocation_policy_change_candidate
        is build_master_allocation_policy_change_candidate
    )
