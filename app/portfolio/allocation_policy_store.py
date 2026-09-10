from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol, runtime_checkable

from .allocation import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    MasterAllocationPolicy,
    master_allocation_policy_fingerprint,
)
from .models import PortfolioMemberRef


def _required_text(value: object, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _sha256(value: str, *, field_name: str) -> str:
    normalized = str(value).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
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


def _validate_policy_integrity(policy: MasterAllocationPolicy, *, context: str) -> None:
    if _policy_fingerprint(policy) != policy.fingerprint_sha256:
        raise ValueError(f"{context} policy fingerprint integrity failure")


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _policy_storage_payload(policy: MasterAllocationPolicy) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-policy-store-record.v1",
        "master_portfolio_id": policy.master_portfolio_id,
        "policy_id": policy.policy_id,
        "members": [member.canonical_payload() for member in policy.members],
        "envelopes": [
            {
                "system_id": envelope.system_id,
                "status": envelope.status.value,
                "capital_ceiling_amount": _decimal_text(envelope.capital_ceiling_amount),
                "open_risk_ceiling_amount": _decimal_text(envelope.open_risk_ceiling_amount),
                "gross_exposure_ceiling_amount": _decimal_text(
                    envelope.gross_exposure_ceiling_amount
                ),
                "reason_code": envelope.reason_code,
            }
            for envelope in policy.envelopes
        ],
        "status": policy.status.value,
        "reason_codes": list(policy.reason_codes),
        "fingerprint_sha256": policy.fingerprint_sha256,
        "source_ref": policy.source_ref,
        "schema_version": policy.schema_version,
    }


