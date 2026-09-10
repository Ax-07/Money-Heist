from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from app.portfolio.allocation import build_master_allocation_policy
from app.portfolio.allocation_policy_replacement import (
    InMemoryMasterAllocationPolicyAtomicState,
    MasterAllocationPolicyReplacementStatus,
    apply_master_allocation_policy_replacement,
)
from app.portfolio.allocation_policy_store import (
    MasterAllocationPolicyAtomicStore,
    MasterAllocationPolicyAtomicSwapOutcome,
    SQLiteMasterAllocationPolicyStore,
)
from tests.portfolio.test_master_allocation_policy_atomic_replacement import (
    APPLY_TIME,
    _ready_bundle,
)


def _sqlite_store(
    path: Path,
    *,
    initial=True,
) -> SQLiteMasterAllocationPolicyStore:
    policy, _candidate, _authorization, _preflight = _ready_bundle()
    return SQLiteMasterAllocationPolicyStore(
        database_path=path,
        master_portfolio_id=policy.master_portfolio_id,
        initial_policy=policy if initial else None,
    )


def _persistent_apply(path: Path, *, new_policy_id: str = "persistent-policy-v2"):
    base, candidate, authorization, preflight = _ready_bundle()
    store = SQLiteMasterAllocationPolicyStore(
        database_path=path,
        master_portfolio_id=base.master_portfolio_id,
        initial_policy=base,
    )
    receipt = apply_master_allocation_policy_replacement(
        atomic_state=store,
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base,
        new_policy_id=new_policy_id,
        application_source_ref="operator-policy:batch21g-step4-persistent",
        attempted_at=APPLY_TIME,
    )
    return store, base, candidate, authorization, preflight, receipt


def test_in_memory_state_implements_atomic_store_port() -> None:
    base, _candidate, _authorization, _preflight = _ready_bundle()
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    assert isinstance(state, MasterAllocationPolicyAtomicStore)


def test_sqlite_store_implements_atomic_store_port(tmp_path: Path) -> None:
    store = _sqlite_store(tmp_path / "policy.db")

    assert isinstance(store, MasterAllocationPolicyAtomicStore)


def test_sqlite_store_declares_durable_local_scope(tmp_path: Path) -> None:
    store = _sqlite_store(tmp_path / "policy.db")

    assert store.in_process_only is False
    assert store.durable is True
    assert store.multi_process_safe is True
    assert store.multi_host_safe is False
    assert store.live_ready is False


