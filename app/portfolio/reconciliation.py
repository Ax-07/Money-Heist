from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .allocation import MasterAllocationPolicy
from .models import CrewExposureSnapshot, MasterPortfolioSnapshot, SnapshotDataStatus
from .reservation import CrewReservationUsage, ReservationLedgerSnapshot

ZERO = Decimal("0")


class ReservationReconciliationStatus(StrEnum):
    CONSISTENT = "CONSISTENT"
    PENDING = "PENDING"
    INCONSISTENT = "INCONSISTENT"
    UNAVAILABLE = "UNAVAILABLE"


class ReservationReconciliationReasonCode(StrEnum):
    PORTFOLIO_SNAPSHOT_UNAVAILABLE = "PORTFOLIO_SNAPSHOT_UNAVAILABLE"
    MASTER_PORTFOLIO_ID_MISMATCH = "MASTER_PORTFOLIO_ID_MISMATCH"
    POLICY_FINGERPRINT_MISMATCH = "POLICY_FINGERPRINT_MISMATCH"
    MEMBERSHIP_MISMATCH = "MEMBERSHIP_MISMATCH"
    LEDGER_CREW_SET_MISMATCH = "LEDGER_CREW_SET_MISMATCH"
    LEDGER_STATE_AFTER_OBSERVATION = "LEDGER_STATE_AFTER_OBSERVATION"
    CREW_EXPOSURE_UNAVAILABLE = "CREW_EXPOSURE_UNAVAILABLE"
    OBSERVED_OPEN_RISK_EXCEEDS_COMMITTED = "OBSERVED_OPEN_RISK_EXCEEDS_COMMITTED"
    OBSERVED_GROSS_EXPOSURE_EXCEEDS_COMMITTED = (
        "OBSERVED_GROSS_EXPOSURE_EXCEEDS_COMMITTED"
    )
    COMMITTED_OPEN_RISK_NOT_YET_OBSERVED = "COMMITTED_OPEN_RISK_NOT_YET_OBSERVED"
    COMMITTED_GROSS_EXPOSURE_NOT_YET_OBSERVED = (
        "COMMITTED_GROSS_EXPOSURE_NOT_YET_OBSERVED"
    )


def _ordered_unique_reason_codes(
    values: list[ReservationReconciliationReasonCode],
) -> tuple[ReservationReconciliationReasonCode, ...]:
    return tuple(dict.fromkeys(values))


def _comparison_reason_codes(
    *,
    observed_status: SnapshotDataStatus,
    observed_open_risk_amount: Decimal | None,
    committed_open_risk_amount: Decimal,
    observed_gross_exposure_amount: Decimal | None,
    committed_gross_exposure_amount: Decimal,
) -> tuple[ReservationReconciliationReasonCode, ...]:
    if observed_status is SnapshotDataStatus.UNAVAILABLE:
        return (ReservationReconciliationReasonCode.CREW_EXPOSURE_UNAVAILABLE,)

    assert observed_open_risk_amount is not None
    assert observed_gross_exposure_amount is not None
    reasons: list[ReservationReconciliationReasonCode] = []
    if observed_open_risk_amount > committed_open_risk_amount:
        reasons.append(
            ReservationReconciliationReasonCode.OBSERVED_OPEN_RISK_EXCEEDS_COMMITTED
        )
    elif observed_open_risk_amount < committed_open_risk_amount:
        reasons.append(
            ReservationReconciliationReasonCode.COMMITTED_OPEN_RISK_NOT_YET_OBSERVED
        )

    if observed_gross_exposure_amount > committed_gross_exposure_amount:
        reasons.append(
            ReservationReconciliationReasonCode.OBSERVED_GROSS_EXPOSURE_EXCEEDS_COMMITTED
        )
    elif observed_gross_exposure_amount < committed_gross_exposure_amount:
        reasons.append(
            ReservationReconciliationReasonCode.COMMITTED_GROSS_EXPOSURE_NOT_YET_OBSERVED
        )
    return _ordered_unique_reason_codes(reasons)


