from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .models import PortfolioMemberRef


class AllocationEnvelopeStatus(StrEnum):
    CONFIGURED = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class AllocationPolicySource(StrEnum):
    OPERATOR_CONFIGURATION = "OPERATOR_CONFIGURATION"


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
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


def _non_negative_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


@dataclass(frozen=True, slots=True)
class CrewAllocationEnvelope:
    """Operator-owned static ceilings for one crew; this is not transferred cash."""

    system_id: str
    status: AllocationEnvelopeStatus
    capital_ceiling_amount: Decimal | None = None
    open_risk_ceiling_amount: Decimal | None = None
    gross_exposure_ceiling_amount: Decimal | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        object.__setattr__(
            self,
            "reason_code",
            _optional_text(self.reason_code, field_name="reason_code"),
        )
        ceilings = {
            "capital_ceiling_amount": self.capital_ceiling_amount,
            "open_risk_ceiling_amount": self.open_risk_ceiling_amount,
            "gross_exposure_ceiling_amount": self.gross_exposure_ceiling_amount,
        }

        if self.status is AllocationEnvelopeStatus.CONFIGURED:
            if any(value is None for value in ceilings.values()):
                raise ValueError("CONFIGURED allocation envelope requires every ceiling")
            if self.reason_code is not None:
                raise ValueError("CONFIGURED allocation envelope cannot carry reason_code")
            for field_name, value in ceilings.items():
                assert value is not None
                _non_negative_decimal(value, field_name=field_name)
            return

        if self.status is not AllocationEnvelopeStatus.NOT_CONFIGURED:
            raise ValueError(f"unsupported allocation envelope status: {self.status}")
        if any(value is not None for value in ceilings.values()):
            raise ValueError("NOT_CONFIGURED allocation envelope cannot carry numeric ceilings")
        if self.reason_code is None:
            raise ValueError("NOT_CONFIGURED allocation envelope requires reason_code")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "system_id": self.system_id,
            "status": self.status,
            "capital_ceiling_amount": self.capital_ceiling_amount,
            "open_risk_ceiling_amount": self.open_risk_ceiling_amount,
            "gross_exposure_ceiling_amount": self.gross_exposure_ceiling_amount,
            "reason_code": self.reason_code,
        }


def _policy_reason_codes(
    envelopes: tuple[CrewAllocationEnvelope, ...],
) -> tuple[str, ...]:
    reasons = []
    for envelope in envelopes:
        if envelope.status is AllocationEnvelopeStatus.NOT_CONFIGURED:
            assert envelope.reason_code is not None
            reasons.append(
                f"ALLOCATION_ENVELOPE_NOT_CONFIGURED:{envelope.system_id}:{envelope.reason_code}"
            )
    return tuple(sorted(reasons))


def master_allocation_policy_payload(
    *,
    master_portfolio_id: str,
    policy_id: str,
    members: tuple[PortfolioMemberRef, ...],
    envelopes: tuple[CrewAllocationEnvelope, ...],
    status: AllocationEnvelopeStatus,
    reason_codes: tuple[str, ...],
    source: AllocationPolicySource,
    source_ref: str | None,
    schema_version: str,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-allocation-policy.v1",
        "schema_version": schema_version,
        "master_portfolio_id": master_portfolio_id,
        "policy_id": policy_id,
        "members": [member.canonical_payload() for member in members],
        "envelopes": [envelope.canonical_payload() for envelope in envelopes],
        "status": status,
        "reason_codes": reason_codes,
        "source": source,
        "source_ref": source_ref,
    }


def master_allocation_policy_fingerprint(
    *,
    master_portfolio_id: str,
    policy_id: str,
    members: tuple[PortfolioMemberRef, ...],
    envelopes: tuple[CrewAllocationEnvelope, ...],
    status: AllocationEnvelopeStatus,
    reason_codes: tuple[str, ...],
    source: AllocationPolicySource,
    source_ref: str | None,
    schema_version: str,
) -> str:
    return stable_digest(
        master_allocation_policy_payload(
            master_portfolio_id=master_portfolio_id,
            policy_id=policy_id,
            members=members,
            envelopes=envelopes,
            status=status,
            reason_codes=reason_codes,
            source=source,
            source_ref=source_ref,
            schema_version=schema_version,
        )
    )