def test_sqlite_store_creates_database_file(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "policy.db"
    _sqlite_store(path)

    assert path.is_file()


def test_snapshot_round_trips_exact_initial_policy(tmp_path: Path) -> None:
    base, _candidate, _authorization, _preflight = _ready_bundle()
    store = _sqlite_store(tmp_path / "policy.db")

    assert store.snapshot() == base


def test_reopen_without_initial_policy_reads_persisted_state(tmp_path: Path) -> None:
    path = tmp_path / "policy.db"
    base, _candidate, _authorization, _preflight = _ready_bundle()
    _sqlite_store(path)
    reopened = SQLiteMasterAllocationPolicyStore(
        database_path=path,
        master_portfolio_id=base.master_portfolio_id,
    )

    assert reopened.snapshot() == base


def test_bootstrap_same_policy_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "policy.db"
    base, _candidate, _authorization, _preflight = _ready_bundle()
    _sqlite_store(path)
    second = SQLiteMasterAllocationPolicyStore(
        database_path=path,
        master_portfolio_id=base.master_portfolio_id,
        initial_policy=base,
    )

    assert second.snapshot() == base


def test_bootstrap_different_policy_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "policy.db"
    base, _candidate, _authorization, _preflight = _ready_bundle()
    _sqlite_store(path)
    different = build_master_allocation_policy(
        master_portfolio_id=base.master_portfolio_id,
        policy_id="different-bootstrap",
        members=base.members,
        envelopes=base.envelopes,
        source_ref="operator-policy:different-bootstrap",
    )

    with pytest.raises(ValueError, match="already initialized"):
        SQLiteMasterAllocationPolicyStore(
            database_path=path,
            master_portfolio_id=base.master_portfolio_id,
            initial_policy=different,
        )


def test_uninitialized_store_fails_closed_on_snapshot(tmp_path: Path) -> None:
    base, _candidate, _authorization, _preflight = _ready_bundle()
    store = SQLiteMasterAllocationPolicyStore(
        database_path=tmp_path / "policy.db",
        master_portfolio_id=base.master_portfolio_id,
    )

    with pytest.raises(ValueError, match="not initialized"):
        store.snapshot()


def test_persistent_store_drives_existing_replacement_boundary(tmp_path: Path) -> None:
    store, _base, candidate, _authorization, _preflight, receipt = _persistent_apply(
        tmp_path / "policy.db"
    )

    assert receipt.status is MasterAllocationPolicyReplacementStatus.APPLIED
    assert store.snapshot().envelopes == candidate.proposed_envelopes


def test_applied_policy_survives_store_reopen(tmp_path: Path) -> None:
    path = tmp_path / "policy.db"
    store, base, _candidate, _authorization, _preflight, receipt = _persistent_apply(path)
    expected = store.snapshot()
    reopened = SQLiteMasterAllocationPolicyStore(
        database_path=path,
        master_portfolio_id=base.master_portfolio_id,
    )

    assert receipt.applied is True
    assert reopened.snapshot() == expected


def test_persistent_replacement_receipt_binds_active_policy(tmp_path: Path) -> None:
    store, _base, _candidate, _authorization, _preflight, receipt = _persistent_apply(
        tmp_path / "policy.db"
    )
    active = store.snapshot()

    assert receipt.active_policy_id_after_attempt == active.policy_id
    assert receipt.active_policy_fingerprint_sha256_after_attempt == active.fingerprint_sha256


def test_second_application_of_same_base_is_cas_conflict(tmp_path: Path) -> None:
    path = tmp_path / "policy.db"
    store, base, candidate, authorization, preflight, first = _persistent_apply(path)
    second = apply_master_allocation_policy_replacement(
        atomic_state=store,
        candidate=candidate,
        authorization=authorization,
        preflight=preflight,
        base_allocation_policy=base,
        new_policy_id="persistent-policy-v3",
        application_source_ref="operator-policy:replay",
        attempted_at=APPLY_TIME,
    )

    assert first.status is MasterAllocationPolicyReplacementStatus.APPLIED
    assert second.status is MasterAllocationPolicyReplacementStatus.CAS_CONFLICT
    assert store.snapshot().policy_id == "persistent-policy-v2"


def test_stale_direct_cas_returns_observed_policy_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "policy.db"
    store, base, _candidate, _authorization, _preflight, _receipt = _persistent_apply(path)
    active = store.snapshot()
    requested = build_master_allocation_policy(
        master_portfolio_id=base.master_portfolio_id,
        policy_id="should-not-apply",
        members=base.members,
        envelopes=base.envelopes,
        source_ref="operator-policy:stale-direct-cas",
    )

    outcome = store.compare_and_swap(
        expected_master_portfolio_id=base.master_portfolio_id,
        expected_policy_id=base.policy_id,
        expected_fingerprint_sha256=base.fingerprint_sha256,
        replacement_policy=requested,
    )

    assert outcome.swapped is False
    assert outcome.observed_policy == active
    assert outcome.active_policy == active
    assert store.snapshot() == active


def test_direct_cas_returns_public_outcome_contract(tmp_path: Path) -> None:
    path = tmp_path / "policy.db"
    base, candidate, _authorization, _preflight = _ready_bundle()
    store = _sqlite_store(path)
    replacement_policy = build_master_allocation_policy(
        master_portfolio_id=base.master_portfolio_id,
        policy_id="direct-policy-v2",
        members=base.members,
        envelopes=candidate.proposed_envelopes,
        source_ref="operator-policy:direct-cas-test",
    )

    outcome = store.compare_and_swap(
        expected_master_portfolio_id=base.master_portfolio_id,
        expected_policy_id=base.policy_id,
        expected_fingerprint_sha256=base.fingerprint_sha256,
        replacement_policy=replacement_policy,
    )

    assert isinstance(outcome, MasterAllocationPolicyAtomicSwapOutcome)
    assert outcome.swapped is True
    assert outcome.observed_policy == base
    assert outcome.active_policy == replacement_policy


def test_two_independent_sqlite_store_instances_allow_one_cas_winner(tmp_path: Path) -> None:
    path = tmp_path / "policy.db"
    base, candidate, authorization, preflight = _ready_bundle()
    first_store = _sqlite_store(path)
    second_store = SQLiteMasterAllocationPolicyStore(
        database_path=path,
        master_portfolio_id=base.master_portfolio_id,
    )

    def attempt(store: SQLiteMasterAllocationPolicyStore, policy_id: str):
        return apply_master_allocation_policy_replacement(
            atomic_state=store,
            candidate=candidate,
            authorization=authorization,
            preflight=preflight,
            base_allocation_policy=base,
            new_policy_id=policy_id,
            application_source_ref=f"operator-policy:{policy_id}",
            attempted_at=APPLY_TIME,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = tuple(
            executor.map(
                lambda item: attempt(*item),
                (
                    (first_store, "persistent-concurrent-a"),
                    (second_store, "persistent-concurrent-b"),
                ),
            )
        )

    statuses = sorted(receipt.status.value for receipt in receipts)
    assert statuses == ["APPLIED", "CAS_CONFLICT"]
    assert first_store.snapshot() == second_store.snapshot()


def test_decimal_ceiling_representation_round_trips(tmp_path: Path) -> None:
    base, _candidate, _authorization, _preflight = _ready_bundle()
    envelopes = tuple(
        replace(
            envelope,
            capital_ceiling_amount=Decimal("123.4500"),
            open_risk_ceiling_amount=Decimal("6.700"),
            gross_exposure_ceiling_amount=Decimal("890.1200"),
        )
        for envelope in base.envelopes
    )
    precise = build_master_allocation_policy(
        master_portfolio_id=base.master_portfolio_id,
        policy_id="decimal-round-trip",
        members=base.members,
        envelopes=envelopes,
        source_ref="operator-policy:decimal-round-trip",
    )
    store = SQLiteMasterAllocationPolicyStore(
        database_path=tmp_path / "policy.db",
        master_portfolio_id=base.master_portfolio_id,
        initial_policy=precise,
    )

    assert store.snapshot() == precise
    assert store.snapshot().fingerprint_sha256 == precise.fingerprint_sha256


def test_corrupt_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "policy.db"
    store = _sqlite_store(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE master_allocation_policy_state SET policy_json = ?",
            ("{not-json",),
        )

    with pytest.raises(ValueError, match="invalid JSON"):
        store.snapshot()


def test_corrupt_row_fingerprint_metadata_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "policy.db"
    store = _sqlite_store(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE master_allocation_policy_state SET fingerprint_sha256 = ?",
            ("0" * 64,),
        )

    with pytest.raises(ValueError, match="row metadata mismatch"):
        store.snapshot()


def test_corrupt_policy_payload_fingerprint_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "policy.db"
    store = _sqlite_store(path)
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT policy_json FROM master_allocation_policy_state"
        ).fetchone()
        assert row is not None
        tampered = row[0].replace('"fingerprint_sha256":"', '"fingerprint_sha256":"0')
        connection.execute(
            "UPDATE master_allocation_policy_state SET policy_json = ?",
            (tampered,),
        )

    with pytest.raises(ValueError, match="SHA-256"):
        store.snapshot()


def test_wrong_master_portfolio_cas_fails_closed(tmp_path: Path) -> None:
    base, candidate, _authorization, _preflight = _ready_bundle()
    store = _sqlite_store(tmp_path / "policy.db")
    replacement_policy = build_master_allocation_policy(
        master_portfolio_id=base.master_portfolio_id,
        policy_id="policy-v2",
        members=base.members,
        envelopes=candidate.proposed_envelopes,
        source_ref="operator-policy:wrong-master-test",
    )

    with pytest.raises(ValueError, match="expected Master Portfolio mismatch"):
        store.compare_and_swap(
            expected_master_portfolio_id="other-master",
            expected_policy_id=base.policy_id,
            expected_fingerprint_sha256=base.fingerprint_sha256,
            replacement_policy=replacement_policy,
        )


def test_replacement_membership_change_fails_closed(tmp_path: Path) -> None:
    base, candidate, _authorization, _preflight = _ready_bundle()
    store = _sqlite_store(tmp_path / "policy.db")
    reduced_members = base.members[:-1]
    reduced_ids = {member.system_id for member in reduced_members}
    reduced_envelopes = tuple(
        envelope for envelope in candidate.proposed_envelopes if envelope.system_id in reduced_ids
    )
    replacement_policy = build_master_allocation_policy(
        master_portfolio_id=base.master_portfolio_id,
        policy_id="membership-change",
        members=reduced_members,
        envelopes=reduced_envelopes,
        source_ref="operator-policy:membership-change",
    )

    with pytest.raises(ValueError, match="cannot change membership"):
        store.compare_and_swap(
            expected_master_portfolio_id=base.master_portfolio_id,
            expected_policy_id=base.policy_id,
            expected_fingerprint_sha256=base.fingerprint_sha256,
            replacement_policy=replacement_policy,
        )


def test_timeout_must_be_positive(tmp_path: Path) -> None:
    base, _candidate, _authorization, _preflight = _ready_bundle()

    with pytest.raises(ValueError, match="timeout_seconds"):
        SQLiteMasterAllocationPolicyStore(
            database_path=tmp_path / "policy.db",
            master_portfolio_id=base.master_portfolio_id,
            initial_policy=base,
            timeout_seconds=0,
        )


def test_persistent_store_does_not_enable_live_or_dynamic_allocation(tmp_path: Path) -> None:
    store, _base, _candidate, _authorization, _preflight, receipt = _persistent_apply(
        tmp_path / "policy.db"
    )

    assert store.live_ready is False
    assert receipt.dynamic_allocation_enabled is False
    assert receipt.live_authority is False
    assert receipt.risk_authority is False
    assert receipt.broker_authority is False


def test_persistent_store_path_is_explicit_operator_owned_input(tmp_path: Path) -> None:
    path = tmp_path / "operator-owned" / "allocation.sqlite3"
    store = _sqlite_store(path)

    assert store.database_path == path


def test_persistent_store_never_sums_or_creates_capital(tmp_path: Path) -> None:
    store, _base, candidate, _authorization, _preflight, _receipt = _persistent_apply(
        tmp_path / "policy.db"
    )

    assert store.snapshot().envelopes == candidate.proposed_envelopes
    assert not hasattr(store, "equity")
    assert not hasattr(store, "cash_balance")


def test_in_memory_state_remains_non_durable_after_port_refactor() -> None:
    base, _candidate, _authorization, _preflight = _ready_bundle()
    state = InMemoryMasterAllocationPolicyAtomicState(base)

    assert state.durable is False
    assert state.multi_process_safe is False
    assert state.multi_host_safe is False
    assert state.live_ready is False
