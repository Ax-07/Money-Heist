from __future__ import annotations

from copy import copy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.portfolio import (
    MasterAllocationPolicyChangeAuditReport,
    MasterAllocationPolicyChangeAuditStatus,
    MasterAllocationPolicyChangeClosureSeal,
    MasterAllocationPolicyChangeClosureStatus,
    audit_master_allocation_policy_change,
    seal_master_allocation_policy_change,
)
from app.portfolio.allocation import build_master_allocation_policy
from app.portfolio.allocation_policy_change_closure import (
    master_allocation_policy_change_audit_payload,
    master_allocation_policy_change_closure_payload,
)
from app.portfolio.allocation_policy_replacement import (
    MasterAllocationPolicyReplacementStatus,
    apply_master_allocation_policy_replacement,
    master_allocation_policy_replacement_receipt_payload,
)
from app.portfolio.allocation_policy_store import SQLiteMasterAllocationPolicyStore
from app.services.backtest.ids import stable_digest
from tests.portfolio.test_master_allocation_policy_atomic_replacement import (
    APPLY_TIME,
    _apply,
    _ready_bundle,
)
from tests.portfolio.test_master_allocation_policy_persistent_store import _persistent_apply

AUDIT_TIME = datetime(2026, 2, 1, 13, 8, tzinfo=UTC)
STORE_REF = "sqlite-store:master-portfolio-policy"


def _applied_audit(path: Path):
    store, base, candidate, authorization, preflight, receipt = _persistent_apply(path)
    audit = audit_master_allocation_policy_change(
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base,
        receipt=receipt,
        store=store,
        store_ref=STORE_REF,
        audited_at=AUDIT_TIME,
    )
    return store, base, candidate, authorization, preflight, receipt, audit


def _conflict_bundle(path: Path):
    base, candidate, authorization, preflight = _ready_bundle()
    intervening = build_master_allocation_policy(
        master_portfolio_id=base.master_portfolio_id,
        policy_id="intervening-policy",
        members=base.members,
        envelopes=base.envelopes,
        source_ref="operator-policy:intervening",
    )
    store = SQLiteMasterAllocationPolicyStore(
        database_path=path,
        master_portfolio_id=base.master_portfolio_id,
        initial_policy=intervening,
    )
    receipt = apply_master_allocation_policy_replacement(
        atomic_state=store,
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base,
        new_policy_id="never-applied-policy",
        application_source_ref="operator-policy:conflict-attempt",
        attempted_at=APPLY_TIME,
    )
    return store, base, candidate, authorization, preflight, receipt


def _conflict_audit(path: Path):
    store, base, candidate, authorization, preflight, receipt = _conflict_bundle(path)
    audit = audit_master_allocation_policy_change(
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base,
        receipt=receipt,
        store=store,
        store_ref=STORE_REF,
        audited_at=AUDIT_TIME,
    )
    return store, base, candidate, authorization, preflight, receipt, audit


def _tamper(value, **changes):
    forged = copy(value)
    for name, replacement in changes.items():
        object.__setattr__(forged, name, replacement)
    return forged


def test_applied_lifecycle_audit_is_verified(tmp_path: Path) -> None:
    *_, audit = _applied_audit(tmp_path / "policy.db")

    assert audit.status is MasterAllocationPolicyChangeAuditStatus.VERIFIED
    assert audit.policy_change_applied is True


def test_applied_audit_binds_entire_step1_to_step4_chain(tmp_path: Path) -> None:
    _store, base, candidate, authorization, preflight, receipt, audit = _applied_audit(
        tmp_path / "policy.db"
    )

    assert audit.change_candidate_id == candidate.change_candidate_id
    assert audit.authorization_id == authorization.authorization_id
    assert audit.preflight_id == preflight.preflight_id
    assert audit.application_id == receipt.application_id
    assert audit.base_policy_id == base.policy_id


def test_applied_audit_binds_exact_persisted_policy(tmp_path: Path) -> None:
    store, _base, _candidate, _authorization, _preflight, receipt, audit = _applied_audit(
        tmp_path / "policy.db"
    )
    active = store.snapshot()

    assert audit.active_policy_id == active.policy_id == receipt.requested_new_policy_id
    assert audit.active_policy_fingerprint_sha256 == active.fingerprint_sha256
    assert audit.requested_policy_fingerprint_sha256 == active.fingerprint_sha256


def test_audit_records_persistent_store_scope_without_claiming_live(tmp_path: Path) -> None:
    *_, audit = _applied_audit(tmp_path / "policy.db")

    assert audit.store_durable is True
    assert audit.store_multi_process_safe is True
    assert audit.store_multi_host_safe is False
    assert audit.store_live_ready is False