def _crew_reason_codes(
    *,
    exposure: CrewExposureSnapshot,
    usage: CrewReservationUsage,
) -> tuple[ReservationReconciliationReasonCode, ...]:
    return _comparison_reason_codes(
        observed_status=exposure.status,
        observed_open_risk_amount=exposure.open_risk_amount,
        committed_open_risk_amount=usage.committed_open_risk_amount,
        observed_gross_exposure_amount=exposure.gross_exposure_amount,
        committed_gross_exposure_amount=usage.committed_gross_exposure_amount,
    )


def _crew_status(
    reason_codes: tuple[ReservationReconciliationReasonCode, ...],
) -> ReservationReconciliationStatus:
    if ReservationReconciliationReasonCode.CREW_EXPOSURE_UNAVAILABLE in reason_codes:
        return ReservationReconciliationStatus.UNAVAILABLE
    if any(
        reason in reason_codes
        for reason in (
            ReservationReconciliationReasonCode.OBSERVED_OPEN_RISK_EXCEEDS_COMMITTED,
            ReservationReconciliationReasonCode.OBSERVED_GROSS_EXPOSURE_EXCEEDS_COMMITTED,
        )
    ):
        return ReservationReconciliationStatus.INCONSISTENT
    if reason_codes:
        return ReservationReconciliationStatus.PENDING
    return ReservationReconciliationStatus.CONSISTENT


