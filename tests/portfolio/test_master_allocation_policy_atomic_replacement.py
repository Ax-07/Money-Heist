from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from app.portfolio.allocation import (
    AllocationPolicySource,
    MasterAllocationPolicy,
    build_master_allocation_policy,
)
from app.portfolio.allocation_policy_application import (
    MasterAllocationPolicyApplicationAuthorizationAction,
    MasterAllocationPolicyApplicationPreflightStatus,
    master_allocation_policy_application_authorization_payload,
    master_allocation_policy_application_preflight_payload,
)
from app.portfolio.allocation_policy_change import (
    master_allocation_policy_change_candidate_payload,
)
from app.portfolio.allocation_policy_replacement import (
    InMemoryMasterAllocationPolicyAtomicState,
    MasterAllocationPolicyReplacementReasonCode,
    MasterAllocationPolicyReplacementReceipt,
    MasterAllocationPolicyReplacementStatus,
    apply_master_allocation_policy_replacement,
    master_allocation_policy_replacement_receipt_payload,
)
from app.services.backtest.ids import stable_digest
from tests.portfolio.test_master_allocation_policy_application_preflight import (
    CHECK_TIME,
    _authorization,
    _context,
    _preflight,
)

APPLY_TIME = datetime(2026, 2, 1, 13, 7, tzinfo=UTC)


def _ready_bundle():
    policy, candidate = _context()
    authorization = _authorization(candidate)
    preflight = _preflight(
        policy=policy,
        candidate=candidate,
        authorization=authorization,
    )
    return policy, candidate, authorization, preflight


def _apply(
    state: InMemoryMasterAllocationPolicyAtomicState | None = None,
    *,
    new_policy_id: str = "master-allocation-policy-v2",
    source_ref: str = "operator-policy-application:batch21g-step3",
    attempted_at: datetime = APPLY_TIME,
):
    policy, candidate, authorization, preflight = _ready_bundle()
    if state is None:
        state = InMemoryMasterAllocationPolicyAtomicState(policy)
    receipt = apply_master_allocation_policy_replacement(
        atomic_state=state,
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=policy,
        new_policy_id=new_policy_id,
        application_source_ref=source_ref,
        attempted_at=attempted_at,
    )
    return state, policy, candidate, authorization, preflight, receipt


def test_atomic_state_starts_with_exact_policy() -> None:
    policy, _candidate = _context()
    state = InMemoryMasterAllocationPolicyAtomicState(policy)

    assert state.snapshot() is policy


def test_atomic_state_declares_in_process_non_live_scope() -> None:
    policy, _candidate = _context()
    state = InMemoryMasterAllocationPolicyAtomicState(policy)

    assert state.in_process_only is True
    assert state.durable is False
    assert state.multi_process_safe is False
    assert state.live_ready is False


def test_ready_preflight_applies_exact_operator_owned_envelopes() -> None:
    state, _policy, candidate, _authorization_record, _preflight_record, receipt = _apply()
    active = state.snapshot()

    assert receipt.status is MasterAllocationPolicyReplacementStatus.APPLIED
    assert receipt.reason_code is MasterAllocationPolicyReplacementReasonCode.APPLIED
    assert receipt.applied is True
    assert active.envelopes == candidate.proposed_envelopes


def test_replacement_preserves_membership_and_master_identity() -> None:
    state, base, _candidate, _authorization_record, _preflight_record, _receipt = _apply()
    active = state.snapshot()

    assert active.master_portfolio_id == base.master_portfolio_id
    assert active.members == base.members


def test_replacement_policy_uses_explicit_operator_configuration_provenance() -> None:
    state, _base, _candidate, _authorization_record, _preflight_record, _receipt = _apply(
        source_ref="operator-policy:approved-replacement-2026-02-01"
    )
    active = state.snapshot()

    assert active.source is AllocationPolicySource.OPERATOR_CONFIGURATION
    assert active.source_ref == "operator-policy:approved-replacement-2026-02-01"
    assert active.auto_apply is False
    assert active.dynamic_allocation is False


