from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .allocation_policy_change_closure import (
    MasterAllocationPolicyChangeClosureSeal,
    MasterAllocationPolicyChangeClosureStatus,
    master_allocation_policy_change_closure_payload,
)


class MasterAllocationReadinessEvidenceKind(StrEnum):
    HISTORICAL_OOS = "HISTORICAL_OOS"
    WALK_FORWARD_OOS = "WALK_FORWARD_OOS"
    PAPER = "PAPER"
    SHADOW = "SHADOW"


class MasterAllocationReadinessEvidenceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"
    NOT_PROVIDED = "NOT_PROVIDED"


class MasterAllocationInfrastructureStatus(StrEnum):
    COMPLETE = "COMPLETE"


class MasterAllocationDynamicStatus(StrEnum):
    DISABLED = "DISABLED"


class MasterAllocationMultiCrewLiveReadinessStatus(StrEnum):
    BLOCKED = "BLOCKED"


class MasterAllocationReadinessReasonCode(StrEnum):
    POLICY_STORE_NOT_MULTI_HOST_SAFE = "POLICY_STORE_NOT_MULTI_HOST_SAFE"
    POLICY_STORE_NOT_LIVE_READY = "POLICY_STORE_NOT_LIVE_READY"
    BATCH15_LIVE_BOUNDARY_SINGLE_SYSTEM_ONLY = "BATCH15_LIVE_BOUNDARY_SINGLE_SYSTEM_ONLY"
    HISTORICAL_OOS_EVIDENCE_NOT_AVAILABLE = "HISTORICAL_OOS_EVIDENCE_NOT_AVAILABLE"
    WALK_FORWARD_OOS_EVIDENCE_NOT_AVAILABLE = "WALK_FORWARD_OOS_EVIDENCE_NOT_AVAILABLE"
    PAPER_EVIDENCE_NOT_AVAILABLE = "PAPER_EVIDENCE_NOT_AVAILABLE"
    SHADOW_EVIDENCE_NOT_AVAILABLE = "SHADOW_EVIDENCE_NOT_AVAILABLE"


class MasterAllocationBatch21gClosureStatus(StrEnum):
    SEALED = "SEALED"


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


