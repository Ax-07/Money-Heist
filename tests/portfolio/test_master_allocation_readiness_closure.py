from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

import app.portfolio as portfolio
from app.portfolio.allocation_policy_change_closure import (
    MasterAllocationPolicyChangeClosureSeal,
    MasterAllocationPolicyChangeClosureStatus,
    master_allocation_policy_change_closure_payload,
)
from app.portfolio.allocation_policy_replacement import (
    MasterAllocationPolicyReplacementReasonCode,
    MasterAllocationPolicyReplacementStatus,
)
from app.portfolio.allocation_readiness_closure import (
    MasterAllocationBatch21gClosureStatus,
    MasterAllocationDynamicStatus,
    MasterAllocationInfrastructureStatus,
    MasterAllocationMultiCrewLiveReadinessStatus,
    MasterAllocationReadinessEvidenceKind,
    MasterAllocationReadinessEvidenceStatus,
    MasterAllocationReadinessReasonCode,
    assess_master_allocation_live_readiness,
    build_master_allocation_readiness_evidence,
    seal_master_allocation_batch21g,
)
from app.services.backtest.ids import stable_digest

BASE_TIME = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
DIGEST_D = "d" * 64


def _step5_closure(
    *,
    multi_host_safe: bool = False,
    live_ready: bool = False,
) -> MasterAllocationPolicyChangeClosureSeal:
    values = {
        "status": MasterAllocationPolicyChangeClosureStatus.SEALED,
        "master_portfolio_id": "master-main",
        "audit_fingerprint_sha256": DIGEST_A,
        "replacement_receipt_fingerprint_sha256": DIGEST_B,
        "application_status": MasterAllocationPolicyReplacementStatus.APPLIED,
        "application_reason_code": MasterAllocationPolicyReplacementReasonCode.APPLIED,
        "active_policy_id": "allocation-v2",
        "active_policy_fingerprint_sha256": DIGEST_C,
        "store_ref": "sqlite:///operator/master-allocation.db",
        "store_durable": True,
        "store_multi_process_safe": True,
        "store_multi_host_safe": multi_host_safe,
        "store_live_ready": live_ready,
        "sealed_at": BASE_TIME,
    }
    closure_id = "master-allocation-policy-change-closure:test"
    provisional = MasterAllocationPolicyChangeClosureSeal.__new__(
        MasterAllocationPolicyChangeClosureSeal
    )
    object.__setattr__(provisional, "closure_id", closure_id)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterAllocationPolicyChangeClosureSeal(
        closure_id=closure_id,
        **values,
        closure_fingerprint_sha256=stable_digest(
            master_allocation_policy_change_closure_payload(provisional)
        ),
    )


def _available(kind: MasterAllocationReadinessEvidenceKind, digest: str):
    return build_master_allocation_readiness_evidence(
        kind=kind,
        status=MasterAllocationReadinessEvidenceStatus.AVAILABLE,
        source_ref=f"evidence://{kind.value.lower()}",
        artifact_fingerprint_sha256=digest,
    )


def _not_provided(kind: MasterAllocationReadinessEvidenceKind):
    return build_master_allocation_readiness_evidence(
        kind=kind,
        status=MasterAllocationReadinessEvidenceStatus.NOT_PROVIDED,
        reason_code="OPERATOR_EVIDENCE_NOT_PROVIDED",
    )


def _all_available():
    return (
        _available(MasterAllocationReadinessEvidenceKind.HISTORICAL_OOS, DIGEST_A),
        _available(MasterAllocationReadinessEvidenceKind.WALK_FORWARD_OOS, DIGEST_B),
        _available(MasterAllocationReadinessEvidenceKind.PAPER, DIGEST_C),
        _available(MasterAllocationReadinessEvidenceKind.SHADOW, DIGEST_D),
    )


def _all_missing():
    return tuple(_not_provided(kind) for kind in MasterAllocationReadinessEvidenceKind)


def _assessment(*, evidence=None, closure=None):
    return assess_master_allocation_live_readiness(
        policy_change_closure=closure or _step5_closure(),
        evidence=evidence or _all_available(),
        assessed_at=BASE_TIME + timedelta(minutes=5),
    )