@dataclass(frozen=True, slots=True)
class MasterAllocationPolicy:
    """Static operator policy. It grants no reservation, Risk, execution, or LIVE authority."""

    master_portfolio_id: str
    policy_id: str
    members: tuple[PortfolioMemberRef, ...]
    envelopes: tuple[CrewAllocationEnvelope, ...]
    status: AllocationEnvelopeStatus
    reason_codes: tuple[str, ...]
    fingerprint_sha256: str
    source_ref: str | None = None
    source: AllocationPolicySource = field(
        default=AllocationPolicySource.OPERATOR_CONFIGURATION,
        init=False,
    )
    auto_apply: bool = field(default=False, init=False)
    dynamic_allocation: bool = field(default=False, init=False)
    reservation_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "master_portfolio_id",
            _required_text(self.master_portfolio_id, field_name="master_portfolio_id"),
        )
        object.__setattr__(
            self,
            "policy_id",
            _required_text(self.policy_id, field_name="policy_id"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _optional_text(self.source_ref, field_name="source_ref"),
        )
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master allocation policy schema_version")
        if not self.members:
            raise ValueError("Master allocation policy requires at least one member")

        member_ids = tuple(member.system_id for member in self.members)
        envelope_ids = tuple(envelope.system_id for envelope in self.envelopes)
        if member_ids != tuple(sorted(member_ids)):
            raise ValueError("allocation policy members must be sorted by system_id")
        if envelope_ids != tuple(sorted(envelope_ids)):
            raise ValueError("allocation envelopes must be sorted by system_id")
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("allocation policy member system_id values must be unique")
        if len(set(envelope_ids)) != len(envelope_ids):
            raise ValueError("allocation envelope system_id values must be unique")
        if set(member_ids) != set(envelope_ids):
            raise ValueError("every allocation policy member requires exactly one envelope")

        expected_status = (
            AllocationEnvelopeStatus.CONFIGURED
            if all(
                envelope.status is AllocationEnvelopeStatus.CONFIGURED
                for envelope in self.envelopes
            )
            else AllocationEnvelopeStatus.NOT_CONFIGURED
        )
        if self.status is not expected_status:
            raise ValueError("allocation policy status does not match envelope configuration")
        expected_reasons = _policy_reason_codes(self.envelopes)
        if self.reason_codes != expected_reasons:
            raise ValueError("allocation policy reason_codes do not match envelopes")

        normalized_fingerprint = self.fingerprint_sha256.lower()
        if len(normalized_fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in normalized_fingerprint
        ):
            raise ValueError("fingerprint_sha256 must be a SHA-256 hex digest")
        object.__setattr__(self, "fingerprint_sha256", normalized_fingerprint)

        expected_fingerprint = master_allocation_policy_fingerprint(
            master_portfolio_id=self.master_portfolio_id,
            policy_id=self.policy_id,
            members=self.members,
            envelopes=self.envelopes,
            status=self.status,
            reason_codes=self.reason_codes,
            source=self.source,
            source_ref=self.source_ref,
            schema_version=self.schema_version,
        )
        if self.fingerprint_sha256 != expected_fingerprint:
            raise ValueError("Master allocation policy fingerprint does not match payload")


def build_master_allocation_policy(
    *,
    master_portfolio_id: str,
    policy_id: str,
    members: tuple[PortfolioMemberRef, ...],
    envelopes: tuple[CrewAllocationEnvelope, ...],
    source_ref: str | None = None,
) -> MasterAllocationPolicy:
    """Build one canonical static policy without normalizing ceilings into allocations."""

    normalized_master_id = _required_text(
        master_portfolio_id,
        field_name="master_portfolio_id",
    )
    normalized_policy_id = _required_text(policy_id, field_name="policy_id")
    normalized_source_ref = _optional_text(source_ref, field_name="source_ref")
    ordered_members = tuple(sorted(members, key=lambda item: item.system_id))
    ordered_envelopes = tuple(sorted(envelopes, key=lambda item: item.system_id))

    if not ordered_members:
        raise ValueError("Master allocation policy requires at least one member")
    member_ids = tuple(member.system_id for member in ordered_members)
    envelope_ids = tuple(envelope.system_id for envelope in ordered_envelopes)
    if len(set(member_ids)) != len(member_ids):
        raise ValueError("allocation policy member system_id values must be unique")
    if len(set(envelope_ids)) != len(envelope_ids):
        raise ValueError("allocation envelope system_id values must be unique")
    if set(member_ids) != set(envelope_ids):
        raise ValueError("every allocation policy member requires exactly one envelope")

    status = (
        AllocationEnvelopeStatus.CONFIGURED
        if all(
            envelope.status is AllocationEnvelopeStatus.CONFIGURED
            for envelope in ordered_envelopes
        )
        else AllocationEnvelopeStatus.NOT_CONFIGURED
    )
    reason_codes = _policy_reason_codes(ordered_envelopes)
    source = AllocationPolicySource.OPERATOR_CONFIGURATION
    fingerprint = master_allocation_policy_fingerprint(
        master_portfolio_id=normalized_master_id,
        policy_id=normalized_policy_id,
        members=ordered_members,
        envelopes=ordered_envelopes,
        status=status,
        reason_codes=reason_codes,
        source=source,
        source_ref=normalized_source_ref,
        schema_version="1.0",
    )
    return MasterAllocationPolicy(
        master_portfolio_id=normalized_master_id,
        policy_id=normalized_policy_id,
        members=ordered_members,
        envelopes=ordered_envelopes,
        status=status,
        reason_codes=reason_codes,
        fingerprint_sha256=fingerprint,
        source_ref=normalized_source_ref,
    )


__all__ = [
    "AllocationEnvelopeStatus",
    "AllocationPolicySource",
    "CrewAllocationEnvelope",
    "MasterAllocationPolicy",
    "build_master_allocation_policy",
    "master_allocation_policy_fingerprint",
    "master_allocation_policy_payload",
]