def test_receipt_binds_exact_candidate_authorization_preflight_and_base() -> None:
    _state, base, candidate, authorization, preflight, receipt = _apply()

    assert receipt.change_candidate_id == candidate.change_candidate_id
    assert receipt.change_candidate_fingerprint_sha256 == candidate.fingerprint_sha256
    assert receipt.authorization_id == authorization.authorization_id
    assert receipt.authorization_fingerprint_sha256 == authorization.fingerprint_sha256
    assert receipt.preflight_id == preflight.preflight_id
    assert receipt.preflight_fingerprint_sha256 == preflight.fingerprint_sha256
    assert receipt.expected_base_policy_id == base.policy_id
    assert receipt.expected_base_policy_fingerprint_sha256 == base.fingerprint_sha256


def test_applied_receipt_records_mutation_time_compare_and_swap() -> None:
    _state, base, _candidate, _authorization_record, _preflight_record, receipt = _apply()

    assert receipt.atomic_compare_and_swap_performed is True
    assert receipt.base_policy_revalidated_at_mutation is True
    assert receipt.policy_mutation_performed is True
    assert receipt.observed_policy_id_at_mutation == base.policy_id
    assert receipt.observed_policy_fingerprint_sha256_at_mutation == base.fingerprint_sha256
    assert receipt.active_policy_id_after_attempt == receipt.requested_new_policy_id
    assert (
        receipt.active_policy_fingerprint_sha256_after_attempt
        == receipt.requested_new_policy_fingerprint_sha256
    )


def test_receipt_grants_no_trading_or_live_authority() -> None:
    _state, _base, _candidate, _authorization_record, _preflight_record, receipt = _apply()

    assert receipt.static_policy_replacement_only is True
    assert receipt.dynamic_allocation_enabled is False
    assert receipt.reservation_authority is False
    assert receipt.risk_authority is False
    assert receipt.admission_authority is False
    assert receipt.local_risk_override is False
    assert receipt.resize_authority is False
    assert receipt.registry_mutation is False
    assert receipt.broker_authority is False
    assert receipt.live_authority is False
    assert receipt.auto_execute is False


def test_receipt_is_deterministic_for_same_fresh_state_and_inputs() -> None:
    first = _apply()[-1]
    second = _apply()[-1]

    assert first == second
    assert first.fingerprint_sha256 == stable_digest(
        master_allocation_policy_replacement_receipt_payload(first)
    )


def test_atomic_cas_blocks_policy_changed_after_preflight() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    changed = build_master_allocation_policy(
        master_portfolio_id=base.master_portfolio_id,
        policy_id="intervening-policy",
        members=base.members,
        envelopes=base.envelopes,
        source_ref="operator-policy:intervening-change",
    )
    state = InMemoryMasterAllocationPolicyAtomicState(changed)

    receipt = apply_master_allocation_policy_replacement(
        atomic_state=state,
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base,
        new_policy_id="master-allocation-policy-v2",
        application_source_ref="operator-policy:attempt-after-race",
        attempted_at=APPLY_TIME,
    )

    assert receipt.status is MasterAllocationPolicyReplacementStatus.CAS_CONFLICT
    assert receipt.reason_code is (
        MasterAllocationPolicyReplacementReasonCode.ATOMIC_BASE_POLICY_MISMATCH
    )
    assert receipt.policy_mutation_performed is False
    assert state.snapshot() == changed


def test_cas_conflict_receipt_records_observed_policy_and_leaves_it_active() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    changed = build_master_allocation_policy(
        master_portfolio_id=base.master_portfolio_id,
        policy_id="intervening-policy",
        members=base.members,
        envelopes=base.envelopes,
        source_ref="operator-policy:intervening-change",
    )
    state = InMemoryMasterAllocationPolicyAtomicState(changed)

    receipt = apply_master_allocation_policy_replacement(
        atomic_state=state,
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base,
        new_policy_id="master-allocation-policy-v2",
        application_source_ref="operator-policy:attempt-after-race",
        attempted_at=APPLY_TIME,
    )

    assert receipt.observed_policy_id_at_mutation == changed.policy_id
    assert receipt.observed_policy_fingerprint_sha256_at_mutation == changed.fingerprint_sha256
    assert receipt.active_policy_id_after_attempt == changed.policy_id
    assert receipt.active_policy_fingerprint_sha256_after_attempt == changed.fingerprint_sha256