def _tamper(value, **changes):
    for name, replacement in changes.items():
        object.__setattr__(value, name, replacement)
    return value


def test_all_available_evidence_still_cannot_make_multi_crew_live_ready() -> None:
    assessment = _assessment()
    assert assessment.multi_crew_live_readiness_status is (
        MasterAllocationMultiCrewLiveReadinessStatus.BLOCKED
    )
    assert MasterAllocationReadinessReasonCode.BATCH15_LIVE_BOUNDARY_SINGLE_SYSTEM_ONLY in (
        assessment.blocker_codes
    )


def test_current_store_scope_is_explicitly_blocking() -> None:
    assessment = _assessment()
    assert MasterAllocationReadinessReasonCode.POLICY_STORE_NOT_MULTI_HOST_SAFE in (
        assessment.blocker_codes
    )
    assert MasterAllocationReadinessReasonCode.POLICY_STORE_NOT_LIVE_READY in (
        assessment.blocker_codes
    )


def test_infrastructure_can_be_complete_while_live_is_blocked() -> None:
    assessment = _assessment()
    assert assessment.infrastructure_status is MasterAllocationInfrastructureStatus.COMPLETE
    assert assessment.multi_crew_live_readiness_status is (
        MasterAllocationMultiCrewLiveReadinessStatus.BLOCKED
    )


def test_dynamic_allocation_remains_disabled() -> None:
    assessment = _assessment()
    assert assessment.dynamic_allocation_status is MasterAllocationDynamicStatus.DISABLED
    assert assessment.no_dynamic_allocation_enabled is True


def test_missing_evidence_adds_explicit_blockers() -> None:
    assessment = _assessment(evidence=_all_missing())
    expected = {
        MasterAllocationReadinessReasonCode.HISTORICAL_OOS_EVIDENCE_NOT_AVAILABLE,
        MasterAllocationReadinessReasonCode.WALK_FORWARD_OOS_EVIDENCE_NOT_AVAILABLE,
        MasterAllocationReadinessReasonCode.PAPER_EVIDENCE_NOT_AVAILABLE,
        MasterAllocationReadinessReasonCode.SHADOW_EVIDENCE_NOT_AVAILABLE,
    }
    assert expected.issubset(set(assessment.blocker_codes))


def test_available_evidence_does_not_add_evidence_blockers() -> None:
    assessment = _assessment()
    evidence_blockers = {
        MasterAllocationReadinessReasonCode.HISTORICAL_OOS_EVIDENCE_NOT_AVAILABLE,
        MasterAllocationReadinessReasonCode.WALK_FORWARD_OOS_EVIDENCE_NOT_AVAILABLE,
        MasterAllocationReadinessReasonCode.PAPER_EVIDENCE_NOT_AVAILABLE,
        MasterAllocationReadinessReasonCode.SHADOW_EVIDENCE_NOT_AVAILABLE,
    }
    assert not evidence_blockers.intersection(assessment.blocker_codes)


def test_blocked_evidence_keeps_its_reason_and_blocks_readiness() -> None:
    blocked = build_master_allocation_readiness_evidence(
        kind=MasterAllocationReadinessEvidenceKind.PAPER,
        status=MasterAllocationReadinessEvidenceStatus.BLOCKED,
        source_ref="evidence://paper",
        artifact_fingerprint_sha256=DIGEST_C,
        reason_code="PAPER_ACCEPTANCE_CRITERIA_NOT_MET",
    )
    evidence = tuple(
        blocked if item.kind is MasterAllocationReadinessEvidenceKind.PAPER else item
        for item in _all_available()
    )
    assessment = _assessment(evidence=evidence)
    assert blocked.reason_code == "PAPER_ACCEPTANCE_CRITERIA_NOT_MET"
    assert MasterAllocationReadinessReasonCode.PAPER_EVIDENCE_NOT_AVAILABLE in (
        assessment.blocker_codes
    )


def test_store_capabilities_are_copied_from_step5_closure() -> None:
    assessment = _assessment()
    assert assessment.store_durable is True
    assert assessment.store_multi_process_safe is True
    assert assessment.store_multi_host_safe is False
    assert assessment.store_live_ready is False