@dataclass(frozen=True, slots=True)
class CrewReservationReconciliation:
    system_id: str
    status: ReservationReconciliationStatus
    observed_status: SnapshotDataStatus
    observed_open_positions: int | None
    observed_open_risk_amount: Decimal | None
    committed_open_risk_amount: Decimal
    open_risk_delta_amount: Decimal | None
    reserved_open_risk_amount: Decimal
    observed_gross_exposure_amount: Decimal | None
    committed_gross_exposure_amount: Decimal
    gross_exposure_delta_amount: Decimal | None
    reserved_gross_exposure_amount: Decimal
    reserved_capital_amount: Decimal
    committed_capital_amount: Decimal
    reason_codes: tuple[ReservationReconciliationReasonCode, ...]
    fingerprint_sha256: str

    def __post_init__(self) -> None:
        if not self.system_id.strip():
            raise ValueError("system_id must not be blank")
        object.__setattr__(self, "system_id", self.system_id.strip())
        for field_name in (
            "committed_open_risk_amount",
            "reserved_open_risk_amount",
            "committed_gross_exposure_amount",
            "reserved_gross_exposure_amount",
            "reserved_capital_amount",
            "committed_capital_amount",
        ):
            value = getattr(self, field_name)
            if not value.is_finite() or value < ZERO:
                raise ValueError(f"{field_name} must be finite and >= 0")
        if self.observed_status is SnapshotDataStatus.AVAILABLE:
            if self.observed_open_positions is None or self.observed_open_positions < 0:
                raise ValueError("AVAILABLE reconciliation requires open_positions >= 0")
            if self.observed_open_risk_amount is None:
                raise ValueError("AVAILABLE reconciliation requires observed open risk")
            if self.observed_gross_exposure_amount is None:
                raise ValueError("AVAILABLE reconciliation requires observed gross exposure")
            if self.open_risk_delta_amount is None or self.gross_exposure_delta_amount is None:
                raise ValueError("AVAILABLE reconciliation requires comparison deltas")
            for field_name in (
                "observed_open_risk_amount",
                "observed_gross_exposure_amount",
            ):
                value = getattr(self, field_name)
                assert value is not None
                if not value.is_finite() or value < ZERO:
                    raise ValueError(f"{field_name} must be finite and >= 0")
            if self.open_risk_delta_amount != (
                self.observed_open_risk_amount - self.committed_open_risk_amount
            ):
                raise ValueError("open_risk_delta_amount does not match observed - committed")
            if self.gross_exposure_delta_amount != (
                self.observed_gross_exposure_amount - self.committed_gross_exposure_amount
            ):
                raise ValueError(
                    "gross_exposure_delta_amount does not match observed - committed"
                )
        elif self.observed_status is SnapshotDataStatus.UNAVAILABLE:
            if any(
                value is not None
                for value in (
                    self.observed_open_positions,
                    self.observed_open_risk_amount,
                    self.open_risk_delta_amount,
                    self.observed_gross_exposure_amount,
                    self.gross_exposure_delta_amount,
                )
            ):
                raise ValueError("UNAVAILABLE reconciliation cannot invent observed values")
        else:
            raise ValueError(f"unsupported observed status: {self.observed_status}")

        expected_reasons = _comparison_reason_codes(
            observed_status=self.observed_status,
            observed_open_risk_amount=self.observed_open_risk_amount,
            committed_open_risk_amount=self.committed_open_risk_amount,
            observed_gross_exposure_amount=self.observed_gross_exposure_amount,
            committed_gross_exposure_amount=self.committed_gross_exposure_amount,
        )
        if self.reason_codes != expected_reasons:
            raise ValueError("crew reconciliation reason_codes do not match comparison")
        if self.status is not _crew_status(expected_reasons):
            raise ValueError("crew reconciliation status does not match comparison")
        expected = crew_reservation_reconciliation_fingerprint(self)
        normalized = self.fingerprint_sha256.lower()
        if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError("fingerprint_sha256 must be a SHA-256 hex digest")
        if normalized != expected:
            raise ValueError("crew reconciliation fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return crew_reservation_reconciliation_payload(self)


def crew_reservation_reconciliation_payload(
    item: CrewReservationReconciliation,
) -> dict[str, object]:
    return {
        "schema": "money-heist.crew-reservation-reconciliation.v1",
        "system_id": item.system_id,
        "status": item.status,
        "observed_status": item.observed_status,
        "observed_open_positions": item.observed_open_positions,
        "observed_open_risk_amount": item.observed_open_risk_amount,
        "committed_open_risk_amount": item.committed_open_risk_amount,
        "open_risk_delta_amount": item.open_risk_delta_amount,
        "reserved_open_risk_amount": item.reserved_open_risk_amount,
        "observed_gross_exposure_amount": item.observed_gross_exposure_amount,
        "committed_gross_exposure_amount": item.committed_gross_exposure_amount,
        "gross_exposure_delta_amount": item.gross_exposure_delta_amount,
        "reserved_gross_exposure_amount": item.reserved_gross_exposure_amount,
        "reserved_capital_amount": item.reserved_capital_amount,
        "committed_capital_amount": item.committed_capital_amount,
        "reason_codes": item.reason_codes,
    }


def crew_reservation_reconciliation_fingerprint(
    item: CrewReservationReconciliation,
) -> str:
    return stable_digest(crew_reservation_reconciliation_payload(item))


def _build_crew_reconciliation(
    *,
    exposure: CrewExposureSnapshot,
    usage: CrewReservationUsage,
) -> CrewReservationReconciliation:
    reasons = _crew_reason_codes(exposure=exposure, usage=usage)
    status = _crew_status(reasons)
    if exposure.status is SnapshotDataStatus.AVAILABLE:
        assert exposure.open_risk_amount is not None
        assert exposure.gross_exposure_amount is not None
        risk_delta = exposure.open_risk_amount - usage.committed_open_risk_amount
        gross_delta = exposure.gross_exposure_amount - usage.committed_gross_exposure_amount
    else:
        risk_delta = None
        gross_delta = None

    payload = {
        "schema": "money-heist.crew-reservation-reconciliation.v1",
        "system_id": exposure.system_id,
        "status": status,
        "observed_status": exposure.status,
        "observed_open_positions": exposure.open_positions,
        "observed_open_risk_amount": exposure.open_risk_amount,
        "committed_open_risk_amount": usage.committed_open_risk_amount,
        "open_risk_delta_amount": risk_delta,
        "reserved_open_risk_amount": usage.reserved_open_risk_amount,
        "observed_gross_exposure_amount": exposure.gross_exposure_amount,
        "committed_gross_exposure_amount": usage.committed_gross_exposure_amount,
        "gross_exposure_delta_amount": gross_delta,
        "reserved_gross_exposure_amount": usage.reserved_gross_exposure_amount,
        "reserved_capital_amount": usage.reserved_capital_amount,
        "committed_capital_amount": usage.committed_capital_amount,
        "reason_codes": reasons,
    }
    return CrewReservationReconciliation(
        system_id=exposure.system_id,
        status=status,
        observed_status=exposure.status,
        observed_open_positions=exposure.open_positions,
        observed_open_risk_amount=exposure.open_risk_amount,
        committed_open_risk_amount=usage.committed_open_risk_amount,
        open_risk_delta_amount=risk_delta,
        reserved_open_risk_amount=usage.reserved_open_risk_amount,
        observed_gross_exposure_amount=exposure.gross_exposure_amount,
        committed_gross_exposure_amount=usage.committed_gross_exposure_amount,
        gross_exposure_delta_amount=gross_delta,
        reserved_gross_exposure_amount=usage.reserved_gross_exposure_amount,
        reserved_capital_amount=usage.reserved_capital_amount,
        committed_capital_amount=usage.committed_capital_amount,
        reason_codes=reasons,
        fingerprint_sha256=stable_digest(payload),
    )


def _future_ledger_event_exists(
    *,
    ledger_snapshot: ReservationLedgerSnapshot,
    observed_at,
) -> bool:
    for record in ledger_snapshot.reservations:
        if record.request.requested_at > observed_at:
            return True
        if record.committed_at is not None and record.committed_at > observed_at:
            return True
        if record.released_at is not None and record.released_at > observed_at:
            return True
    return False


def _global_reason_codes(
    *,
    policy: MasterAllocationPolicy,
    ledger_snapshot: ReservationLedgerSnapshot,
    portfolio_snapshot: MasterPortfolioSnapshot,
) -> tuple[ReservationReconciliationReasonCode, ...]:
    reasons: list[ReservationReconciliationReasonCode] = []
    master_ids = {
        policy.master_portfolio_id,
        ledger_snapshot.master_portfolio_id,
        portfolio_snapshot.master_portfolio_id,
    }
    if len(master_ids) != 1:
        reasons.append(ReservationReconciliationReasonCode.MASTER_PORTFOLIO_ID_MISMATCH)
    if ledger_snapshot.policy_fingerprint_sha256 != policy.fingerprint_sha256:
        reasons.append(ReservationReconciliationReasonCode.POLICY_FINGERPRINT_MISMATCH)
    if portfolio_snapshot.members != policy.members:
        reasons.append(ReservationReconciliationReasonCode.MEMBERSHIP_MISMATCH)
    ledger_ids = tuple(item.system_id for item in ledger_snapshot.crew_usage)
    policy_ids = tuple(item.system_id for item in policy.members)
    if ledger_ids != policy_ids:
        reasons.append(ReservationReconciliationReasonCode.LEDGER_CREW_SET_MISMATCH)
    if _future_ledger_event_exists(
        ledger_snapshot=ledger_snapshot,
        observed_at=portfolio_snapshot.observed_at,
    ):
        reasons.append(ReservationReconciliationReasonCode.LEDGER_STATE_AFTER_OBSERVATION)
    if portfolio_snapshot.status is SnapshotDataStatus.UNAVAILABLE:
        reasons.append(ReservationReconciliationReasonCode.PORTFOLIO_SNAPSHOT_UNAVAILABLE)
    return _ordered_unique_reason_codes(reasons)


def _hard_global_failure(
    reasons: tuple[ReservationReconciliationReasonCode, ...],
) -> bool:
    hard = {
        ReservationReconciliationReasonCode.MASTER_PORTFOLIO_ID_MISMATCH,
        ReservationReconciliationReasonCode.POLICY_FINGERPRINT_MISMATCH,
        ReservationReconciliationReasonCode.MEMBERSHIP_MISMATCH,
        ReservationReconciliationReasonCode.LEDGER_CREW_SET_MISMATCH,
        ReservationReconciliationReasonCode.LEDGER_STATE_AFTER_OBSERVATION,
    }
    return any(reason in hard for reason in reasons)


def _report_reason_codes(
    *,
    global_reasons: tuple[ReservationReconciliationReasonCode, ...],
    crews: tuple[CrewReservationReconciliation, ...],
) -> tuple[str, ...]:
    reasons = [reason.value for reason in global_reasons]
    for crew in crews:
        reasons.extend(f"CREW:{crew.system_id}:{reason.value}" for reason in crew.reason_codes)
    return tuple(sorted(set(reasons)))


def _report_status(
    *,
    global_reasons: tuple[ReservationReconciliationReasonCode, ...],
    crews: tuple[CrewReservationReconciliation, ...],
) -> ReservationReconciliationStatus:
    if _hard_global_failure(global_reasons):
        return ReservationReconciliationStatus.UNAVAILABLE
    if any(crew.status is ReservationReconciliationStatus.INCONSISTENT for crew in crews):
        return ReservationReconciliationStatus.INCONSISTENT
    if (
        ReservationReconciliationReasonCode.PORTFOLIO_SNAPSHOT_UNAVAILABLE
        in global_reasons
    ):
        return ReservationReconciliationStatus.UNAVAILABLE
    if any(crew.status is ReservationReconciliationStatus.UNAVAILABLE for crew in crews):
        return ReservationReconciliationStatus.UNAVAILABLE
    if any(crew.status is ReservationReconciliationStatus.PENDING for crew in crews):
        return ReservationReconciliationStatus.PENDING
    return ReservationReconciliationStatus.CONSISTENT


@dataclass(frozen=True, slots=True)
class ReservationReconciliationReport:
    master_portfolio_id: str
    observed_at: datetime
    status: ReservationReconciliationStatus
    policy_fingerprint_sha256: str
    ledger_snapshot_fingerprint_sha256: str
    portfolio_snapshot_fingerprint_sha256: str
    opening_snapshot_fingerprint_sha256: str
    crews: tuple[CrewReservationReconciliation, ...]
    reason_codes: tuple[str, ...]
    fingerprint_sha256: str
    mutation_applied: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not self.master_portfolio_id.strip():
            raise ValueError("master_portfolio_id must not be blank")
        object.__setattr__(self, "master_portfolio_id", self.master_portfolio_id.strip())
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))
        expected_order = tuple(sorted(self.crews, key=lambda item: item.system_id))
        if self.crews != expected_order:
            raise ValueError("reconciliation crews must be sorted by system_id")
        crew_ids = tuple(item.system_id for item in self.crews)
        if len(set(crew_ids)) != len(crew_ids):
            raise ValueError("reconciliation crew system_id values must be unique")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("reconciliation reason_codes must be sorted and unique")
        reason_values = {item.value: item for item in ReservationReconciliationReasonCode}
        global_reasons = tuple(
            reason_values[value]
            for value in self.reason_codes
            if value in reason_values
        )
        expected_reasons = _report_reason_codes(
            global_reasons=global_reasons,
            crews=self.crews,
        )
        if self.reason_codes != expected_reasons:
            raise ValueError("reconciliation report reason_codes do not match payload")
        expected_status = _report_status(
            global_reasons=global_reasons,
            crews=self.crews,
        )
        if self.status is not expected_status:
            raise ValueError("reconciliation report status does not match payload")
        for field_name in (
            "policy_fingerprint_sha256",
            "ledger_snapshot_fingerprint_sha256",
            "portfolio_snapshot_fingerprint_sha256",
            "opening_snapshot_fingerprint_sha256",
        ):
            value = getattr(self, field_name).lower()
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"{field_name} must be a SHA-256 hex digest")
            object.__setattr__(self, field_name, value)
        expected = reservation_reconciliation_report_fingerprint(self)
        normalized = self.fingerprint_sha256.lower()
        if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError("fingerprint_sha256 must be a SHA-256 hex digest")
        if normalized != expected:
            raise ValueError("reconciliation report fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def reservation_reconciliation_report_payload(
    report: ReservationReconciliationReport,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-reservation-reconciliation.v1",
        "master_portfolio_id": report.master_portfolio_id,
        "observed_at": report.observed_at,
        "status": report.status,
        "policy_fingerprint_sha256": report.policy_fingerprint_sha256,
        "ledger_snapshot_fingerprint_sha256": report.ledger_snapshot_fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": report.portfolio_snapshot_fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": report.opening_snapshot_fingerprint_sha256,
        "crews": [crew.canonical_payload() for crew in report.crews],
        "reason_codes": report.reason_codes,
    }