def master_allocation_readiness_evidence_payload(
    evidence: MasterAllocationReadinessEvidence,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-readiness-evidence.v1",
        "schema_version": evidence.schema_version,
        "kind": evidence.kind,
        "status": evidence.status,
        "source_ref": evidence.source_ref,
        "artifact_fingerprint_sha256": evidence.artifact_fingerprint_sha256,
        "reason_code": evidence.reason_code,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationReadinessEvidence:
    """Explicit external evidence reference; availability is not a quality verdict."""

    kind: MasterAllocationReadinessEvidenceKind
    status: MasterAllocationReadinessEvidenceStatus
    source_ref: str | None
    artifact_fingerprint_sha256: str | None
    reason_code: str | None
    fingerprint_sha256: str
    evidence_reference_only: bool = field(default=True, init=False)
    policy_mutation_authority: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_ref",
            _optional_text(self.source_ref, field_name="source_ref"),
        )
        object.__setattr__(
            self,
            "reason_code",
            _optional_text(self.reason_code, field_name="reason_code"),
        )
        if self.artifact_fingerprint_sha256 is not None:
            object.__setattr__(
                self,
                "artifact_fingerprint_sha256",
                _sha256(
                    self.artifact_fingerprint_sha256,
                    field_name="artifact_fingerprint_sha256",
                ),
            )
        if self.status is MasterAllocationReadinessEvidenceStatus.AVAILABLE:
            if self.source_ref is None or self.artifact_fingerprint_sha256 is None:
                raise ValueError("AVAILABLE readiness evidence requires source and fingerprint")
            if self.reason_code is not None:
                raise ValueError("AVAILABLE readiness evidence cannot carry reason_code")
        elif self.status is MasterAllocationReadinessEvidenceStatus.BLOCKED:
            if self.source_ref is None or self.artifact_fingerprint_sha256 is None:
                raise ValueError("BLOCKED readiness evidence requires source and fingerprint")
            if self.reason_code is None:
                raise ValueError("BLOCKED readiness evidence requires reason_code")
        elif self.status is MasterAllocationReadinessEvidenceStatus.NOT_PROVIDED:
            if self.source_ref is not None or self.artifact_fingerprint_sha256 is not None:
                raise ValueError("NOT_PROVIDED readiness evidence cannot carry artifact provenance")
            if self.reason_code is None:
                raise ValueError("NOT_PROVIDED readiness evidence requires reason_code")
        else:
            raise ValueError("unsupported readiness evidence status")
        if self.schema_version != "1.0":
            raise ValueError("unsupported readiness evidence schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        if normalized != stable_digest(master_allocation_readiness_evidence_payload(self)):
            raise ValueError("readiness evidence fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_readiness_evidence_payload(self)


def build_master_allocation_readiness_evidence(
    *,
    kind: MasterAllocationReadinessEvidenceKind,
    status: MasterAllocationReadinessEvidenceStatus,
    source_ref: str | None = None,
    artifact_fingerprint_sha256: str | None = None,
    reason_code: str | None = None,
) -> MasterAllocationReadinessEvidence:
    provisional = MasterAllocationReadinessEvidence.__new__(MasterAllocationReadinessEvidence)
    values = {
        "kind": kind,
        "status": status,
        "source_ref": source_ref,
        "artifact_fingerprint_sha256": artifact_fingerprint_sha256,
        "reason_code": reason_code,
    }
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterAllocationReadinessEvidence(
        **values,
        fingerprint_sha256=stable_digest(
            master_allocation_readiness_evidence_payload(provisional)
        ),
    )


def _ordered_evidence(
    evidence: tuple[MasterAllocationReadinessEvidence, ...],
) -> tuple[MasterAllocationReadinessEvidence, ...]:
    expected = tuple(MasterAllocationReadinessEvidenceKind)
    if len(evidence) != len(expected):
        raise ValueError("readiness assessment requires exactly one record per evidence kind")
    ordered = tuple(sorted(evidence, key=lambda item: item.kind.value))
    kinds = tuple(item.kind for item in ordered)
    if set(kinds) != set(expected) or len(set(kinds)) != len(kinds):
        raise ValueError("readiness assessment evidence kinds must be complete and unique")
    for item in ordered:
        if stable_digest(master_allocation_readiness_evidence_payload(item)) != (
            item.fingerprint_sha256
        ):
            raise ValueError("readiness assessment evidence fingerprint integrity failure")
    return ordered


def _evidence_blocker(
    kind: MasterAllocationReadinessEvidenceKind,
) -> MasterAllocationReadinessReasonCode:
    mapping = {
        MasterAllocationReadinessEvidenceKind.HISTORICAL_OOS: (
            MasterAllocationReadinessReasonCode.HISTORICAL_OOS_EVIDENCE_NOT_AVAILABLE
        ),
        MasterAllocationReadinessEvidenceKind.WALK_FORWARD_OOS: (
            MasterAllocationReadinessReasonCode.WALK_FORWARD_OOS_EVIDENCE_NOT_AVAILABLE
        ),
        MasterAllocationReadinessEvidenceKind.PAPER: (
            MasterAllocationReadinessReasonCode.PAPER_EVIDENCE_NOT_AVAILABLE
        ),
        MasterAllocationReadinessEvidenceKind.SHADOW: (
            MasterAllocationReadinessReasonCode.SHADOW_EVIDENCE_NOT_AVAILABLE
        ),
    }
    return mapping[kind]


def _blocker_codes(
    *,
    policy_change_closure: MasterAllocationPolicyChangeClosureSeal,
    evidence: tuple[MasterAllocationReadinessEvidence, ...],
) -> tuple[MasterAllocationReadinessReasonCode, ...]:
    reasons = {
        MasterAllocationReadinessReasonCode.BATCH15_LIVE_BOUNDARY_SINGLE_SYSTEM_ONLY,
    }
    if not policy_change_closure.store_multi_host_safe:
        reasons.add(MasterAllocationReadinessReasonCode.POLICY_STORE_NOT_MULTI_HOST_SAFE)
    if not policy_change_closure.store_live_ready:
        reasons.add(MasterAllocationReadinessReasonCode.POLICY_STORE_NOT_LIVE_READY)
    for item in evidence:
        if item.status is not MasterAllocationReadinessEvidenceStatus.AVAILABLE:
            reasons.add(_evidence_blocker(item.kind))
    return tuple(sorted(reasons, key=lambda item: item.value))


def master_allocation_readiness_assessment_payload(
    assessment: MasterAllocationReadinessAssessment,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-readiness-assessment.v1",
        "schema_version": assessment.schema_version,
        "assessment_id": assessment.assessment_id,
        "master_portfolio_id": assessment.master_portfolio_id,
        "infrastructure_status": assessment.infrastructure_status,
        "dynamic_allocation_status": assessment.dynamic_allocation_status,
        "multi_crew_live_readiness_status": assessment.multi_crew_live_readiness_status,
        "policy_change_closure_fingerprint_sha256": (
            assessment.policy_change_closure_fingerprint_sha256
        ),
        "active_policy_id": assessment.active_policy_id,
        "active_policy_fingerprint_sha256": assessment.active_policy_fingerprint_sha256,
        "store_ref": assessment.store_ref,
        "store_durable": assessment.store_durable,
        "store_multi_process_safe": assessment.store_multi_process_safe,
        "store_multi_host_safe": assessment.store_multi_host_safe,
        "store_live_ready": assessment.store_live_ready,
        "evidence_fingerprints_sha256": assessment.evidence_fingerprints_sha256,
        "blocker_codes": assessment.blocker_codes,
        "assessed_at": assessment.assessed_at,
        "step5_closure_verified": assessment.step5_closure_verified,
        "evidence_inventory_explicit": assessment.evidence_inventory_explicit,
        "batch15_live_preflight_preserved": assessment.batch15_live_preflight_preserved,
        "operator_arm_still_required": assessment.operator_arm_still_required,
        "no_live_activation_performed": assessment.no_live_activation_performed,
        "no_dynamic_allocation_enabled": assessment.no_dynamic_allocation_enabled,
        "no_trading_authority_verified": assessment.no_trading_authority_verified,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationReadinessAssessment:
    """Read-only assessment that cannot authorize LIVE or dynamic allocation."""

    assessment_id: str
    master_portfolio_id: str
    infrastructure_status: MasterAllocationInfrastructureStatus
    dynamic_allocation_status: MasterAllocationDynamicStatus
    multi_crew_live_readiness_status: MasterAllocationMultiCrewLiveReadinessStatus
    policy_change_closure_fingerprint_sha256: str
    active_policy_id: str
    active_policy_fingerprint_sha256: str
    store_ref: str
    store_durable: bool
    store_multi_process_safe: bool
    store_multi_host_safe: bool
    store_live_ready: bool
    evidence: tuple[MasterAllocationReadinessEvidence, ...]
    evidence_fingerprints_sha256: tuple[str, ...]
    blocker_codes: tuple[MasterAllocationReadinessReasonCode, ...]
    assessed_at: datetime
    step5_closure_verified: bool
    evidence_inventory_explicit: bool
    batch15_live_preflight_preserved: bool
    operator_arm_still_required: bool
    no_live_activation_performed: bool
    no_dynamic_allocation_enabled: bool
    no_trading_authority_verified: bool
    fingerprint_sha256: str
    assessment_only: bool = field(default=True, init=False)
    read_only: bool = field(default=True, init=False)
    policy_mutation_authority: bool = field(default=False, init=False)
    reservation_authority: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("assessment_id", "master_portfolio_id", "active_policy_id", "store_ref"):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        for name in (
            "policy_change_closure_fingerprint_sha256",
            "active_policy_fingerprint_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), field_name=name))
        ordered = _ordered_evidence(self.evidence)
        object.__setattr__(self, "evidence", ordered)
        expected_fingerprints = tuple(item.fingerprint_sha256 for item in ordered)
        normalized_fingerprints = tuple(
            _sha256(value, field_name="evidence_fingerprints_sha256")
            for value in self.evidence_fingerprints_sha256
        )
        if normalized_fingerprints != expected_fingerprints:
            raise ValueError("readiness assessment evidence fingerprint list mismatch")
        object.__setattr__(self, "evidence_fingerprints_sha256", normalized_fingerprints)
        ordered_blockers = tuple(sorted(self.blocker_codes, key=lambda item: item.value))
        if self.blocker_codes != ordered_blockers or len(set(self.blocker_codes)) != len(
            self.blocker_codes
        ):
            raise ValueError("readiness assessment blocker codes must be sorted and unique")
        object.__setattr__(self, "assessed_at", _utc(self.assessed_at, field_name="assessed_at"))
        if self.infrastructure_status is not MasterAllocationInfrastructureStatus.COMPLETE:
            raise ValueError("Batch 21g infrastructure status must be COMPLETE")
        if self.dynamic_allocation_status is not MasterAllocationDynamicStatus.DISABLED:
            raise ValueError("Batch 21g dynamic allocation must remain DISABLED")
        if self.multi_crew_live_readiness_status is not (
            MasterAllocationMultiCrewLiveReadinessStatus.BLOCKED
        ):
            raise ValueError("Batch 21g multi-crew LIVE readiness must remain BLOCKED")
        if MasterAllocationReadinessReasonCode.BATCH15_LIVE_BOUNDARY_SINGLE_SYSTEM_ONLY not in (
            self.blocker_codes
        ):
            raise ValueError("readiness assessment must preserve Batch 15 single-system blocker")
        verification_flags = (
            self.step5_closure_verified,
            self.evidence_inventory_explicit,
            self.batch15_live_preflight_preserved,
            self.operator_arm_still_required,
            self.no_live_activation_performed,
            self.no_dynamic_allocation_enabled,
            self.no_trading_authority_verified,
        )
        if not all(verification_flags):
            raise ValueError("readiness assessment requires every safety verification flag")
        if not self.store_durable or not self.store_multi_process_safe:
            raise ValueError("readiness assessment requires durable multi-process policy storage")
        if self.store_multi_host_safe and (
            MasterAllocationReadinessReasonCode.POLICY_STORE_NOT_MULTI_HOST_SAFE
            in self.blocker_codes
        ):
            raise ValueError("multi-host-safe store cannot carry multi-host blocker")
        if not self.store_multi_host_safe and (
            MasterAllocationReadinessReasonCode.POLICY_STORE_NOT_MULTI_HOST_SAFE
            not in self.blocker_codes
        ):
            raise ValueError("non-multi-host store requires multi-host blocker")
        if self.store_live_ready and (
            MasterAllocationReadinessReasonCode.POLICY_STORE_NOT_LIVE_READY in self.blocker_codes
        ):
            raise ValueError("LIVE-ready store cannot carry store LIVE-readiness blocker")
        if not self.store_live_ready and (
            MasterAllocationReadinessReasonCode.POLICY_STORE_NOT_LIVE_READY
            not in self.blocker_codes
        ):
            raise ValueError("non-LIVE-ready store requires store LIVE-readiness blocker")
        for item in ordered:
            blocker = _evidence_blocker(item.kind)
            if item.status is MasterAllocationReadinessEvidenceStatus.AVAILABLE:
                if blocker in self.blocker_codes:
                    raise ValueError("available evidence cannot carry availability blocker")
            elif blocker not in self.blocker_codes:
                raise ValueError("unavailable evidence requires availability blocker")
        if self.schema_version != "1.0":
            raise ValueError("unsupported readiness assessment schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        if normalized != stable_digest(master_allocation_readiness_assessment_payload(self)):
            raise ValueError("readiness assessment fingerprint mismatch")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_readiness_assessment_payload(self)


def assess_master_allocation_live_readiness(
    *,
    policy_change_closure: MasterAllocationPolicyChangeClosureSeal,
    evidence: tuple[MasterAllocationReadinessEvidence, ...],
    assessed_at: datetime,
) -> MasterAllocationReadinessAssessment:
    """Assess Batch 21g infrastructure and inventory evidence without granting authority."""

    if stable_digest(master_allocation_policy_change_closure_payload(policy_change_closure)) != (
        policy_change_closure.closure_fingerprint_sha256
    ):
        raise ValueError("readiness assessment Step 5 closure fingerprint integrity failure")
    if policy_change_closure.status is not MasterAllocationPolicyChangeClosureStatus.SEALED:
        raise ValueError("readiness assessment requires SEALED Step 5 closure")
    if not policy_change_closure.lifecycle_closed:
        raise ValueError("readiness assessment requires closed policy-change lifecycle")
    if policy_change_closure.dynamic_allocation_enabled:
        raise ValueError("readiness assessment refuses dynamic allocation already enabled")
    if any(
        (
            policy_change_closure.policy_mutation_authority,
            policy_change_closure.reservation_authority,
            policy_change_closure.risk_authority,
            policy_change_closure.admission_authority,
            policy_change_closure.local_risk_override,
            policy_change_closure.resize_authority,
            policy_change_closure.registry_mutation,
            policy_change_closure.broker_authority,
            policy_change_closure.live_authority,
            policy_change_closure.auto_execute,
        )
    ):
        raise ValueError("readiness assessment Step 5 closure has forbidden authority")
    ordered_evidence = _ordered_evidence(evidence)
    normalized_assessed_at = _utc(assessed_at, field_name="assessed_at")
    if normalized_assessed_at < policy_change_closure.sealed_at:
        raise ValueError("readiness assessment cannot predate Step 5 closure")
    blockers = _blocker_codes(
        policy_change_closure=policy_change_closure,
        evidence=ordered_evidence,
    )
    values = {
        "master_portfolio_id": policy_change_closure.master_portfolio_id,
        "infrastructure_status": MasterAllocationInfrastructureStatus.COMPLETE,
        "dynamic_allocation_status": MasterAllocationDynamicStatus.DISABLED,
        "multi_crew_live_readiness_status": MasterAllocationMultiCrewLiveReadinessStatus.BLOCKED,
        "policy_change_closure_fingerprint_sha256": (
            policy_change_closure.closure_fingerprint_sha256
        ),
        "active_policy_id": policy_change_closure.active_policy_id,
        "active_policy_fingerprint_sha256": (
            policy_change_closure.active_policy_fingerprint_sha256
        ),
        "store_ref": policy_change_closure.store_ref,
        "store_durable": policy_change_closure.store_durable,
        "store_multi_process_safe": policy_change_closure.store_multi_process_safe,
        "store_multi_host_safe": policy_change_closure.store_multi_host_safe,
        "store_live_ready": policy_change_closure.store_live_ready,
        "evidence": ordered_evidence,
        "evidence_fingerprints_sha256": tuple(
            item.fingerprint_sha256 for item in ordered_evidence
        ),
        "blocker_codes": blockers,
        "assessed_at": normalized_assessed_at,
        "step5_closure_verified": True,
        "evidence_inventory_explicit": True,
        "batch15_live_preflight_preserved": True,
        "operator_arm_still_required": True,
        "no_live_activation_performed": True,
        "no_dynamic_allocation_enabled": True,
        "no_trading_authority_verified": True,
    }
    assessment_id = "master-allocation-readiness-assessment:" + stable_digest(
        {"schema": "money-heist.master-allocation-readiness-assessment-id.v1", **values}
    )
    provisional = MasterAllocationReadinessAssessment.__new__(
        MasterAllocationReadinessAssessment
    )
    object.__setattr__(provisional, "assessment_id", assessment_id)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterAllocationReadinessAssessment(
        assessment_id=assessment_id,
        **values,
        fingerprint_sha256=stable_digest(
            master_allocation_readiness_assessment_payload(provisional)
        ),
    )


def master_allocation_batch21g_closure_payload(
    seal: MasterAllocationBatch21gClosureSeal,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-batch21g-closure.v1",
        "schema_version": seal.schema_version,
        "closure_id": seal.closure_id,
        "status": seal.status,
        "master_portfolio_id": seal.master_portfolio_id,
        "readiness_assessment_fingerprint_sha256": (
            seal.readiness_assessment_fingerprint_sha256
        ),
        "policy_change_closure_fingerprint_sha256": (
            seal.policy_change_closure_fingerprint_sha256
        ),
        "infrastructure_status": seal.infrastructure_status,
        "dynamic_allocation_status": seal.dynamic_allocation_status,
        "multi_crew_live_readiness_status": seal.multi_crew_live_readiness_status,
        "blocker_codes": seal.blocker_codes,
        "sealed_at": seal.sealed_at,
    }


@dataclass(frozen=True, slots=True)
class MasterAllocationBatch21gClosureSeal:
    """Final Batch 21g seal; COMPLETE infrastructure does not mean LIVE-ready."""

    closure_id: str
    status: MasterAllocationBatch21gClosureStatus
    master_portfolio_id: str
    readiness_assessment_fingerprint_sha256: str
    policy_change_closure_fingerprint_sha256: str
    infrastructure_status: MasterAllocationInfrastructureStatus
    dynamic_allocation_status: MasterAllocationDynamicStatus
    multi_crew_live_readiness_status: MasterAllocationMultiCrewLiveReadinessStatus
    blocker_codes: tuple[MasterAllocationReadinessReasonCode, ...]
    sealed_at: datetime
    closure_fingerprint_sha256: str
    batch_21g_complete: bool = field(default=True, init=False)
    closure_only: bool = field(default=True, init=False)
    read_only: bool = field(default=True, init=False)
    dynamic_allocation_enabled: bool = field(default=False, init=False)
    multi_crew_live_ready: bool = field(default=False, init=False)
    live_activation_performed: bool = field(default=False, init=False)
    operator_arm_still_required: bool = field(default=True, init=False)
    policy_mutation_authority: bool = field(default=False, init=False)
    reservation_authority: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for name in ("closure_id", "master_portfolio_id"):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), field_name=name),
            )
        for name in (
            "readiness_assessment_fingerprint_sha256",
            "policy_change_closure_fingerprint_sha256",
        ):
            object.__setattr__(self, name, _sha256(getattr(self, name), field_name=name))
        object.__setattr__(self, "sealed_at", _utc(self.sealed_at, field_name="sealed_at"))
        if self.status is not MasterAllocationBatch21gClosureStatus.SEALED:
            raise ValueError("Batch 21g closure status must be SEALED")
        if self.infrastructure_status is not MasterAllocationInfrastructureStatus.COMPLETE:
            raise ValueError("Batch 21g closure requires COMPLETE infrastructure")
        if self.dynamic_allocation_status is not MasterAllocationDynamicStatus.DISABLED:
            raise ValueError("Batch 21g closure requires dynamic allocation DISABLED")
        if self.multi_crew_live_readiness_status is not (
            MasterAllocationMultiCrewLiveReadinessStatus.BLOCKED
        ):
            raise ValueError("Batch 21g closure requires multi-crew LIVE readiness BLOCKED")
        ordered_blockers = tuple(sorted(self.blocker_codes, key=lambda item: item.value))
        if self.blocker_codes != ordered_blockers or len(set(self.blocker_codes)) != len(
            self.blocker_codes
        ):
            raise ValueError("Batch 21g closure blocker codes must be sorted and unique")
        if MasterAllocationReadinessReasonCode.BATCH15_LIVE_BOUNDARY_SINGLE_SYSTEM_ONLY not in (
            self.blocker_codes
        ):
            raise ValueError("Batch 21g closure must preserve Batch 15 single-system blocker")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Batch 21g closure schema_version")
        normalized = _sha256(
            self.closure_fingerprint_sha256,
            field_name="closure_fingerprint_sha256",
        )
        if normalized != stable_digest(master_allocation_batch21g_closure_payload(self)):
            raise ValueError("Batch 21g closure fingerprint mismatch")
        object.__setattr__(self, "closure_fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_allocation_batch21g_closure_payload(self)


def seal_master_allocation_batch21g(
    *,
    assessment: MasterAllocationReadinessAssessment,
) -> MasterAllocationBatch21gClosureSeal:
    """Seal Batch 21g without enabling dynamic allocation or LIVE."""

    if stable_digest(master_allocation_readiness_assessment_payload(assessment)) != (
        assessment.fingerprint_sha256
    ):
        raise ValueError("Batch 21g closure readiness assessment fingerprint integrity failure")
    if assessment.infrastructure_status is not MasterAllocationInfrastructureStatus.COMPLETE:
        raise ValueError("Batch 21g closure requires COMPLETE infrastructure assessment")
    if assessment.dynamic_allocation_status is not MasterAllocationDynamicStatus.DISABLED:
        raise ValueError("Batch 21g closure requires DISABLED dynamic allocation assessment")
    if assessment.multi_crew_live_readiness_status is not (
        MasterAllocationMultiCrewLiveReadinessStatus.BLOCKED
    ):
        raise ValueError("Batch 21g closure requires BLOCKED multi-crew LIVE assessment")
    values = {
        "status": MasterAllocationBatch21gClosureStatus.SEALED,
        "master_portfolio_id": assessment.master_portfolio_id,
        "readiness_assessment_fingerprint_sha256": assessment.fingerprint_sha256,
        "policy_change_closure_fingerprint_sha256": (
            assessment.policy_change_closure_fingerprint_sha256
        ),
        "infrastructure_status": assessment.infrastructure_status,
        "dynamic_allocation_status": assessment.dynamic_allocation_status,
        "multi_crew_live_readiness_status": assessment.multi_crew_live_readiness_status,
        "blocker_codes": assessment.blocker_codes,
        "sealed_at": assessment.assessed_at,
    }
    closure_id = "master-allocation-batch21g-closure:" + stable_digest(
        {"schema": "money-heist.master-allocation-batch21g-closure-id.v1", **values}
    )
    provisional = MasterAllocationBatch21gClosureSeal.__new__(
        MasterAllocationBatch21gClosureSeal
    )
    object.__setattr__(provisional, "closure_id", closure_id)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(provisional, "schema_version", "1.0")
    return MasterAllocationBatch21gClosureSeal(
        closure_id=closure_id,
        **values,
        closure_fingerprint_sha256=stable_digest(
            master_allocation_batch21g_closure_payload(provisional)
        ),
    )


__all__ = [
    "MasterAllocationBatch21gClosureSeal",
    "MasterAllocationBatch21gClosureStatus",
    "MasterAllocationDynamicStatus",
    "MasterAllocationInfrastructureStatus",
    "MasterAllocationMultiCrewLiveReadinessStatus",
    "MasterAllocationReadinessAssessment",
    "MasterAllocationReadinessEvidence",
    "MasterAllocationReadinessEvidenceKind",
    "MasterAllocationReadinessEvidenceStatus",
    "MasterAllocationReadinessReasonCode",
    "assess_master_allocation_live_readiness",
    "build_master_allocation_readiness_evidence",
    "master_allocation_batch21g_closure_payload",
    "master_allocation_readiness_assessment_payload",
    "master_allocation_readiness_evidence_payload",
    "seal_master_allocation_batch21g",
]