def test_hypothetical_stronger_store_removes_only_store_blockers() -> None:
    assessment = _assessment(closure=_step5_closure(multi_host_safe=True, live_ready=True))
    assert MasterAllocationReadinessReasonCode.POLICY_STORE_NOT_MULTI_HOST_SAFE not in (
        assessment.blocker_codes
    )
    assert MasterAllocationReadinessReasonCode.POLICY_STORE_NOT_LIVE_READY not in (
        assessment.blocker_codes
    )
    assert MasterAllocationReadinessReasonCode.BATCH15_LIVE_BOUNDARY_SINGLE_SYSTEM_ONLY in (
        assessment.blocker_codes
    )


def test_assessment_preserves_separate_live_preflight_and_operator_arm() -> None:
    assessment = _assessment()
    assert assessment.batch15_live_preflight_preserved is True
    assert assessment.operator_arm_still_required is True
    assert assessment.no_live_activation_performed is True


def test_assessment_grants_no_runtime_authority() -> None:
    assessment = _assessment()
    assert assessment.policy_mutation_authority is False
    assert assessment.reservation_authority is False
    assert assessment.risk_authority is False
    assert assessment.admission_authority is False
    assert assessment.local_risk_override is False
    assert assessment.resize_authority is False
    assert assessment.registry_mutation is False
    assert assessment.broker_authority is False
    assert assessment.live_authority is False
    assert assessment.auto_execute is False


def test_assessment_is_deterministic() -> None:
    first = _assessment()
    second = _assessment()
    assert first == second
    assert first.fingerprint_sha256 == second.fingerprint_sha256


def test_evidence_is_canonicalized_by_kind() -> None:
    assessment = _assessment(evidence=tuple(reversed(_all_available())))
    assert tuple(item.kind.value for item in assessment.evidence) == tuple(
        sorted(item.kind.value for item in assessment.evidence)
    )


def test_assessment_cannot_predate_step5_closure() -> None:
    with pytest.raises(ValueError, match="cannot predate Step 5 closure"):
        assess_master_allocation_live_readiness(
            policy_change_closure=_step5_closure(),
            evidence=_all_available(),
            assessed_at=BASE_TIME - timedelta(seconds=1),
        )


def test_incomplete_evidence_inventory_fails_closed() -> None:
    with pytest.raises(ValueError, match="exactly one record per evidence kind"):
        assess_master_allocation_live_readiness(
            policy_change_closure=_step5_closure(),
            evidence=_all_available()[:-1],
            assessed_at=BASE_TIME + timedelta(minutes=1),
        )


def test_duplicate_evidence_kind_fails_closed() -> None:
    evidence = _all_available()
    duplicated = evidence[:-1] + (evidence[0],)
    with pytest.raises(ValueError, match="complete and unique"):
        assess_master_allocation_live_readiness(
            policy_change_closure=_step5_closure(),
            evidence=duplicated,
            assessed_at=BASE_TIME + timedelta(minutes=1),
        )


def test_available_evidence_requires_provenance() -> None:
    with pytest.raises(ValueError, match="requires source and fingerprint"):
        build_master_allocation_readiness_evidence(
            kind=MasterAllocationReadinessEvidenceKind.PAPER,
            status=MasterAllocationReadinessEvidenceStatus.AVAILABLE,
        )


def test_not_provided_evidence_requires_reason() -> None:
    with pytest.raises(ValueError, match="requires reason_code"):
        build_master_allocation_readiness_evidence(
            kind=MasterAllocationReadinessEvidenceKind.PAPER,
            status=MasterAllocationReadinessEvidenceStatus.NOT_PROVIDED,
        )


def test_not_provided_evidence_cannot_fake_artifact_provenance() -> None:
    with pytest.raises(ValueError, match="cannot carry artifact provenance"):
        build_master_allocation_readiness_evidence(
            kind=MasterAllocationReadinessEvidenceKind.PAPER,
            status=MasterAllocationReadinessEvidenceStatus.NOT_PROVIDED,
            source_ref="evidence://paper",
            artifact_fingerprint_sha256=DIGEST_A,
            reason_code="MISSING",
        )


