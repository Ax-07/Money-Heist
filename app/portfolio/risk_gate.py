from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.services.backtest.ids import stable_digest
from app.trading.risk.models import RiskDecision, RiskDecisionStatus, RiskReasonCode

ZERO = Decimal("0")
_LOCAL_AUTHORIZED = {RiskDecisionStatus.APPROVED, RiskDecisionStatus.RESIZED}


class MasterRiskGatePolicyStatus(StrEnum):
    CONFIGURED = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class MasterRiskGatePolicySource(StrEnum):
    OPERATOR_CONFIGURATION = "OPERATOR_CONFIGURATION"


class MasterRiskGateDecisionStatus(StrEnum):
    ADMIT = "ADMIT"
    REJECT = "REJECT"


class MasterRiskGateReasonCode(StrEnum):
    ADMITTED = "ADMITTED"
    LOCAL_RISK_NOT_AUTHORIZED = "LOCAL_RISK_NOT_AUTHORIZED"
    GATE_POLICY_NOT_CONFIGURED = "GATE_POLICY_NOT_CONFIGURED"
    MASTER_PORTFOLIO_ID_MISMATCH = "MASTER_PORTFOLIO_ID_MISMATCH"
    SYSTEM_NOT_MEMBER = "SYSTEM_NOT_MEMBER"
    ALLOCATION_POLICY_MISMATCH = "ALLOCATION_POLICY_MISMATCH"
    LEDGER_POLICY_MISMATCH = "LEDGER_POLICY_MISMATCH"
    PORTFOLIO_SNAPSHOT_UNAVAILABLE = "PORTFOLIO_SNAPSHOT_UNAVAILABLE"
    RESERVATION_NOT_FOUND = "RESERVATION_NOT_FOUND"
    RESERVATION_NOT_RESERVED = "RESERVATION_NOT_RESERVED"
    RESERVATION_PAYLOAD_MISMATCH = "RESERVATION_PAYLOAD_MISMATCH"
    MASTER_OPEN_RISK_LIMIT_EXCEEDED = "MASTER_OPEN_RISK_LIMIT_EXCEEDED"
    MASTER_GROSS_EXPOSURE_LIMIT_EXCEEDED = "MASTER_GROSS_EXPOSURE_LIMIT_EXCEEDED"


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


