from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.portfolio.allocation import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    MasterAllocationPolicy,
    build_master_allocation_policy,
)
from app.portfolio.allocation_policy_application import (
    MasterAllocationPolicyApplicationAuthorization,
    MasterAllocationPolicyApplicationAuthorizationAction,
    MasterAllocationPolicyApplicationAuthorizationStatus,
    MasterAllocationPolicyApplicationPreflight,
    MasterAllocationPolicyApplicationPreflightReasonCode,
    MasterAllocationPolicyApplicationPreflightStatus,
    build_master_allocation_policy_application_authorization,
    evaluate_master_allocation_policy_application_preflight,
    master_allocation_policy_application_authorization_payload,
    master_allocation_policy_application_preflight_payload,
)
from app.portfolio.allocation_policy_change import (
    MasterAllocationPolicyChangeCandidate,
    master_allocation_policy_change_candidate_payload,
)
from app.services.backtest.ids import stable_digest
from tests.portfolio.test_master_allocation_policy_change_candidate import _build, _bundle

AUTH_TIME = datetime(2026, 2, 1, 13, 5, tzinfo=UTC)
CHECK_TIME = datetime(2026, 2, 1, 13, 6, tzinfo=UTC)


def _context() -> tuple[MasterAllocationPolicy, MasterAllocationPolicyChangeCandidate]:
    bundle = _bundle()
    return bundle[0], _build(bundle)


def _authorization(
    candidate: MasterAllocationPolicyChangeCandidate | None = None,
    *,
    action: MasterAllocationPolicyApplicationAuthorizationAction = (
        MasterAllocationPolicyApplicationAuthorizationAction.AUTHORIZE
    ),
) -> MasterAllocationPolicyApplicationAuthorization:
    if candidate is None:
        _policy, candidate = _context()
    return build_master_allocation_policy_application_authorization(
        candidate=candidate,
        action=action,
        operator_ref="operator-policy-application:batch21g-step2",
        rationale_codes=("EXPLICIT_POLICY_APPLICATION_DECISION",),
        decided_at=AUTH_TIME,
    )


def _preflight(
    *,
    policy: MasterAllocationPolicy | None = None,
    candidate: MasterAllocationPolicyChangeCandidate | None = None,
    authorization: MasterAllocationPolicyApplicationAuthorization | None = None,
    checked_at: datetime = CHECK_TIME,
) -> MasterAllocationPolicyApplicationPreflight:
    if policy is None or candidate is None:
        default_policy, default_candidate = _context()
        policy = default_policy if policy is None else policy
        candidate = default_candidate if candidate is None else candidate
    if authorization is None:
        authorization = _authorization(candidate)
    return evaluate_master_allocation_policy_application_preflight(
        candidate=candidate,
        authorization=authorization,
        current_allocation_policy=policy,
        checked_at=checked_at,
    )


def test_builds_explicit_authorization_for_exact_candidate() -> None:
    policy, candidate = _context()
    authorization = _authorization(candidate)

    assert authorization.status is MasterAllocationPolicyApplicationAuthorizationStatus.AUTHORIZED
    assert authorization.action is MasterAllocationPolicyApplicationAuthorizationAction.AUTHORIZE
    assert authorization.master_portfolio_id == policy.master_portfolio_id
    assert authorization.change_candidate_id == candidate.change_candidate_id
    assert authorization.change_candidate_fingerprint_sha256 == candidate.fingerprint_sha256
    assert authorization.base_policy_id == candidate.base_policy_id
    assert authorization.base_policy_fingerprint_sha256 == candidate.base_policy_fingerprint_sha256


def test_reject_and_defer_are_recorded_as_distinct_operator_outcomes() -> None:
    _policy, candidate = _context()

    rejected = _authorization(
        candidate,
        action=MasterAllocationPolicyApplicationAuthorizationAction.REJECT,
    )
    deferred = _authorization(
        candidate,
        action=MasterAllocationPolicyApplicationAuthorizationAction.DEFER,
    )

    assert rejected.status is MasterAllocationPolicyApplicationAuthorizationStatus.REJECTED
    assert deferred.status is MasterAllocationPolicyApplicationAuthorizationStatus.DEFERRED


def test_authorization_preserves_strict_non_application_boundary() -> None:
    authorization = _authorization()

    assert authorization.human_operator_required is True
    assert authorization.single_candidate_scope is True
    assert authorization.deterministic_preflight_required is True
    assert authorization.atomic_compare_and_swap_required is True
    assert authorization.policy_application_performed is False
    assert authorization.runtime_policy_application_authority is False
    assert authorization.auto_apply is False
    assert authorization.dynamic_allocation_enabled is False
    assert authorization.reservation_authority is False
    assert authorization.risk_authority is False
    assert authorization.admission_authority is False
    assert authorization.local_risk_override is False
    assert authorization.resize_authority is False
    assert authorization.registry_mutation is False
    assert authorization.broker_authority is False
    assert authorization.live_authority is False
    assert authorization.auto_execute is False