def test_blocked_evidence_requires_reason() -> None:
    with pytest.raises(ValueError, match="requires reason_code"):
        build_master_allocation_readiness_evidence(
            kind=MasterAllocationReadinessEvidenceKind.PAPER,
            status=MasterAllocationReadinessEvidenceStatus.BLOCKED,
            source_ref="evidence://paper",
            artifact_fingerprint_sha256=DIGEST_A,
        )


def test_evidence_fingerprint_tampering_fails_closed() -> None:
    evidence = list(_all_available())
    _tamper(evidence[0], fingerprint_sha256=DIGEST_D)
    with pytest.raises(ValueError, match="evidence fingerprint integrity failure"):
        _assessment(evidence=tuple(evidence))


def test_step5_closure_fingerprint_tampering_fails_closed() -> None:
    closure = _step5_closure()
    _tamper(closure, closure_fingerprint_sha256=DIGEST_D)
    with pytest.raises(ValueError, match="Step 5 closure fingerprint integrity failure"):
        _assessment(closure=closure)


def test_assessment_rejects_false_safety_verification_flag() -> None:
    assessment = _assessment()
    with pytest.raises(ValueError, match="requires every safety verification flag"):
        replace(
            assessment,
            no_live_activation_performed=False,
            fingerprint_sha256=assessment.fingerprint_sha256,
        )


def test_batch21g_closure_is_sealed_and_complete() -> None:
    seal = seal_master_allocation_batch21g(assessment=_assessment())
    assert seal.status is MasterAllocationBatch21gClosureStatus.SEALED
    assert seal.batch_21g_complete is True
    assert seal.infrastructure_status is MasterAllocationInfrastructureStatus.COMPLETE


def test_batch21g_closure_preserves_blocked_live_and_disabled_dynamic() -> None:
    seal = seal_master_allocation_batch21g(assessment=_assessment())
    assert seal.dynamic_allocation_status is MasterAllocationDynamicStatus.DISABLED
    assert seal.dynamic_allocation_enabled is False
    assert seal.multi_crew_live_readiness_status is (
        MasterAllocationMultiCrewLiveReadinessStatus.BLOCKED
    )
    assert seal.multi_crew_live_ready is False


def test_batch21g_closure_uses_assessment_timestamp() -> None:
    assessment = _assessment()
    seal = seal_master_allocation_batch21g(assessment=assessment)
    assert seal.sealed_at == assessment.assessed_at


def test_batch21g_closure_is_deterministic() -> None:
    assessment = _assessment()
    first = seal_master_allocation_batch21g(assessment=assessment)
    second = seal_master_allocation_batch21g(assessment=assessment)
    assert first == second
    assert first.closure_fingerprint_sha256 == second.closure_fingerprint_sha256


def test_batch21g_closure_grants_no_runtime_authority() -> None:
    seal = seal_master_allocation_batch21g(assessment=_assessment())
    assert seal.live_activation_performed is False
    assert seal.operator_arm_still_required is True
    assert seal.policy_mutation_authority is False
    assert seal.reservation_authority is False
    assert seal.risk_authority is False
    assert seal.admission_authority is False
    assert seal.registry_mutation is False
    assert seal.broker_authority is False
    assert seal.live_authority is False
    assert seal.auto_execute is False


def test_batch21g_closure_rejects_tampered_assessment() -> None:
    assessment = _assessment()
    _tamper(assessment, fingerprint_sha256=DIGEST_D)
    with pytest.raises(ValueError, match="assessment fingerprint integrity failure"):
        seal_master_allocation_batch21g(assessment=assessment)


def test_public_exports_are_available() -> None:
    assert portfolio.MasterAllocationReadinessAssessment is not None
    assert portfolio.MasterAllocationReadinessEvidence is not None
    assert portfolio.MasterAllocationBatch21gClosureSeal is not None
    assert portfolio.assess_master_allocation_live_readiness is (
        assess_master_allocation_live_readiness
    )
    assert portfolio.build_master_allocation_readiness_evidence is (
        build_master_allocation_readiness_evidence
    )
    assert portfolio.seal_master_allocation_batch21g is seal_master_allocation_batch21g