def test_second_application_of_same_base_cannot_overwrite_first() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    first = apply_master_allocation_policy_replacement(
        atomic_state=state,
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base,
        new_policy_id="policy-first",
        application_source_ref="operator-policy:first",
        attempted_at=APPLY_TIME,
    )
    second = apply_master_allocation_policy_replacement(
        atomic_state=state,
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base,
        new_policy_id="policy-second",
        application_source_ref="operator-policy:second",
        attempted_at=APPLY_TIME,
    )

    assert first.status is MasterAllocationPolicyReplacementStatus.APPLIED
    assert second.status is MasterAllocationPolicyReplacementStatus.CAS_CONFLICT
    assert state.snapshot().policy_id == "policy-first"


def test_concurrent_replacements_allow_exactly_one_cas_winner() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    def apply_one(index: int) -> MasterAllocationPolicyReplacementReceipt:
        return apply_master_allocation_policy_replacement(
            atomic_state=state,
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            new_policy_id=f"policy-concurrent-{index}",
            application_source_ref=f"operator-policy:concurrent-{index}",
            attempted_at=APPLY_TIME,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = tuple(pool.map(apply_one, (1, 2)))

    statuses = [receipt.status for receipt in receipts]
    assert statuses.count(MasterAllocationPolicyReplacementStatus.APPLIED) == 1
    assert statuses.count(MasterAllocationPolicyReplacementStatus.CAS_CONFLICT) == 1
    winner = next(receipt for receipt in receipts if receipt.applied)
    assert state.snapshot().policy_id == winner.requested_new_policy_id


def test_replacement_rejects_blocked_preflight_before_touching_state() -> None:
    base, candidate = _context()
    authorization = _authorization(
        candidate,
        action=MasterAllocationPolicyApplicationAuthorizationAction.REJECT,
    )
    blocked = _preflight(
        policy=base,
        candidate=candidate,
        authorization=authorization,
    )
    assert blocked.status is MasterAllocationPolicyApplicationPreflightStatus.BLOCKED
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    with pytest.raises(ValueError, match="requires AUTHORIZE operator action"):
        apply_master_allocation_policy_replacement(
            atomic_state=state,
            candidate=candidate,
            authorization=authorization,
            preflight=blocked,
            base_allocation_policy=base,
            new_policy_id="policy-never-applied",
            application_source_ref="operator-policy:blocked",
            attempted_at=APPLY_TIME,
        )

    assert state.snapshot() == base


def test_replacement_rejects_forged_ready_preflight() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    object.__setattr__(preflight, "authorization_id", "forged-authorization")
    object.__setattr__(
        preflight,
        "fingerprint_sha256",
        stable_digest(master_allocation_policy_application_preflight_payload(preflight)),
    )
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    with pytest.raises(ValueError, match="provenance mismatch"):
        apply_master_allocation_policy_replacement(
            atomic_state=state,
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            new_policy_id="policy-never-applied",
            application_source_ref="operator-policy:forged-preflight",
            attempted_at=APPLY_TIME,
        )


def test_replacement_rejects_tampered_candidate_integrity() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    object.__setattr__(candidate, "operator_ref", "tampered")
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    with pytest.raises(ValueError, match="change candidate fingerprint integrity"):
        apply_master_allocation_policy_replacement(
            atomic_state=state,
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            new_policy_id="policy-never-applied",
            application_source_ref="operator-policy:tampered-candidate",
            attempted_at=APPLY_TIME,
        )


def test_replacement_rejects_tampered_authorization_integrity() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    object.__setattr__(authorization, "operator_ref", "tampered")
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    with pytest.raises(ValueError, match="authorization fingerprint integrity"):
        apply_master_allocation_policy_replacement(
            atomic_state=state,
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            new_policy_id="policy-never-applied",
            application_source_ref="operator-policy:tampered-authorization",
            attempted_at=APPLY_TIME,
        )


def test_replacement_rejects_tampered_preflight_integrity() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    object.__setattr__(preflight, "checked_at", CHECK_TIME + timedelta(seconds=9))
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    with pytest.raises(ValueError, match="preflight fingerprint integrity"):
        apply_master_allocation_policy_replacement(
            atomic_state=state,
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            new_policy_id="policy-never-applied",
            application_source_ref="operator-policy:tampered-preflight",
            attempted_at=APPLY_TIME,
        )


def test_replacement_rejects_tampered_base_policy_integrity() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    state = InMemoryMasterAllocationPolicyAtomicState(base)
    object.__setattr__(base, "policy_id", "tampered-base")

    with pytest.raises(ValueError, match="base policy fingerprint integrity"):
        apply_master_allocation_policy_replacement(
            atomic_state=state,
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            new_policy_id="policy-never-applied",
            application_source_ref="operator-policy:tampered-base",
            attempted_at=APPLY_TIME,
        )


def test_atomic_state_rejects_tampered_current_policy() -> None:
    base, _candidate = _context()
    state = InMemoryMasterAllocationPolicyAtomicState(base)
    object.__setattr__(base, "policy_id", "tampered-after-state-init")

    with pytest.raises(ValueError, match="atomic state current policy fingerprint integrity"):
        state.snapshot()


def test_replacement_requires_new_policy_id_distinct_from_base() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    with pytest.raises(ValueError, match="must differ from base policy ID"):
        apply_master_allocation_policy_replacement(
            atomic_state=state,
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            new_policy_id=base.policy_id,
            application_source_ref="operator-policy:same-id",
            attempted_at=APPLY_TIME,
        )


def test_replacement_requires_explicit_nonblank_source_reference() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    with pytest.raises(ValueError, match="application_source_ref"):
        apply_master_allocation_policy_replacement(
            atomic_state=state,
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            new_policy_id="policy-v2",
            application_source_ref="   ",
            attempted_at=APPLY_TIME,
        )


def test_replacement_attempt_cannot_predate_preflight() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    with pytest.raises(ValueError, match="cannot predate preflight"):
        apply_master_allocation_policy_replacement(
            atomic_state=state,
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            new_policy_id="policy-v2",
            application_source_ref="operator-policy:too-early",
            attempted_at=preflight.checked_at - timedelta(seconds=1),
        )


def test_receipt_detects_post_construction_tampering() -> None:
    receipt = _apply()[-1]
    object.__setattr__(receipt, "operator_ref", "tampered")

    with pytest.raises(ValueError, match="receipt fingerprint mismatch"):
        MasterAllocationPolicyReplacementReceipt(
            application_id=receipt.application_id,
            status=receipt.status,
            reason_code=receipt.reason_code,
            master_portfolio_id=receipt.master_portfolio_id,
            change_candidate_id=receipt.change_candidate_id,
            change_candidate_fingerprint_sha256=receipt.change_candidate_fingerprint_sha256,
            authorization_id=receipt.authorization_id,
            authorization_fingerprint_sha256=receipt.authorization_fingerprint_sha256,
            preflight_id=receipt.preflight_id,
            preflight_fingerprint_sha256=receipt.preflight_fingerprint_sha256,
            expected_base_policy_id=receipt.expected_base_policy_id,
            expected_base_policy_fingerprint_sha256=(
                receipt.expected_base_policy_fingerprint_sha256
            ),
            observed_policy_id_at_mutation=receipt.observed_policy_id_at_mutation,
            observed_policy_fingerprint_sha256_at_mutation=(
                receipt.observed_policy_fingerprint_sha256_at_mutation
            ),
            requested_new_policy_id=receipt.requested_new_policy_id,
            requested_new_policy_fingerprint_sha256=(
                receipt.requested_new_policy_fingerprint_sha256
            ),
            active_policy_id_after_attempt=receipt.active_policy_id_after_attempt,
            active_policy_fingerprint_sha256_after_attempt=(
                receipt.active_policy_fingerprint_sha256_after_attempt
            ),
            application_source_ref=receipt.application_source_ref,
            operator_ref=receipt.operator_ref,
            attempted_at=receipt.attempted_at,
            atomic_compare_and_swap_performed=receipt.atomic_compare_and_swap_performed,
            base_policy_revalidated_at_mutation=receipt.base_policy_revalidated_at_mutation,
            policy_mutation_performed=receipt.policy_mutation_performed,
            fingerprint_sha256=receipt.fingerprint_sha256,
        )


def test_receipt_constructor_rejects_false_applied_mutation_flag() -> None:
    receipt = _apply()[-1]

    with pytest.raises(ValueError, match="must record policy mutation"):
        MasterAllocationPolicyReplacementReceipt(
            application_id=receipt.application_id,
            status=receipt.status,
            reason_code=receipt.reason_code,
            master_portfolio_id=receipt.master_portfolio_id,
            change_candidate_id=receipt.change_candidate_id,
            change_candidate_fingerprint_sha256=receipt.change_candidate_fingerprint_sha256,
            authorization_id=receipt.authorization_id,
            authorization_fingerprint_sha256=receipt.authorization_fingerprint_sha256,
            preflight_id=receipt.preflight_id,
            preflight_fingerprint_sha256=receipt.preflight_fingerprint_sha256,
            expected_base_policy_id=receipt.expected_base_policy_id,
            expected_base_policy_fingerprint_sha256=(
                receipt.expected_base_policy_fingerprint_sha256
            ),
            observed_policy_id_at_mutation=receipt.observed_policy_id_at_mutation,
            observed_policy_fingerprint_sha256_at_mutation=(
                receipt.observed_policy_fingerprint_sha256_at_mutation
            ),
            requested_new_policy_id=receipt.requested_new_policy_id,
            requested_new_policy_fingerprint_sha256=(
                receipt.requested_new_policy_fingerprint_sha256
            ),
            active_policy_id_after_attempt=receipt.active_policy_id_after_attempt,
            active_policy_fingerprint_sha256_after_attempt=(
                receipt.active_policy_fingerprint_sha256_after_attempt
            ),
            application_source_ref=receipt.application_source_ref,
            operator_ref=receipt.operator_ref,
            attempted_at=receipt.attempted_at,
            atomic_compare_and_swap_performed=receipt.atomic_compare_and_swap_performed,
            base_policy_revalidated_at_mutation=receipt.base_policy_revalidated_at_mutation,
            policy_mutation_performed=False,
            fingerprint_sha256=receipt.fingerprint_sha256,
        )


def test_step3_does_not_modify_source_candidate_authorization_or_preflight() -> None:
    base, candidate, authorization, preflight = _ready_bundle()
    candidate_before = stable_digest(master_allocation_policy_change_candidate_payload(candidate))
    authorization_before = stable_digest(
        master_allocation_policy_application_authorization_payload(authorization)
    )
    preflight_before = stable_digest(
        master_allocation_policy_application_preflight_payload(preflight)
    )
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    apply_master_allocation_policy_replacement(
        atomic_state=state,
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base,
        new_policy_id="policy-v2",
        application_source_ref="operator-policy:immutability-check",
        attempted_at=APPLY_TIME,
    )

    assert candidate_before == candidate.fingerprint_sha256
    assert authorization_before == authorization.fingerprint_sha256
    assert preflight_before == preflight.fingerprint_sha256


def test_public_contract_exposes_atomic_replacement() -> None:
    import app.portfolio as portfolio

    assert portfolio.InMemoryMasterAllocationPolicyAtomicState is (
        InMemoryMasterAllocationPolicyAtomicState
    )
    assert portfolio.MasterAllocationPolicyReplacementReceipt is (
        MasterAllocationPolicyReplacementReceipt
    )
    assert portfolio.apply_master_allocation_policy_replacement is (
        apply_master_allocation_policy_replacement
    )


def test_step3_builds_real_master_allocation_policy_only_after_ready_chain() -> None:
    state, _base, _candidate, _authorization_record, preflight, receipt = _apply()

    assert preflight.status is (
        MasterAllocationPolicyApplicationPreflightStatus.READY_FOR_APPLICATION
    )
    assert receipt.status is MasterAllocationPolicyReplacementStatus.APPLIED
    assert isinstance(state.snapshot(), MasterAllocationPolicy)