def test_authorization_is_deterministic_and_fingerprinted() -> None:
    _policy, candidate = _context()

    first = _authorization(candidate)
    second = _authorization(candidate)

    assert first == second
    assert first.authorization_id == second.authorization_id
    assert first.fingerprint_sha256 == stable_digest(
        master_allocation_policy_application_authorization_payload(first)
    )


def test_authorization_rejects_time_before_advisory_review() -> None:
    _policy, candidate = _context()

    with pytest.raises(ValueError, match="cannot predate advisory review"):
        build_master_allocation_policy_application_authorization(
            candidate=candidate,
            action=MasterAllocationPolicyApplicationAuthorizationAction.AUTHORIZE,
            operator_ref="operator:too-early",
            rationale_codes=("EXPLICIT_POLICY_APPLICATION_DECISION",),
            decided_at=candidate.reviewed_at - timedelta(seconds=1),
        )


def test_authorization_rejects_blank_operator_reference() -> None:
    _policy, candidate = _context()

    with pytest.raises(ValueError, match="operator_ref"):
        build_master_allocation_policy_application_authorization(
            candidate=candidate,
            action=MasterAllocationPolicyApplicationAuthorizationAction.AUTHORIZE,
            operator_ref="   ",
            rationale_codes=("EXPLICIT_POLICY_APPLICATION_DECISION",),
            decided_at=AUTH_TIME,
        )


def test_authorization_rejects_duplicate_rationale_codes() -> None:
    _policy, candidate = _context()

    with pytest.raises(ValueError, match="rationale_codes"):
        build_master_allocation_policy_application_authorization(
            candidate=candidate,
            action=MasterAllocationPolicyApplicationAuthorizationAction.AUTHORIZE,
            operator_ref="operator:duplicate-reason",
            rationale_codes=("SAME", "SAME"),
            decided_at=AUTH_TIME,
        )


def test_authorization_rejects_tampered_change_candidate() -> None:
    _policy, candidate = _context()
    object.__setattr__(candidate, "operator_ref", "tampered-operator")

    with pytest.raises(ValueError, match="candidate fingerprint integrity"):
        _authorization(candidate)


def test_preflight_is_ready_for_fresh_authorized_base_policy() -> None:
    preflight = _preflight()

    assert preflight.status is (
        MasterAllocationPolicyApplicationPreflightStatus.READY_FOR_APPLICATION
    )
    assert preflight.reason_codes == (MasterAllocationPolicyApplicationPreflightReasonCode.READY,)
    assert preflight.ready_for_application is True


def test_ready_preflight_verifies_every_required_guard() -> None:
    preflight = _preflight()

    assert preflight.operator_authorization_verified is True
    assert preflight.base_policy_identity_verified is True
    assert preflight.base_policy_fingerprint_verified is True
    assert preflight.membership_verified is True
    assert preflight.configuration_verified is True


def test_preflight_binds_candidate_authorization_and_current_policy() -> None:
    policy, candidate = _context()
    authorization = _authorization(candidate)
    preflight = _preflight(
        policy=policy,
        candidate=candidate,
        authorization=authorization,
    )

    assert preflight.change_candidate_id == candidate.change_candidate_id
    assert preflight.change_candidate_fingerprint_sha256 == candidate.fingerprint_sha256
    assert preflight.authorization_id == authorization.authorization_id
    assert preflight.authorization_fingerprint_sha256 == authorization.fingerprint_sha256
    assert preflight.base_policy_id == candidate.base_policy_id
    assert preflight.base_policy_fingerprint_sha256 == candidate.base_policy_fingerprint_sha256
    assert preflight.current_policy_id == policy.policy_id
    assert preflight.current_policy_fingerprint_sha256 == policy.fingerprint_sha256


def test_preflight_remains_non_mutating_and_non_trading() -> None:
    preflight = _preflight()

    assert preflight.preflight_only is True
    assert preflight.atomic_compare_and_swap_still_required is True
    assert preflight.policy_application_performed is False
    assert preflight.policy_mutation is False
    assert preflight.auto_apply is False
    assert preflight.dynamic_allocation_enabled is False
    assert preflight.reservation_authority is False
    assert preflight.risk_authority is False
    assert preflight.admission_authority is False
    assert preflight.local_risk_override is False
    assert preflight.resize_authority is False
    assert preflight.registry_mutation is False
    assert preflight.broker_authority is False
    assert preflight.live_authority is False
    assert preflight.auto_execute is False