def _serialize_policy(policy: MasterAllocationPolicy) -> str:
    _validate_policy_integrity(policy, context="persistent store serialization")
    return json.dumps(
        _policy_storage_payload(policy),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _decimal(value: object, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be stored as decimal text")
    return Decimal(value)


def _deserialize_policy(serialized: str) -> MasterAllocationPolicy:
    try:
        payload = json.loads(serialized)
    except json.JSONDecodeError as exc:
        raise ValueError("persistent allocation policy payload is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("persistent allocation policy payload must be an object")
    if payload.get("schema") != "money-heist.master-allocation-policy-store-record.v1":
        raise ValueError("unsupported persistent allocation policy record schema")
    members_raw = payload.get("members")
    envelopes_raw = payload.get("envelopes")
    if not isinstance(members_raw, list) or not isinstance(envelopes_raw, list):
        raise ValueError("persistent allocation policy members/envelopes must be lists")
    members = tuple(
        PortfolioMemberRef(
            system_id=_required_text(item["system_id"], field_name="member.system_id"),
            membership_ref=item.get("membership_ref"),
        )
        for item in members_raw
        if isinstance(item, dict)
    )
    if len(members) != len(members_raw):
        raise ValueError("persistent allocation policy member record is invalid")
    envelopes = tuple(
        CrewAllocationEnvelope(
            system_id=_required_text(item["system_id"], field_name="envelope.system_id"),
            status=AllocationEnvelopeStatus(item["status"]),
            capital_ceiling_amount=_decimal(
                item.get("capital_ceiling_amount"),
                field_name="capital_ceiling_amount",
            ),
            open_risk_ceiling_amount=_decimal(
                item.get("open_risk_ceiling_amount"),
                field_name="open_risk_ceiling_amount",
            ),
            gross_exposure_ceiling_amount=_decimal(
                item.get("gross_exposure_ceiling_amount"),
                field_name="gross_exposure_ceiling_amount",
            ),
            reason_code=item.get("reason_code"),
        )
        for item in envelopes_raw
        if isinstance(item, dict)
    )
    if len(envelopes) != len(envelopes_raw):
        raise ValueError("persistent allocation policy envelope record is invalid")
    reason_codes_raw = payload.get("reason_codes")
    if not isinstance(reason_codes_raw, list) or any(
        not isinstance(item, str) for item in reason_codes_raw
    ):
        raise ValueError("persistent allocation policy reason_codes must be text")
    policy = MasterAllocationPolicy(
        master_portfolio_id=_required_text(
            payload.get("master_portfolio_id"),
            field_name="master_portfolio_id",
        ),
        policy_id=_required_text(payload.get("policy_id"), field_name="policy_id"),
        members=members,
        envelopes=envelopes,
        status=AllocationEnvelopeStatus(payload.get("status")),
        reason_codes=tuple(reason_codes_raw),
        fingerprint_sha256=_sha256(
            str(payload.get("fingerprint_sha256")),
            field_name="fingerprint_sha256",
        ),
        source_ref=payload.get("source_ref"),
        schema_version=_required_text(
            payload.get("schema_version"),
            field_name="schema_version",
        ),
    )
    _validate_policy_integrity(policy, context="persistent store deserialization")
    return policy


@dataclass(frozen=True, slots=True)
class MasterAllocationPolicyAtomicSwapOutcome:
    swapped: bool
    observed_policy: MasterAllocationPolicy
    active_policy: MasterAllocationPolicy


@runtime_checkable
class MasterAllocationPolicyAtomicStore(Protocol):
    """Minimal state port required by the allocation-policy CAS mutation boundary."""

    in_process_only: bool
    durable: bool
    multi_process_safe: bool
    multi_host_safe: bool
    live_ready: bool

    def snapshot(self) -> MasterAllocationPolicy:
        """Return one integrity-validated active allocation policy."""

    def compare_and_swap(
        self,
        *,
        expected_master_portfolio_id: str,
        expected_policy_id: str,
        expected_fingerprint_sha256: str,
        replacement_policy: MasterAllocationPolicy,
    ) -> MasterAllocationPolicyAtomicSwapOutcome:
        """Atomically replace only if the exact expected policy is still active."""


class SQLiteMasterAllocationPolicyStore:
    """Durable local-file CAS adapter for one Master Portfolio allocation policy."""

    in_process_only = False
    durable = True
    multi_process_safe = True
    multi_host_safe = False
    live_ready = False
    policy_storage_only = True
    reservation_authority = False
    risk_authority = False
    admission_authority = False
    registry_mutation = False
    broker_authority = False
    live_authority = False
    auto_execute = False

    def __init__(
        self,
        *,
        database_path: str | Path,
        master_portfolio_id: str,
        initial_policy: MasterAllocationPolicy | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._database_path = Path(database_path)
        self._master_portfolio_id = _required_text(
            master_portfolio_id,
            field_name="master_portfolio_id",
        )
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        self._timeout_seconds = float(timeout_seconds)
        if initial_policy is not None:
            _validate_policy_integrity(initial_policy, context="persistent store initial")
            if initial_policy.master_portfolio_id != self._master_portfolio_id:
                raise ValueError("persistent store initial policy Master Portfolio mismatch")
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()
        if initial_policy is not None:
            self._bootstrap_if_absent(initial_policy)

    @property
    def database_path(self) -> Path:
        return self._database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            timeout=self._timeout_seconds,
            isolation_level=None,
        )
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS master_allocation_policy_state (
                    master_portfolio_id TEXT PRIMARY KEY NOT NULL,
                    policy_id TEXT NOT NULL,
                    fingerprint_sha256 TEXT NOT NULL,
                    policy_json TEXT NOT NULL
                )
                """
            )

    def _bootstrap_if_absent(self, policy: MasterAllocationPolicy) -> None:
        serialized = _serialize_policy(policy)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT policy_id, fingerprint_sha256, policy_json
                FROM master_allocation_policy_state
                WHERE master_portfolio_id = ?
                """,
                (self._master_portfolio_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO master_allocation_policy_state (
                        master_portfolio_id, policy_id, fingerprint_sha256, policy_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        self._master_portfolio_id,
                        policy.policy_id,
                        policy.fingerprint_sha256,
                        serialized,
                    ),
                )
                connection.execute("COMMIT")
                return
            stored = self._policy_from_row(row)
            if stored != policy:
                connection.execute("ROLLBACK")
                raise ValueError(
                    "persistent store is already initialized with a different active policy"
                )
            connection.execute("COMMIT")

    def _policy_from_row(self, row: tuple[object, ...]) -> MasterAllocationPolicy:
        if len(row) != 3:
            raise ValueError("persistent allocation policy row shape mismatch")
        policy_id, fingerprint, policy_json = row
        if not all(isinstance(item, str) for item in row):
            raise ValueError("persistent allocation policy row contains invalid values")
        policy = _deserialize_policy(policy_json)
        if policy.master_portfolio_id != self._master_portfolio_id:
            raise ValueError("persistent allocation policy Master Portfolio mismatch")
        if policy.policy_id != policy_id or policy.fingerprint_sha256 != fingerprint:
            raise ValueError("persistent allocation policy row metadata mismatch")
        return policy

    def snapshot(self) -> MasterAllocationPolicy:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT policy_id, fingerprint_sha256, policy_json
                FROM master_allocation_policy_state
                WHERE master_portfolio_id = ?
                """,
                (self._master_portfolio_id,),
            ).fetchone()
        if row is None:
            raise ValueError("persistent allocation policy store is not initialized")
        return self._policy_from_row(row)

    def compare_and_swap(
        self,
        *,
        expected_master_portfolio_id: str,
        expected_policy_id: str,
        expected_fingerprint_sha256: str,
        replacement_policy: MasterAllocationPolicy,
    ) -> MasterAllocationPolicyAtomicSwapOutcome:
        expected_master = _required_text(
            expected_master_portfolio_id,
            field_name="expected_master_portfolio_id",
        )
        expected_id = _required_text(expected_policy_id, field_name="expected_policy_id")
        expected_fingerprint = _sha256(
            expected_fingerprint_sha256,
            field_name="expected_fingerprint_sha256",
        )
        if expected_master != self._master_portfolio_id:
            raise ValueError("persistent CAS expected Master Portfolio mismatch")
        _validate_policy_integrity(replacement_policy, context="persistent CAS replacement")
        if replacement_policy.master_portfolio_id != expected_master:
            raise ValueError("persistent CAS replacement Master Portfolio mismatch")
        replacement_json = _serialize_policy(replacement_policy)

        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT policy_id, fingerprint_sha256, policy_json
                    FROM master_allocation_policy_state
                    WHERE master_portfolio_id = ?
                    """,
                    (self._master_portfolio_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("persistent allocation policy store is not initialized")
                observed = self._policy_from_row(row)
                matches = (
                    observed.policy_id == expected_id
                    and observed.fingerprint_sha256 == expected_fingerprint
                )
                if not matches:
                    connection.execute("COMMIT")
                    return MasterAllocationPolicyAtomicSwapOutcome(
                        swapped=False,
                        observed_policy=observed,
                        active_policy=observed,
                    )
                if tuple(member.system_id for member in observed.members) != tuple(
                    member.system_id for member in replacement_policy.members
                ):
                    raise ValueError("persistent CAS replacement cannot change membership")
                cursor = connection.execute(
                    """
                    UPDATE master_allocation_policy_state
                    SET policy_id = ?, fingerprint_sha256 = ?, policy_json = ?
                    WHERE master_portfolio_id = ?
                      AND policy_id = ?
                      AND fingerprint_sha256 = ?
                    """,
                    (
                        replacement_policy.policy_id,
                        replacement_policy.fingerprint_sha256,
                        replacement_json,
                        self._master_portfolio_id,
                        expected_id,
                        expected_fingerprint,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "persistent allocation policy CAS lost transaction ownership"
                    )
                connection.execute("COMMIT")
                return MasterAllocationPolicyAtomicSwapOutcome(
                    swapped=True,
                    observed_policy=observed,
                    active_policy=replacement_policy,
                )
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise


__all__ = [
    "MasterAllocationPolicyAtomicStore",
    "MasterAllocationPolicyAtomicSwapOutcome",
    "SQLiteMasterAllocationPolicyStore",
]