def _sha256(value: str, *, field_name: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return normalized


def _non_negative_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if not value.is_finite() or value < ZERO:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _unique_reason_codes[T](values: tuple[T, ...], *, field_name: str) -> tuple[T, ...]:
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


def master_risk_gate_policy_payload(
    *,
    master_portfolio_id: str,
    gate_policy_id: str,
    allocation_policy_fingerprint_sha256: str,
    status: MasterRiskGatePolicyStatus,
    max_total_open_risk_amount: Decimal | None,
    max_total_gross_exposure_amount: Decimal | None,
    reason_code: str | None,
    source: MasterRiskGatePolicySource,
    source_ref: str | None,
    schema_version: str,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-risk-gate-policy.v1",
        "schema_version": schema_version,
        "master_portfolio_id": master_portfolio_id,
        "gate_policy_id": gate_policy_id,
        "allocation_policy_fingerprint_sha256": allocation_policy_fingerprint_sha256,
        "status": status,
        "max_total_open_risk_amount": max_total_open_risk_amount,
        "max_total_gross_exposure_amount": max_total_gross_exposure_amount,
        "reason_code": reason_code,
        "source": source,
        "source_ref": source_ref,
    }


def master_risk_gate_policy_fingerprint(**kwargs: object) -> str:
    return stable_digest(master_risk_gate_policy_payload(**kwargs))


@dataclass(frozen=True, slots=True)
class MasterRiskGatePolicy:
    """Operator-owned global ceilings. Local Risk remains the trade-risk authority."""

    master_portfolio_id: str
    gate_policy_id: str
    allocation_policy_fingerprint_sha256: str
    status: MasterRiskGatePolicyStatus
    fingerprint_sha256: str
    max_total_open_risk_amount: Decimal | None = None
    max_total_gross_exposure_amount: Decimal | None = None
    reason_code: str | None = None
    source_ref: str | None = None
    source: MasterRiskGatePolicySource = field(
        default=MasterRiskGatePolicySource.OPERATOR_CONFIGURATION,
        init=False,
    )
    veto_only: bool = field(default=True, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_authority: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "master_portfolio_id",
            _required_text(self.master_portfolio_id, field_name="master_portfolio_id"),
        )
        object.__setattr__(
            self,
            "gate_policy_id",
            _required_text(self.gate_policy_id, field_name="gate_policy_id"),
        )
        object.__setattr__(
            self,
            "allocation_policy_fingerprint_sha256",
            _sha256(
                self.allocation_policy_fingerprint_sha256,
                field_name="allocation_policy_fingerprint_sha256",
            ),
        )
        object.__setattr__(
            self,
            "reason_code",
            _optional_text(self.reason_code, field_name="reason_code"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _optional_text(self.source_ref, field_name="source_ref"),
        )
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Risk Gate policy schema_version")

        limits = {
            "max_total_open_risk_amount": self.max_total_open_risk_amount,
            "max_total_gross_exposure_amount": self.max_total_gross_exposure_amount,
        }
        if self.status is MasterRiskGatePolicyStatus.CONFIGURED:
            if any(value is None for value in limits.values()):
                raise ValueError("CONFIGURED Master Risk Gate policy requires every global limit")
            if self.reason_code is not None:
                raise ValueError("CONFIGURED Master Risk Gate policy cannot carry reason_code")
            assert self.max_total_open_risk_amount is not None
            assert self.max_total_gross_exposure_amount is not None
            _non_negative_decimal(
                self.max_total_open_risk_amount,
                field_name="max_total_open_risk_amount",
            )
            _non_negative_decimal(
                self.max_total_gross_exposure_amount,
                field_name="max_total_gross_exposure_amount",
            )
        elif self.status is MasterRiskGatePolicyStatus.NOT_CONFIGURED:
            if any(value is not None for value in limits.values()):
                raise ValueError("NOT_CONFIGURED Master Risk Gate policy cannot carry limits")
            if self.reason_code is None:
                raise ValueError("NOT_CONFIGURED Master Risk Gate policy requires reason_code")
        else:
            raise ValueError(f"unsupported Master Risk Gate policy status: {self.status}")

        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_risk_gate_policy_fingerprint(
            master_portfolio_id=self.master_portfolio_id,
            gate_policy_id=self.gate_policy_id,
            allocation_policy_fingerprint_sha256=self.allocation_policy_fingerprint_sha256,
            status=self.status,
            max_total_open_risk_amount=self.max_total_open_risk_amount,
            max_total_gross_exposure_amount=self.max_total_gross_exposure_amount,
            reason_code=self.reason_code,
            source=self.source,
            source_ref=self.source_ref,
            schema_version=self.schema_version,
        )
        if normalized != expected:
            raise ValueError("Master Risk Gate policy fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def build_master_risk_gate_policy(
    *,
    master_portfolio_id: str,
    gate_policy_id: str,
    allocation_policy_fingerprint_sha256: str,
    max_total_open_risk_amount: Decimal | None = None,
    max_total_gross_exposure_amount: Decimal | None = None,
    reason_code: str | None = None,
    source_ref: str | None = None,
) -> MasterRiskGatePolicy:
    normalized_master_id = _required_text(
        master_portfolio_id,
        field_name="master_portfolio_id",
    )
    normalized_gate_id = _required_text(gate_policy_id, field_name="gate_policy_id")
    normalized_allocation_fingerprint = _sha256(
        allocation_policy_fingerprint_sha256,
        field_name="allocation_policy_fingerprint_sha256",
    )
    normalized_reason = _optional_text(reason_code, field_name="reason_code")
    normalized_source_ref = _optional_text(source_ref, field_name="source_ref")
    limits = (
        max_total_open_risk_amount,
        max_total_gross_exposure_amount,
    )
    if all(value is not None for value in limits):
        status = MasterRiskGatePolicyStatus.CONFIGURED
        assert max_total_open_risk_amount is not None
        assert max_total_gross_exposure_amount is not None
        _non_negative_decimal(
            max_total_open_risk_amount,
            field_name="max_total_open_risk_amount",
        )
        _non_negative_decimal(
            max_total_gross_exposure_amount,
            field_name="max_total_gross_exposure_amount",
        )
        if normalized_reason is not None:
            raise ValueError("CONFIGURED Master Risk Gate policy cannot carry reason_code")
    elif all(value is None for value in limits):
        status = MasterRiskGatePolicyStatus.NOT_CONFIGURED
        if normalized_reason is None:
            raise ValueError("NOT_CONFIGURED Master Risk Gate policy requires reason_code")
    else:
        raise ValueError("Master Risk Gate global limits must be all configured or all absent")
    source = MasterRiskGatePolicySource.OPERATOR_CONFIGURATION
    fingerprint = master_risk_gate_policy_fingerprint(
        master_portfolio_id=normalized_master_id,
        gate_policy_id=normalized_gate_id,
        allocation_policy_fingerprint_sha256=normalized_allocation_fingerprint,
        status=status,
        max_total_open_risk_amount=max_total_open_risk_amount,
        max_total_gross_exposure_amount=max_total_gross_exposure_amount,
        reason_code=normalized_reason,
        source=source,
        source_ref=normalized_source_ref,
        schema_version="1.0",
    )
    return MasterRiskGatePolicy(
        master_portfolio_id=normalized_master_id,
        gate_policy_id=normalized_gate_id,
        allocation_policy_fingerprint_sha256=normalized_allocation_fingerprint,
        status=status,
        fingerprint_sha256=fingerprint,
        max_total_open_risk_amount=max_total_open_risk_amount,
        max_total_gross_exposure_amount=max_total_gross_exposure_amount,
        reason_code=normalized_reason,
        source_ref=normalized_source_ref,
    )


def local_risk_decision_payload(*, system_id: str, decision: RiskDecision) -> dict[str, object]:
    return {
        "schema": "money-heist.local-risk-decision-binding.v1",
        "system_id": system_id,
        "proposal_id": decision.proposal_id,
        "status": decision.status,
        "reason_codes": decision.reason_codes,
        "approved_quantity": decision.approved_quantity,
        "approved_risk_amount": decision.approved_risk_amount,
        "approved_notional": decision.approved_notional,
        "created_at": decision.created_at,
        "details": decision.details,
    }


def local_risk_decision_fingerprint(*, system_id: str, decision: RiskDecision) -> str:
    return stable_digest(local_risk_decision_payload(system_id=system_id, decision=decision))


def master_risk_gate_candidate_payload(candidate: MasterRiskGateCandidate) -> dict[str, object]:
    return {
        "schema": "money-heist.master-risk-gate-candidate.v1",
        "schema_version": candidate.schema_version,
        "master_portfolio_id": candidate.master_portfolio_id,
        "system_id": candidate.system_id,
        "proposal_id": candidate.proposal_id,
        "reservation_id": candidate.reservation_id,
        "local_risk_status": candidate.local_risk_status,
        "local_risk_reason_codes": candidate.local_risk_reason_codes,
        "local_approved_quantity": candidate.local_approved_quantity,
        "local_approved_risk_amount": candidate.local_approved_risk_amount,
        "local_approved_notional": candidate.local_approved_notional,
        "local_risk_created_at": candidate.local_risk_created_at,
        "local_risk_decision_fingerprint_sha256": (
            candidate.local_risk_decision_fingerprint_sha256
        ),
    }


def master_risk_gate_candidate_fingerprint(candidate: MasterRiskGateCandidate) -> str:
    return stable_digest(master_risk_gate_candidate_payload(candidate))


@dataclass(frozen=True, slots=True)
class MasterRiskGateCandidate:
    """Immutable binding of one local Risk decision to one Master reservation context."""

    master_portfolio_id: str
    system_id: str
    proposal_id: str
    reservation_id: str | None
    local_risk_status: RiskDecisionStatus
    local_risk_reason_codes: tuple[RiskReasonCode, ...]
    local_approved_quantity: Decimal
    local_approved_risk_amount: Decimal
    local_approved_notional: Decimal
    local_risk_created_at: datetime
    local_risk_decision_fingerprint_sha256: str
    fingerprint_sha256: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "master_portfolio_id",
            _required_text(self.master_portfolio_id, field_name="master_portfolio_id"),
        )
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        object.__setattr__(
            self,
            "proposal_id",
            _required_text(self.proposal_id, field_name="proposal_id"),
        )
        object.__setattr__(
            self,
            "reservation_id",
            _optional_text(self.reservation_id, field_name="reservation_id"),
        )
        object.__setattr__(
            self,
            "local_risk_created_at",
            _utc(self.local_risk_created_at, field_name="local_risk_created_at"),
        )
        _unique_reason_codes(
            self.local_risk_reason_codes,
            field_name="local_risk_reason_codes",
        )
        for field_name in (
            "local_approved_quantity",
            "local_approved_risk_amount",
            "local_approved_notional",
        ):
            _non_negative_decimal(getattr(self, field_name), field_name=field_name)

        if self.local_risk_status in _LOCAL_AUTHORIZED:
            if self.reservation_id is None:
                raise ValueError("locally authorized candidate requires reservation_id")
        elif self.local_risk_status is RiskDecisionStatus.REJECTED:
            if self.reservation_id is not None:
                raise ValueError("locally rejected candidate cannot carry reservation_id")
            if any(
                value != ZERO
                for value in (
                    self.local_approved_quantity,
                    self.local_approved_risk_amount,
                    self.local_approved_notional,
                )
            ):
                raise ValueError("locally rejected candidate cannot carry approved amounts")
        else:
            raise ValueError(f"unsupported local Risk status: {self.local_risk_status}")

        object.__setattr__(
            self,
            "local_risk_decision_fingerprint_sha256",
            _sha256(
                self.local_risk_decision_fingerprint_sha256,
                field_name="local_risk_decision_fingerprint_sha256",
            ),
        )
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Risk Gate candidate schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_risk_gate_candidate_fingerprint(self)
        if normalized != expected:
            raise ValueError("Master Risk Gate candidate fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    @property
    def local_risk_authorized(self) -> bool:
        return self.local_risk_status in _LOCAL_AUTHORIZED


def build_master_risk_gate_candidate(
    *,
    master_portfolio_id: str,
    system_id: str,
    local_risk_decision: RiskDecision,
    reservation_id: str | None,
) -> MasterRiskGateCandidate:
    normalized_master_id = _required_text(
        master_portfolio_id,
        field_name="master_portfolio_id",
    )
    normalized_system_id = _required_text(system_id, field_name="system_id")
    normalized_reservation_id = _optional_text(reservation_id, field_name="reservation_id")
    normalized_created_at = _utc(local_risk_decision.created_at, field_name="created_at")
    local_fingerprint = local_risk_decision_fingerprint(
        system_id=normalized_system_id,
        decision=local_risk_decision,
    )
    payload = {
        "schema": "money-heist.master-risk-gate-candidate.v1",
        "schema_version": "1.0",
        "master_portfolio_id": normalized_master_id,
        "system_id": normalized_system_id,
        "proposal_id": local_risk_decision.proposal_id,
        "reservation_id": normalized_reservation_id,
        "local_risk_status": local_risk_decision.status,
        "local_risk_reason_codes": local_risk_decision.reason_codes,
        "local_approved_quantity": local_risk_decision.approved_quantity,
        "local_approved_risk_amount": local_risk_decision.approved_risk_amount,
        "local_approved_notional": local_risk_decision.approved_notional,
        "local_risk_created_at": normalized_created_at,
        "local_risk_decision_fingerprint_sha256": local_fingerprint,
    }
    return MasterRiskGateCandidate(
        master_portfolio_id=normalized_master_id,
        system_id=normalized_system_id,
        proposal_id=local_risk_decision.proposal_id,
        reservation_id=normalized_reservation_id,
        local_risk_status=local_risk_decision.status,
        local_risk_reason_codes=local_risk_decision.reason_codes,
        local_approved_quantity=local_risk_decision.approved_quantity,
        local_approved_risk_amount=local_risk_decision.approved_risk_amount,
        local_approved_notional=local_risk_decision.approved_notional,
        local_risk_created_at=normalized_created_at,
        local_risk_decision_fingerprint_sha256=local_fingerprint,
        fingerprint_sha256=stable_digest(payload),
    )


def master_risk_gate_decision_payload(decision: MasterRiskGateDecision) -> dict[str, object]:
    return {
        "schema": "money-heist.master-risk-gate-decision.v1",
        "schema_version": decision.schema_version,
        "decision_id": decision.decision_id,
        "candidate_fingerprint_sha256": decision.candidate_fingerprint_sha256,
        "local_risk_decision_fingerprint_sha256": (
            decision.local_risk_decision_fingerprint_sha256
        ),
        "gate_policy_fingerprint_sha256": decision.gate_policy_fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": (
            decision.portfolio_snapshot_fingerprint_sha256
        ),
        "reservation_ledger_fingerprint_sha256": (
            decision.reservation_ledger_fingerprint_sha256
        ),
        "local_risk_status": decision.local_risk_status,
        "local_approved_quantity": decision.local_approved_quantity,
        "local_approved_risk_amount": decision.local_approved_risk_amount,
        "local_approved_notional": decision.local_approved_notional,
        "status": decision.status,
        "reason_codes": decision.reason_codes,
        "admitted_quantity": decision.admitted_quantity,
        "admitted_risk_amount": decision.admitted_risk_amount,
        "admitted_notional": decision.admitted_notional,
        "created_at": decision.created_at,
    }


def master_risk_gate_decision_fingerprint(decision: MasterRiskGateDecision) -> str:
    return stable_digest(master_risk_gate_decision_payload(decision))


@dataclass(frozen=True, slots=True)
class MasterRiskGateDecision:
    """Veto-only portfolio admission. It can never resize or override local Risk."""

    decision_id: str
    candidate_fingerprint_sha256: str
    local_risk_decision_fingerprint_sha256: str
    gate_policy_fingerprint_sha256: str
    portfolio_snapshot_fingerprint_sha256: str
    reservation_ledger_fingerprint_sha256: str
    local_risk_status: RiskDecisionStatus
    local_approved_quantity: Decimal
    local_approved_risk_amount: Decimal
    local_approved_notional: Decimal
    status: MasterRiskGateDecisionStatus
    reason_codes: tuple[MasterRiskGateReasonCode, ...]
    admitted_quantity: Decimal
    admitted_risk_amount: Decimal
    admitted_notional: Decimal
    created_at: datetime
    fingerprint_sha256: str
    veto_only: bool = field(default=True, init=False)
    local_risk_override: bool = field(default=False, init=False)
    resize_applied: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=True, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            _required_text(self.decision_id, field_name="decision_id"),
        )
        for field_name in (
            "candidate_fingerprint_sha256",
            "local_risk_decision_fingerprint_sha256",
            "gate_policy_fingerprint_sha256",
            "portfolio_snapshot_fingerprint_sha256",
            "reservation_ledger_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "local_approved_quantity",
            "local_approved_risk_amount",
            "local_approved_notional",
            "admitted_quantity",
            "admitted_risk_amount",
            "admitted_notional",
        ):
            _non_negative_decimal(getattr(self, field_name), field_name=field_name)
        object.__setattr__(self, "created_at", _utc(self.created_at, field_name="created_at"))
        _unique_reason_codes(self.reason_codes, field_name="reason_codes")
        if not self.reason_codes:
            raise ValueError("Master Risk Gate decision requires at least one reason_code")

        if self.status is MasterRiskGateDecisionStatus.ADMIT:
            if self.local_risk_status not in _LOCAL_AUTHORIZED:
                raise ValueError("ADMIT requires an authorized local Risk decision")
            if self.reason_codes != (MasterRiskGateReasonCode.ADMITTED,):
                raise ValueError("ADMIT requires exactly the ADMITTED reason code")
            if (
                self.admitted_quantity != self.local_approved_quantity
                or self.admitted_risk_amount != self.local_approved_risk_amount
                or self.admitted_notional != self.local_approved_notional
            ):
                raise ValueError("Master Risk Gate cannot resize local Risk-approved amounts")
        elif self.status is MasterRiskGateDecisionStatus.REJECT:
            if MasterRiskGateReasonCode.ADMITTED in self.reason_codes:
                raise ValueError("REJECT cannot carry ADMITTED reason code")
            if any(
                value != ZERO
                for value in (
                    self.admitted_quantity,
                    self.admitted_risk_amount,
                    self.admitted_notional,
                )
            ):
                raise ValueError("REJECT cannot carry admitted amounts")
            if (
                self.local_risk_status is RiskDecisionStatus.REJECTED
                and MasterRiskGateReasonCode.LOCAL_RISK_NOT_AUTHORIZED not in self.reason_codes
            ):
                raise ValueError("local Risk rejection must remain explicit in Master rejection")
        else:
            raise ValueError(f"unsupported Master Risk Gate decision status: {self.status}")

        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Risk Gate decision schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_risk_gate_decision_fingerprint(self)
        if normalized != expected:
            raise ValueError("Master Risk Gate decision fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def _build_master_risk_gate_decision(
    *,
    candidate: MasterRiskGateCandidate,
    status: MasterRiskGateDecisionStatus,
    reason_codes: tuple[MasterRiskGateReasonCode, ...],
    gate_policy_fingerprint_sha256: str,
    portfolio_snapshot_fingerprint_sha256: str,
    reservation_ledger_fingerprint_sha256: str,
    created_at: datetime,
) -> MasterRiskGateDecision:
    normalized_created_at = _utc(created_at, field_name="created_at")
    normalized_policy_fingerprint = _sha256(
        gate_policy_fingerprint_sha256,
        field_name="gate_policy_fingerprint_sha256",
    )
    normalized_snapshot_fingerprint = _sha256(
        portfolio_snapshot_fingerprint_sha256,
        field_name="portfolio_snapshot_fingerprint_sha256",
    )
    normalized_ledger_fingerprint = _sha256(
        reservation_ledger_fingerprint_sha256,
        field_name="reservation_ledger_fingerprint_sha256",
    )
    is_admit = status is MasterRiskGateDecisionStatus.ADMIT
    admitted_quantity = candidate.local_approved_quantity if is_admit else ZERO
    admitted_risk = candidate.local_approved_risk_amount if is_admit else ZERO
    admitted_notional = candidate.local_approved_notional if is_admit else ZERO
    decision_id = "master-risk-gate:" + stable_digest(
        {
            "schema": "money-heist.master-risk-gate-decision-id.v1",
            "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
            "gate_policy_fingerprint_sha256": normalized_policy_fingerprint,
            "portfolio_snapshot_fingerprint_sha256": normalized_snapshot_fingerprint,
            "reservation_ledger_fingerprint_sha256": normalized_ledger_fingerprint,
            "status": status,
            "reason_codes": reason_codes,
            "created_at": normalized_created_at,
        }
    )
    payload = {
        "schema": "money-heist.master-risk-gate-decision.v1",
        "schema_version": "1.0",
        "decision_id": decision_id,
        "candidate_fingerprint_sha256": candidate.fingerprint_sha256,
        "local_risk_decision_fingerprint_sha256": (
            candidate.local_risk_decision_fingerprint_sha256
        ),
        "gate_policy_fingerprint_sha256": normalized_policy_fingerprint,
        "portfolio_snapshot_fingerprint_sha256": normalized_snapshot_fingerprint,
        "reservation_ledger_fingerprint_sha256": normalized_ledger_fingerprint,
        "local_risk_status": candidate.local_risk_status,
        "local_approved_quantity": candidate.local_approved_quantity,
        "local_approved_risk_amount": candidate.local_approved_risk_amount,
        "local_approved_notional": candidate.local_approved_notional,
        "status": status,
        "reason_codes": reason_codes,
        "admitted_quantity": admitted_quantity,
        "admitted_risk_amount": admitted_risk,
        "admitted_notional": admitted_notional,
        "created_at": normalized_created_at,
    }
    return MasterRiskGateDecision(
        decision_id=decision_id,
        candidate_fingerprint_sha256=candidate.fingerprint_sha256,
        local_risk_decision_fingerprint_sha256=(
            candidate.local_risk_decision_fingerprint_sha256
        ),
        gate_policy_fingerprint_sha256=normalized_policy_fingerprint,
        portfolio_snapshot_fingerprint_sha256=normalized_snapshot_fingerprint,
        reservation_ledger_fingerprint_sha256=normalized_ledger_fingerprint,
        local_risk_status=candidate.local_risk_status,
        local_approved_quantity=candidate.local_approved_quantity,
        local_approved_risk_amount=candidate.local_approved_risk_amount,
        local_approved_notional=candidate.local_approved_notional,
        status=status,
        reason_codes=reason_codes,
        admitted_quantity=admitted_quantity,
        admitted_risk_amount=admitted_risk,
        admitted_notional=admitted_notional,
        created_at=normalized_created_at,
        fingerprint_sha256=stable_digest(payload),
    )


__all__ = [
    "MasterRiskGateCandidate",
    "MasterRiskGateDecision",
    "MasterRiskGateDecisionStatus",
    "MasterRiskGatePolicy",
    "MasterRiskGatePolicySource",
    "MasterRiskGatePolicyStatus",
    "MasterRiskGateReasonCode",
    "build_master_risk_gate_candidate",
    "build_master_risk_gate_policy",
    "local_risk_decision_fingerprint",
    "master_risk_gate_candidate_fingerprint",
    "master_risk_gate_decision_fingerprint",
    "master_risk_gate_policy_fingerprint",
]