def test_preflight_is_deterministic_and_fingerprinted() -> None:
    policy, candidate = _context()
    authorization = _authorization(candidate)

    first = _preflight(policy=policy, candidate=candidate, authorization=authorization)
    second = _preflight(policy=policy, candidate=candidate, authorization=authorization)

    assert first == second
    assert first.preflight_id == second.preflight_id
    assert first.fingerprint_sha256 == stable_digest(
        master_allocation_policy_application_preflight_payload(first)
    )


def test_rejected_operator_decision_blocks_preflight() -> None:
    policy, candidate = _context()
    authorization = _authorization(
        candidate,
        action=MasterAllocationPolicyApplicationAuthorizationAction.REJECT,
    )

    preflight = _preflight(
        policy=policy,
        candidate=candidate,
        authorization=authorization,
    )

    assert preflight.status is MasterAllocationPolicyApplicationPreflightStatus.BLOCKED
    assert MasterAllocationPolicyApplicationPreflightReasonCode.OPERATOR_REJECTED in (
        preflight.reason_codes
    )
    assert preflight.operator_authorization_verified is False


def test_deferred_operator_decision_blocks_preflight() -> None:
    policy, candidate = _context()
    authorization = _authorization(
        candidate,
        action=MasterAllocationPolicyApplicationAuthorizationAction.DEFER,
    )

    preflight = _preflight(
        policy=policy,
        candidate=candidate,
        authorization=authorization,
    )

    assert preflight.status is MasterAllocationPolicyApplicationPreflightStatus.BLOCKED
    assert MasterAllocationPolicyApplicationPreflightReasonCode.OPERATOR_DEFERRED in (
        preflight.reason_codes
    )


def test_changed_policy_fingerprint_blocks_stale_application() -> None:
    policy, candidate = _context()
    changed = build_master_allocation_policy(
        master_portfolio_id=policy.master_portfolio_id,
        policy_id=policy.policy_id,
        members=policy.members,
        envelopes=candidate.proposed_envelopes,
        source_ref="operator-policy:changed-after-candidate",
    )

    preflight = _preflight(policy=changed, candidate=candidate)

    assert preflight.status is MasterAllocationPolicyApplicationPreflightStatus.BLOCKED
    assert (
        MasterAllocationPolicyApplicationPreflightReasonCode.BASE_POLICY_FINGERPRINT_MISMATCH
        in preflight.reason_codes
    )
    assert preflight.base_policy_fingerprint_verified is False


def test_changed_policy_id_blocks_preflight() -> None:
    policy, candidate = _context()
    changed = build_master_allocation_policy(
        master_portfolio_id=policy.master_portfolio_id,
        policy_id="replacement-policy-id",
        members=policy.members,
        envelopes=policy.envelopes,
        source_ref=policy.source_ref,
    )

    preflight = _preflight(policy=changed, candidate=candidate)

    assert MasterAllocationPolicyApplicationPreflightReasonCode.BASE_POLICY_ID_MISMATCH in (
        preflight.reason_codes
    )
    assert preflight.base_policy_identity_verified is False


def test_changed_master_portfolio_blocks_preflight() -> None:
    policy, candidate = _context()
    changed = build_master_allocation_policy(
        master_portfolio_id="other-master-portfolio",
        policy_id=policy.policy_id,
        members=policy.members,
        envelopes=policy.envelopes,
        source_ref=policy.source_ref,
    )

    preflight = _preflight(policy=changed, candidate=candidate)

    assert MasterAllocationPolicyApplicationPreflightReasonCode.MASTER_PORTFOLIO_MISMATCH in (
        preflight.reason_codes
    )
    assert preflight.base_policy_identity_verified is False


def test_changed_membership_blocks_preflight() -> None:
    policy, candidate = _context()
    changed = build_master_allocation_policy(
        master_portfolio_id=policy.master_portfolio_id,
        policy_id=policy.policy_id,
        members=policy.members[:1],
        envelopes=policy.envelopes[:1],
        source_ref=policy.source_ref,
    )

    preflight = _preflight(policy=changed, candidate=candidate)

    assert MasterAllocationPolicyApplicationPreflightReasonCode.MEMBERSHIP_MISMATCH in (
        preflight.reason_codes
    )
    assert preflight.membership_verified is False


def test_not_configured_current_policy_blocks_preflight() -> None:
    policy, candidate = _context()
    unconfigured = tuple(
        CrewAllocationEnvelope(
            system_id=member.system_id,
            status=AllocationEnvelopeStatus.NOT_CONFIGURED,
            reason_code="OPERATOR_NOT_CONFIGURED",
        )
        for member in policy.members
    )
    changed = build_master_allocation_policy(
        master_portfolio_id=policy.master_portfolio_id,
        policy_id=policy.policy_id,
        members=policy.members,
        envelopes=unconfigured,
        source_ref="operator-policy:not-configured",
    )

    preflight = _preflight(policy=changed, candidate=candidate)

    assert MasterAllocationPolicyApplicationPreflightReasonCode.BASE_POLICY_NOT_CONFIGURED in (
        preflight.reason_codes
    )
    assert preflight.configuration_verified is False