def test_audit_grants_no_runtime_authority(tmp_path: Path) -> None:
    *_, audit = _applied_audit(tmp_path / "policy.db")

    assert audit.audit_only is True
    assert audit.read_only is True
    assert audit.lifecycle_closed is False
    assert audit.dynamic_allocation_enabled is False
    assert audit.policy_mutation_authority is False
    assert audit.reservation_authority is False
    assert audit.risk_authority is False
    assert audit.admission_authority is False
    assert audit.registry_mutation is False
    assert audit.broker_authority is False
    assert audit.live_authority is False
    assert audit.auto_execute is False


def test_audit_is_deterministic_for_same_state_and_inputs(tmp_path: Path) -> None:
    store, base, candidate, authorization, preflight, receipt, first = _applied_audit(
        tmp_path / "policy.db"
    )
    second = audit_master_allocation_policy_change(
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base,
        receipt=receipt,
        store=store,
        store_ref=STORE_REF,
        audited_at=AUDIT_TIME,
    )

    assert first == second
    assert first.fingerprint_sha256 == stable_digest(
        master_allocation_policy_change_audit_payload(first)
    )


def test_closure_seals_verified_applied_audit(tmp_path: Path) -> None:
    *_, audit = _applied_audit(tmp_path / "policy.db")
    seal = seal_master_allocation_policy_change(audit=audit)

    assert seal.status is MasterAllocationPolicyChangeClosureStatus.SEALED
    assert seal.policy_change_applied is True
    assert seal.lifecycle_closed is True


def test_closure_binds_audit_receipt_and_active_policy(tmp_path: Path) -> None:
    *_, receipt, audit = _applied_audit(tmp_path / "policy.db")
    seal = seal_master_allocation_policy_change(audit=audit)

    assert seal.audit_fingerprint_sha256 == audit.fingerprint_sha256
    assert seal.replacement_receipt_fingerprint_sha256 == receipt.fingerprint_sha256
    assert seal.active_policy_id == audit.active_policy_id
    assert seal.active_policy_fingerprint_sha256 == audit.active_policy_fingerprint_sha256


def test_closure_uses_audit_timestamp_without_wall_clock(tmp_path: Path) -> None:
    *_, audit = _applied_audit(tmp_path / "policy.db")
    seal = seal_master_allocation_policy_change(audit=audit)

    assert seal.sealed_at == AUDIT_TIME == audit.audited_at


def test_closure_grants_no_risk_broker_or_live_authority(tmp_path: Path) -> None:
    *_, audit = _applied_audit(tmp_path / "policy.db")
    seal = seal_master_allocation_policy_change(audit=audit)

    assert seal.read_only is True
    assert seal.dynamic_allocation_enabled is False
    assert seal.policy_mutation_authority is False
    assert seal.reservation_authority is False
    assert seal.risk_authority is False
    assert seal.admission_authority is False
    assert seal.registry_mutation is False
    assert seal.broker_authority is False
    assert seal.live_authority is False
    assert seal.auto_execute is False


def test_closure_is_deterministic(tmp_path: Path) -> None:
    *_, audit = _applied_audit(tmp_path / "policy.db")
    first = seal_master_allocation_policy_change(audit=audit)
    second = seal_master_allocation_policy_change(audit=audit)

    assert first == second
    assert first.closure_fingerprint_sha256 == stable_digest(
        master_allocation_policy_change_closure_payload(first)
    )


def test_cas_conflict_lifecycle_can_be_verified_and_sealed(tmp_path: Path) -> None:
    *_, receipt, audit = _conflict_audit(tmp_path / "policy.db")
    seal = seal_master_allocation_policy_change(audit=audit)

    assert receipt.status is MasterAllocationPolicyReplacementStatus.CAS_CONFLICT
    assert audit.status is MasterAllocationPolicyChangeAuditStatus.VERIFIED
    assert audit.policy_change_applied is False
    assert seal.status is MasterAllocationPolicyChangeClosureStatus.SEALED
    assert seal.policy_change_applied is False


def test_cas_conflict_audit_proves_attempt_left_observed_policy_active(tmp_path: Path) -> None:
    store, _base, _candidate, _authorization, _preflight, receipt, audit = _conflict_audit(
        tmp_path / "policy.db"
    )
    active = store.snapshot()

    assert receipt.policy_mutation_performed is False
    assert audit.active_policy_id == active.policy_id
    assert audit.active_policy_fingerprint_sha256 == active.fingerprint_sha256
    assert audit.active_policy_id == receipt.observed_policy_id_at_mutation