def reservation_reconciliation_report_fingerprint(
    report: ReservationReconciliationReport,
) -> str:
    return stable_digest(reservation_reconciliation_report_payload(report))


def build_reservation_reconciliation_report(
    *,
    policy: MasterAllocationPolicy,
    ledger_snapshot: ReservationLedgerSnapshot,
    portfolio_snapshot: MasterPortfolioSnapshot,
) -> ReservationReconciliationReport:
    global_reasons = _global_reason_codes(
        policy=policy,
        ledger_snapshot=ledger_snapshot,
        portfolio_snapshot=portfolio_snapshot,
    )

    crews: tuple[CrewReservationReconciliation, ...]
    if _hard_global_failure(global_reasons):
        crews = ()
    else:
        usage_by_system = {item.system_id: item for item in ledger_snapshot.crew_usage}
        crews = tuple(
            _build_crew_reconciliation(
                exposure=exposure,
                usage=usage_by_system[exposure.system_id],
            )
            for exposure in portfolio_snapshot.crew_exposures
        )

    status = _report_status(global_reasons=global_reasons, crews=crews)
    reason_codes = _report_reason_codes(global_reasons=global_reasons, crews=crews)
    payload = {
        "schema": "money-heist.master-reservation-reconciliation.v1",
        "master_portfolio_id": policy.master_portfolio_id,
        "observed_at": portfolio_snapshot.observed_at,
        "status": status,
        "policy_fingerprint_sha256": policy.fingerprint_sha256,
        "ledger_snapshot_fingerprint_sha256": ledger_snapshot.fingerprint_sha256,
        "portfolio_snapshot_fingerprint_sha256": portfolio_snapshot.fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": (
            ledger_snapshot.opening_snapshot_fingerprint_sha256
        ),
        "crews": [crew.canonical_payload() for crew in crews],
        "reason_codes": reason_codes,
    }
    return ReservationReconciliationReport(
        master_portfolio_id=policy.master_portfolio_id,
        observed_at=portfolio_snapshot.observed_at,
        status=status,
        policy_fingerprint_sha256=policy.fingerprint_sha256,
        ledger_snapshot_fingerprint_sha256=ledger_snapshot.fingerprint_sha256,
        portfolio_snapshot_fingerprint_sha256=portfolio_snapshot.fingerprint_sha256,
        opening_snapshot_fingerprint_sha256=(
            ledger_snapshot.opening_snapshot_fingerprint_sha256
        ),
        crews=crews,
        reason_codes=reason_codes,
        fingerprint_sha256=stable_digest(payload),
    )


__all__ = [
    "CrewReservationReconciliation",
    "ReservationReconciliationReasonCode",
    "ReservationReconciliationReport",
    "ReservationReconciliationStatus",
    "build_reservation_reconciliation_report",
    "crew_reservation_reconciliation_fingerprint",
    "reservation_reconciliation_report_fingerprint",
]