def test_preflight_rejects_tampered_current_policy_integrity() -> None:
    policy, candidate = _context()
    object.__setattr__(policy, "policy_id", "tampered-policy")

    with pytest.raises(ValueError, match="current policy fingerprint integrity"):
        _preflight(policy=policy, candidate=candidate)


def test_preflight_rejects_tampered_authorization_integrity() -> None:
    policy, candidate = _context()
    authorization = _authorization(candidate)
    object.__setattr__(authorization, "operator_ref", "tampered-operator")

    with pytest.raises(ValueError, match="authorization fingerprint integrity"):
        _preflight(
            policy=policy,
            candidate=candidate,
            authorization=authorization,
        )


def test_preflight_rejects_authorization_for_another_candidate() -> None:
    policy, candidate = _context()
    authorization = _authorization(candidate)
    object.__setattr__(authorization, "change_candidate_id", "other-change-candidate")
    object.__setattr__(
        authorization,
        "fingerprint_sha256",
        stable_digest(master_allocation_policy_application_authorization_payload(authorization)),
    )

    with pytest.raises(ValueError, match="candidate provenance mismatch"):
        _preflight(
            policy=policy,
            candidate=candidate,
            authorization=authorization,
        )


def test_preflight_rejects_check_time_before_authorization() -> None:
    policy, candidate = _context()
    authorization = _authorization(candidate)

    with pytest.raises(ValueError, match="cannot predate operator authorization"):
        _preflight(
            policy=policy,
            candidate=candidate,
            authorization=authorization,
            checked_at=authorization.decided_at - timedelta(seconds=1),
        )


def test_preflight_cannot_be_forged_with_inconsistent_verification_flags() -> None:
    preflight = _preflight()
    object.__setattr__(preflight, "operator_authorization_verified", False)
    object.__setattr__(
        preflight,
        "fingerprint_sha256",
        stable_digest(master_allocation_policy_application_preflight_payload(preflight)),
    )

    with pytest.raises(ValueError, match="every verification"):
        MasterAllocationPolicyApplicationPreflight(
            preflight_id=preflight.preflight_id,
            status=preflight.status,
            reason_codes=preflight.reason_codes,
            master_portfolio_id=preflight.master_portfolio_id,
            change_candidate_id=preflight.change_candidate_id,
            change_candidate_fingerprint_sha256=preflight.change_candidate_fingerprint_sha256,
            authorization_id=preflight.authorization_id,
            authorization_fingerprint_sha256=preflight.authorization_fingerprint_sha256,
            base_policy_id=preflight.base_policy_id,
            base_policy_fingerprint_sha256=preflight.base_policy_fingerprint_sha256,
            current_policy_id=preflight.current_policy_id,
            current_policy_fingerprint_sha256=preflight.current_policy_fingerprint_sha256,
            proposed_system_ids=preflight.proposed_system_ids,
            operator_authorization_verified=preflight.operator_authorization_verified,
            base_policy_identity_verified=preflight.base_policy_identity_verified,
            base_policy_fingerprint_verified=preflight.base_policy_fingerprint_verified,
            membership_verified=preflight.membership_verified,
            configuration_verified=preflight.configuration_verified,
            checked_at=preflight.checked_at,
            fingerprint_sha256=preflight.fingerprint_sha256,
        )


def test_step2_does_not_build_or_apply_master_allocation_policy() -> None:
    authorization = _authorization()
    preflight = _preflight()

    assert not isinstance(authorization, MasterAllocationPolicy)
    assert not isinstance(preflight, MasterAllocationPolicy)
    assert not hasattr(preflight, "new_policy_id")
    assert not hasattr(preflight, "apply")


def test_public_contract_exposes_authorization_and_preflight() -> None:
    import app.portfolio as portfolio

    assert (
        portfolio.MasterAllocationPolicyApplicationAuthorization
        is MasterAllocationPolicyApplicationAuthorization
    )
    assert (
        portfolio.MasterAllocationPolicyApplicationPreflight
        is MasterAllocationPolicyApplicationPreflight
    )
    assert (
        portfolio.build_master_allocation_policy_application_authorization
        is build_master_allocation_policy_application_authorization
    )
    assert (
        portfolio.evaluate_master_allocation_policy_application_preflight
        is evaluate_master_allocation_policy_application_preflight
    )


def test_candidate_integrity_payload_remains_unchanged_by_step2() -> None:
    _policy, candidate = _context()
    before = stable_digest(master_allocation_policy_change_candidate_payload(candidate))

    _authorization(candidate)

    after = stable_digest(master_allocation_policy_change_candidate_payload(candidate))
    assert before == after == candidate.fingerprint_sha256