def test_in_memory_store_cannot_close_durable_lifecycle() -> None:
    state, base, candidate, authorization, preflight, receipt = _apply()

    with pytest.raises(ValueError, match="durable policy store"):
        audit_master_allocation_policy_change(
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            receipt=receipt,
            store=state,
            store_ref="memory-only",
            audited_at=AUDIT_TIME,
        )


def test_audit_requires_multi_process_safe_store(tmp_path: Path) -> None:
    store, base, candidate, authorization, preflight, receipt = _persistent_apply(
        tmp_path / "policy.db"
    )

    class UnsafeWrapper:
        durable = True
        multi_process_safe = False
        multi_host_safe = False
        live_ready = False

        def snapshot(self):
            return store.snapshot()

    with pytest.raises(ValueError, match="multi-process-safe"):
        audit_master_allocation_policy_change(
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            receipt=receipt,
            store=UnsafeWrapper(),
            store_ref=STORE_REF,
            audited_at=AUDIT_TIME,
        )


def test_audit_is_read_only_and_never_calls_compare_and_swap(tmp_path: Path) -> None:
    store, base, candidate, authorization, preflight, receipt = _persistent_apply(
        tmp_path / "policy.db"
    )

    class SnapshotOnlyGuard:
        durable = True
        multi_process_safe = True
        multi_host_safe = False
        live_ready = False

        def snapshot(self):
            return store.snapshot()

        def compare_and_swap(self, **_kwargs):
            raise AssertionError("audit must not mutate policy store")

    audit = audit_master_allocation_policy_change(
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base,
        receipt=receipt,
        store=SnapshotOnlyGuard(),
        store_ref=STORE_REF,
        audited_at=AUDIT_TIME,
    )

    assert audit.status is MasterAllocationPolicyChangeAuditStatus.VERIFIED


def test_audit_fails_if_persisted_policy_changed_after_applied_receipt(tmp_path: Path) -> None:
    store, base, candidate, authorization, preflight, receipt = _persistent_apply(
        tmp_path / "policy.db"
    )
    active = store.snapshot()
    later = build_master_allocation_policy(
        master_portfolio_id=base.master_portfolio_id,
        policy_id="later-policy",
        members=base.members,
        envelopes=base.envelopes,
        source_ref="operator-policy:later",
    )
    outcome = store.compare_and_swap(
        expected_master_portfolio_id=base.master_portfolio_id,
        expected_policy_id=active.policy_id,
        expected_fingerprint_sha256=active.fingerprint_sha256,
        replacement_policy=later,
    )
    assert outcome.swapped is True

    with pytest.raises(ValueError, match="persisted applied policy mismatch"):
        audit_master_allocation_policy_change(
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            receipt=receipt,
            store=store,
            store_ref=STORE_REF,
            audited_at=AUDIT_TIME,
        )


def test_audit_fails_if_conflict_policy_changed_after_receipt(tmp_path: Path) -> None:
    store, base, candidate, authorization, preflight, receipt = _conflict_bundle(
        tmp_path / "policy.db"
    )
    active = store.snapshot()
    later = build_master_allocation_policy(
        master_portfolio_id=base.master_portfolio_id,
        policy_id="later-policy",
        members=base.members,
        envelopes=base.envelopes,
        source_ref="operator-policy:later",
    )
    outcome = store.compare_and_swap(
        expected_master_portfolio_id=base.master_portfolio_id,
        expected_policy_id=active.policy_id,
        expected_fingerprint_sha256=active.fingerprint_sha256,
        replacement_policy=later,
    )
    assert outcome.swapped is True

    with pytest.raises(ValueError, match="active policy ID changed"):
        audit_master_allocation_policy_change(
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            receipt=receipt,
            store=store,
            store_ref=STORE_REF,
            audited_at=AUDIT_TIME,
        )


def test_audit_rejects_blank_store_ref(tmp_path: Path) -> None:
    store, base, candidate, authorization, preflight, receipt = _persistent_apply(
        tmp_path / "policy.db"
    )

    with pytest.raises(ValueError, match="store_ref"):
        audit_master_allocation_policy_change(
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            receipt=receipt,
            store=store,
            store_ref="  ",
            audited_at=AUDIT_TIME,
        )


def test_audit_cannot_predate_replacement_attempt(tmp_path: Path) -> None:
    store, base, candidate, authorization, preflight, receipt = _persistent_apply(
        tmp_path / "policy.db"
    )

    with pytest.raises(ValueError, match="cannot predate"):
        audit_master_allocation_policy_change(
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            receipt=receipt,
            store=store,
            store_ref=STORE_REF,
            audited_at=APPLY_TIME.replace(minute=APPLY_TIME.minute - 1),
        )


def test_candidate_fingerprint_tampering_fails_closed(tmp_path: Path) -> None:
    store, base, candidate, authorization, preflight, receipt = _persistent_apply(
        tmp_path / "policy.db"
    )
    forged = _tamper(candidate, fingerprint_sha256="0" * 64)

    with pytest.raises(ValueError, match="candidate fingerprint"):
        audit_master_allocation_policy_change(
            candidate=forged,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            receipt=receipt,
            store=store,
            store_ref=STORE_REF,
            audited_at=AUDIT_TIME,
        )


def test_authorization_fingerprint_tampering_fails_closed(tmp_path: Path) -> None:
    store, base, candidate, authorization, preflight, receipt = _persistent_apply(
        tmp_path / "policy.db"
    )
    forged = _tamper(authorization, fingerprint_sha256="0" * 64)

    with pytest.raises(ValueError, match="authorization fingerprint"):
        audit_master_allocation_policy_change(
            candidate=candidate,
            authorization=forged,
            preflight=preflight,
            base_allocation_policy=base,
            receipt=receipt,
            store=store,
            store_ref=STORE_REF,
            audited_at=AUDIT_TIME,
        )


def test_preflight_fingerprint_tampering_fails_closed(tmp_path: Path) -> None:
    store, base, candidate, authorization, preflight, receipt = _persistent_apply(
        tmp_path / "policy.db"
    )
    forged = _tamper(preflight, fingerprint_sha256="0" * 64)

    with pytest.raises(ValueError, match="preflight fingerprint"):
        audit_master_allocation_policy_change(
            candidate=candidate,
            authorization=authorization,
            preflight=forged,
            base_allocation_policy=base,
            receipt=receipt,
            store=store,
            store_ref=STORE_REF,
            audited_at=AUDIT_TIME,
        )


def test_receipt_fingerprint_tampering_fails_closed(tmp_path: Path) -> None:
    store, base, candidate, authorization, preflight, receipt = _persistent_apply(
        tmp_path / "policy.db"
    )
    forged = _tamper(receipt, fingerprint_sha256="0" * 64)

    with pytest.raises(ValueError, match="receipt fingerprint"):
        audit_master_allocation_policy_change(
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            receipt=forged,
            store=store,
            store_ref=STORE_REF,
            audited_at=AUDIT_TIME,
        )


def test_forged_conflict_requested_policy_fingerprint_fails_closed(tmp_path: Path) -> None:
    store, base, candidate, authorization, preflight, receipt = _conflict_bundle(
        tmp_path / "policy.db"
    )
    forged = _tamper(receipt, requested_new_policy_fingerprint_sha256="0" * 64)
    object.__setattr__(
        forged,
        "fingerprint_sha256",
        stable_digest(master_allocation_policy_replacement_receipt_payload(forged)),
    )

    with pytest.raises(ValueError, match="requested replacement fingerprint mismatch"):
        audit_master_allocation_policy_change(
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            receipt=forged,
            store=store,
            store_ref=STORE_REF,
            audited_at=AUDIT_TIME,
        )


def test_audit_dataclass_rejects_false_verification_flag(tmp_path: Path) -> None:
    *_, audit = _applied_audit(tmp_path / "policy.db")
    values = dict(audit.__dict__) if hasattr(audit, "__dict__") else {
        field: getattr(audit, field)
        for field in audit.__dataclass_fields__
        if getattr(audit.__dataclass_fields__[field], "init", False)
    }
    values["candidate_verified"] = False

    with pytest.raises(ValueError, match="verification flags"):
        MasterAllocationPolicyChangeAuditReport(**values)


def test_closure_rejects_tampered_audit_fingerprint(tmp_path: Path) -> None:
    *_, audit = _applied_audit(tmp_path / "policy.db")
    forged = _tamper(audit, fingerprint_sha256="0" * 64)

    with pytest.raises(ValueError, match="audit fingerprint"):
        seal_master_allocation_policy_change(audit=forged)


def test_closure_contract_rejects_bad_fingerprint(tmp_path: Path) -> None:
    *_, audit = _applied_audit(tmp_path / "policy.db")
    seal = seal_master_allocation_policy_change(audit=audit)
    values = {
        field: getattr(seal, field)
        for field in seal.__dataclass_fields__
        if getattr(seal.__dataclass_fields__[field], "init", False)
    }
    values["closure_fingerprint_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="closure fingerprint"):
        MasterAllocationPolicyChangeClosureSeal(**values)


def test_step5_public_exports_are_available() -> None:
    assert MasterAllocationPolicyChangeAuditReport is not None
    assert MasterAllocationPolicyChangeClosureSeal is not None
    assert callable(audit_master_allocation_policy_change)
    assert callable(seal_master_allocation_policy_change)
