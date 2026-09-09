from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.services.backtest.ids import stable_digest

from .allocation import AllocationEnvelopeStatus, CrewAllocationEnvelope, MasterAllocationPolicy
from .models import MasterPortfolioSnapshot, SnapshotDataStatus

ZERO = Decimal("0")


class ReservationRecordStatus(StrEnum):
    RESERVED = "RESERVED"
    COMMITTED = "COMMITTED"
    RELEASED = "RELEASED"


class ReservationOutcomeStatus(StrEnum):
    RESERVED = "RESERVED"
    NOT_RESERVED = "NOT_RESERVED"


class ReservationReasonCode(StrEnum):
    UNKNOWN_CREW = "UNKNOWN_CREW"
    CAPITAL_ENVELOPE_EXCEEDED = "CAPITAL_ENVELOPE_EXCEEDED"
    OPEN_RISK_ENVELOPE_EXCEEDED = "OPEN_RISK_ENVELOPE_EXCEEDED"
    GROSS_EXPOSURE_ENVELOPE_EXCEEDED = "GROSS_EXPOSURE_ENVELOPE_EXCEEDED"
    MASTER_CAPITAL_EXCEEDED = "MASTER_CAPITAL_EXCEEDED"


class ReservationLedgerInitializationError(ValueError):
    pass


class ReservationIdempotencyConflict(ValueError):
    pass


class ReservationStateTransitionError(ValueError):
    pass


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


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _non_negative(value: Decimal, *, field_name: str) -> Decimal:
    if not value.is_finite() or value < ZERO:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


def _request_payload(request: ReservationRequest) -> dict[str, object]:
    return {
        "schema": "money-heist.master-reservation-request.v1",
        "request_id": request.request_id,
        "system_id": request.system_id,
        "requested_at": request.requested_at,
        "capital_amount": request.capital_amount,
        "open_risk_amount": request.open_risk_amount,
        "gross_exposure_amount": request.gross_exposure_amount,
        "request_ref": request.request_ref,
    }


@dataclass(frozen=True, slots=True)
class ReservationRequest:
    """Explicit accounting capacity request; amounts are supplied, never inferred here."""

    request_id: str
    system_id: str
    requested_at: datetime
    capital_amount: Decimal
    open_risk_amount: Decimal
    gross_exposure_amount: Decimal
    request_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _required_text(self.request_id, field_name="request_id"),
        )
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        object.__setattr__(
            self,
            "requested_at",
            _utc(self.requested_at, field_name="requested_at"),
        )
        object.__setattr__(
            self,
            "request_ref",
            _optional_text(self.request_ref, field_name="request_ref"),
        )
        for field_name in (
            "capital_amount",
            "open_risk_amount",
            "gross_exposure_amount",
        ):
            _non_negative(getattr(self, field_name), field_name=field_name)
        if (
            self.capital_amount == ZERO
            and self.open_risk_amount == ZERO
            and self.gross_exposure_amount == ZERO
        ):
            raise ValueError("reservation request must reserve at least one non-zero amount")

    @property
    def fingerprint_sha256(self) -> str:
        return stable_digest(_request_payload(self))


@dataclass(frozen=True, slots=True)
class PortfolioReservation:
    reservation_id: str
    request: ReservationRequest
    status: ReservationRecordStatus
    master_portfolio_id: str
    policy_fingerprint_sha256: str
    opening_snapshot_fingerprint_sha256: str
    committed_at: datetime | None = None
    commit_ref: str | None = None
    released_at: datetime | None = None
    release_ref: str | None = None
    fingerprint_sha256: str = ""
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reservation_id",
            _required_text(self.reservation_id, field_name="reservation_id"),
        )
        object.__setattr__(
            self,
            "master_portfolio_id",
            _required_text(self.master_portfolio_id, field_name="master_portfolio_id"),
        )
        object.__setattr__(
            self,
            "commit_ref",
            _optional_text(self.commit_ref, field_name="commit_ref"),
        )
        object.__setattr__(
            self,
            "release_ref",
            _optional_text(self.release_ref, field_name="release_ref"),
        )
        if self.committed_at is not None:
            object.__setattr__(
                self,
                "committed_at",
                _utc(self.committed_at, field_name="committed_at"),
            )
        if self.released_at is not None:
            object.__setattr__(
                self,
                "released_at",
                _utc(self.released_at, field_name="released_at"),
            )

        if self.status is ReservationRecordStatus.RESERVED:
            if any(
                value is not None
                for value in (
                    self.committed_at,
                    self.commit_ref,
                    self.released_at,
                    self.release_ref,
                )
            ):
                raise ValueError("RESERVED record cannot carry commit or release metadata")
        elif self.status is ReservationRecordStatus.COMMITTED:
            if self.committed_at is None or self.commit_ref is None:
                raise ValueError("COMMITTED record requires committed_at and commit_ref")
            if self.committed_at < self.request.requested_at:
                raise ValueError("committed_at cannot precede requested_at")
            if self.released_at is not None or self.release_ref is not None:
                raise ValueError("COMMITTED record cannot carry release metadata")
        elif self.status is ReservationRecordStatus.RELEASED:
            if self.released_at is None or self.release_ref is None:
                raise ValueError("RELEASED record requires released_at and release_ref")
            if self.released_at < self.request.requested_at:
                raise ValueError("released_at cannot precede requested_at")
            if self.committed_at is None and self.commit_ref is not None:
                raise ValueError("release cannot carry commit_ref without committed_at")
            if self.committed_at is not None:
                if self.commit_ref is None:
                    raise ValueError("committed release history requires commit_ref")
                if self.committed_at < self.request.requested_at:
                    raise ValueError("committed_at cannot precede requested_at")
                if self.released_at < self.committed_at:
                    raise ValueError("released_at cannot precede committed_at")
        else:
            raise ValueError(f"unsupported reservation status: {self.status}")

        expected_fingerprint = reservation_record_fingerprint(self)
        if self.fingerprint_sha256:
            normalized = self.fingerprint_sha256.lower()
            if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
                raise ValueError("fingerprint_sha256 must be a SHA-256 hex digest")
            if normalized != expected_fingerprint:
                raise ValueError("reservation fingerprint does not match payload")
            object.__setattr__(self, "fingerprint_sha256", normalized)
        else:
            object.__setattr__(self, "fingerprint_sha256", expected_fingerprint)

    @property
    def consumes_capacity(self) -> bool:
        return self.status in {
            ReservationRecordStatus.RESERVED,
            ReservationRecordStatus.COMMITTED,
        }


def reservation_record_payload(record: PortfolioReservation) -> dict[str, object]:
    return {
        "schema": "money-heist.master-reservation-record.v1",
        "reservation_id": record.reservation_id,
        "request": _request_payload(record.request),
        "status": record.status,
        "master_portfolio_id": record.master_portfolio_id,
        "policy_fingerprint_sha256": record.policy_fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": record.opening_snapshot_fingerprint_sha256,
        "committed_at": record.committed_at,
        "commit_ref": record.commit_ref,
        "released_at": record.released_at,
        "release_ref": record.release_ref,
    }


def reservation_record_fingerprint(record: PortfolioReservation) -> str:
    return stable_digest(reservation_record_payload(record))


@dataclass(frozen=True, slots=True)
class ReservationResult:
    request: ReservationRequest
    status: ReservationOutcomeStatus
    reason_codes: tuple[ReservationReasonCode, ...]
    reservation: PortfolioReservation | None
    fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.status is ReservationOutcomeStatus.RESERVED:
            if self.reservation is None:
                raise ValueError("RESERVED result requires reservation")
            if self.reason_codes:
                raise ValueError("RESERVED result cannot carry reason_codes")
        elif self.status is ReservationOutcomeStatus.NOT_RESERVED:
            if self.reservation is not None:
                raise ValueError("NOT_RESERVED result cannot carry reservation")
            if not self.reason_codes:
                raise ValueError("NOT_RESERVED result requires reason_codes")
        else:
            raise ValueError(f"unsupported reservation outcome status: {self.status}")

        expected = reservation_result_fingerprint(self)
        normalized = self.fingerprint_sha256.lower()
        if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError("fingerprint_sha256 must be a SHA-256 hex digest")
        if normalized != expected:
            raise ValueError("reservation result fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def reservation_result_payload(result: ReservationResult) -> dict[str, object]:
    return {
        "schema": "money-heist.master-reservation-result.v1",
        "request_fingerprint_sha256": result.request.fingerprint_sha256,
        "status": result.status,
        "reason_codes": result.reason_codes,
        "reservation_fingerprint_sha256": (
            result.reservation.fingerprint_sha256 if result.reservation is not None else None
        ),
    }


def reservation_result_fingerprint(result: ReservationResult) -> str:
    return stable_digest(reservation_result_payload(result))


@dataclass(frozen=True, slots=True)
class CrewReservationUsage:
    system_id: str
    reserved_capital_amount: Decimal
    committed_capital_amount: Decimal
    active_capital_amount: Decimal
    reserved_open_risk_amount: Decimal
    committed_open_risk_amount: Decimal
    active_open_risk_amount: Decimal
    reserved_gross_exposure_amount: Decimal
    committed_gross_exposure_amount: Decimal
    active_gross_exposure_amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        for field_name in (
            "reserved_capital_amount",
            "committed_capital_amount",
            "active_capital_amount",
            "reserved_open_risk_amount",
            "committed_open_risk_amount",
            "active_open_risk_amount",
            "reserved_gross_exposure_amount",
            "committed_gross_exposure_amount",
            "active_gross_exposure_amount",
        ):
            _non_negative(getattr(self, field_name), field_name=field_name)
        if self.active_capital_amount != (
            self.reserved_capital_amount + self.committed_capital_amount
        ):
            raise ValueError("crew active capital must equal reserved + committed")
        if self.active_open_risk_amount != (
            self.reserved_open_risk_amount + self.committed_open_risk_amount
        ):
            raise ValueError("crew active open risk must equal reserved + committed")
        if self.active_gross_exposure_amount != (
            self.reserved_gross_exposure_amount + self.committed_gross_exposure_amount
        ):
            raise ValueError("crew active gross exposure must equal reserved + committed")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "system_id": self.system_id,
            "reserved_capital_amount": self.reserved_capital_amount,
            "committed_capital_amount": self.committed_capital_amount,
            "active_capital_amount": self.active_capital_amount,
            "reserved_open_risk_amount": self.reserved_open_risk_amount,
            "committed_open_risk_amount": self.committed_open_risk_amount,
            "active_open_risk_amount": self.active_open_risk_amount,
            "reserved_gross_exposure_amount": self.reserved_gross_exposure_amount,
            "committed_gross_exposure_amount": self.committed_gross_exposure_amount,
            "active_gross_exposure_amount": self.active_gross_exposure_amount,
        }


@dataclass(frozen=True, slots=True)
class ReservationLedgerSnapshot:
    master_portfolio_id: str
    policy_fingerprint_sha256: str
    opening_snapshot_fingerprint_sha256: str
    master_capital_capacity_amount: Decimal
    reserved_capital_amount: Decimal
    committed_capital_amount: Decimal
    active_capital_amount: Decimal
    available_capital_amount: Decimal
    crew_usage: tuple[CrewReservationUsage, ...]
    reservations: tuple[PortfolioReservation, ...]
    fingerprint_sha256: str

    def __post_init__(self) -> None:
        for field_name in (
            "master_capital_capacity_amount",
            "reserved_capital_amount",
            "committed_capital_amount",
            "active_capital_amount",
            "available_capital_amount",
        ):
            _non_negative(getattr(self, field_name), field_name=field_name)
        if self.active_capital_amount != (
            self.reserved_capital_amount + self.committed_capital_amount
        ):
            raise ValueError("active_capital_amount must equal reserved + committed")
        if self.available_capital_amount != (
            self.master_capital_capacity_amount - self.active_capital_amount
        ):
            raise ValueError("available_capital_amount does not match active capacity")
        if self.available_capital_amount < ZERO:
            raise ValueError("ledger snapshot cannot represent negative available capital")
        expected_usage_order = tuple(sorted(self.crew_usage, key=lambda item: item.system_id))
        if self.crew_usage != expected_usage_order:
            raise ValueError("ledger crew_usage must be sorted by system_id")
        usage_ids = tuple(item.system_id for item in self.crew_usage)
        if len(set(usage_ids)) != len(usage_ids):
            raise ValueError("ledger crew_usage system_id values must be unique")
        expected_order = tuple(sorted(self.reservations, key=lambda item: item.reservation_id))
        if self.reservations != expected_order:
            raise ValueError("ledger reservations must be sorted by reservation_id")
        expected = reservation_ledger_snapshot_fingerprint(self)
        normalized = self.fingerprint_sha256.lower()
        if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError("fingerprint_sha256 must be a SHA-256 hex digest")
        if normalized != expected:
            raise ValueError("reservation ledger snapshot fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def reservation_ledger_snapshot_payload(snapshot: ReservationLedgerSnapshot) -> dict[str, object]:
    return {
        "schema": "money-heist.master-reservation-ledger-snapshot.v1",
        "master_portfolio_id": snapshot.master_portfolio_id,
        "policy_fingerprint_sha256": snapshot.policy_fingerprint_sha256,
        "opening_snapshot_fingerprint_sha256": snapshot.opening_snapshot_fingerprint_sha256,
        "master_capital_capacity_amount": snapshot.master_capital_capacity_amount,
        "reserved_capital_amount": snapshot.reserved_capital_amount,
        "committed_capital_amount": snapshot.committed_capital_amount,
        "active_capital_amount": snapshot.active_capital_amount,
        "available_capital_amount": snapshot.available_capital_amount,
        "crew_usage": [item.canonical_payload() for item in snapshot.crew_usage],
        "reservations": [reservation_record_payload(item) for item in snapshot.reservations],
    }


def reservation_ledger_snapshot_fingerprint(snapshot: ReservationLedgerSnapshot) -> str:
    return stable_digest(reservation_ledger_snapshot_payload(snapshot))


class MasterReservationLedger:
    """Deterministic in-memory capacity ledger with no Risk, admission, broker, or LIVE power."""

    def __init__(
        self,
        *,
        policy: MasterAllocationPolicy,
        opening_snapshot: MasterPortfolioSnapshot,
    ) -> None:
        self._validate_opening(policy=policy, opening_snapshot=opening_snapshot)
        assert opening_snapshot.master_capital.equity is not None
        self.policy = policy
        self.opening_snapshot = opening_snapshot
        self.master_capital_capacity_amount = opening_snapshot.master_capital.equity
        self._records: dict[str, PortfolioReservation] = {}
        self._attempts: dict[str, tuple[str, ReservationResult]] = {}
        self.risk_authority = False
        self.admission_authority = False
        self.broker_authority = False
        self.live_authority = False

    @staticmethod
    def _validate_opening(
        *,
        policy: MasterAllocationPolicy,
        opening_snapshot: MasterPortfolioSnapshot,
    ) -> None:
        if policy.status is not AllocationEnvelopeStatus.CONFIGURED:
            raise ReservationLedgerInitializationError(
                "allocation policy must be fully CONFIGURED before opening reservation ledger"
            )
        if opening_snapshot.status is not SnapshotDataStatus.AVAILABLE:
            raise ReservationLedgerInitializationError(
                "opening Master Portfolio snapshot must be AVAILABLE"
            )
        if policy.master_portfolio_id != opening_snapshot.master_portfolio_id:
            raise ReservationLedgerInitializationError(
                "allocation policy and opening snapshot belong to different Master Portfolios"
            )
        if policy.members != opening_snapshot.members:
            raise ReservationLedgerInitializationError(
                "allocation policy membership must match opening snapshot membership exactly"
            )
        if (
            opening_snapshot.total_open_positions != 0
            or opening_snapshot.total_gross_exposure_amount != ZERO
            or opening_snapshot.total_open_risk_amount != ZERO
        ):
            raise ReservationLedgerInitializationError(
                "reservation ledger foundation requires an observable flat opening portfolio"
            )
        equity = opening_snapshot.master_capital.equity
        cash = opening_snapshot.master_capital.cash_balance
        assert equity is not None and cash is not None
        if equity < ZERO:
            raise ReservationLedgerInitializationError("opening Master capital equity must be >= 0")
        if cash != equity:
            raise ReservationLedgerInitializationError(
                "flat opening portfolio requires cash_balance to equal equity"
            )

    def reserve(self, request: ReservationRequest) -> ReservationResult:
        request_fingerprint = request.fingerprint_sha256
        previous = self._attempts.get(request.request_id)
        if previous is not None:
            previous_fingerprint, previous_result = previous
            if previous_fingerprint != request_fingerprint:
                raise ReservationIdempotencyConflict(
                    f"request_id {request.request_id!r} was already used with another payload"
                )
            return previous_result

        reasons = self._capacity_reasons(request)
        if reasons:
            result = self._result(
                request=request,
                status=ReservationOutcomeStatus.NOT_RESERVED,
                reason_codes=reasons,
                reservation=None,
            )
            self._attempts[request.request_id] = (request_fingerprint, result)
            return result

        reservation_id = "reservation:" + stable_digest(
            {
                "schema": "money-heist.master-reservation-id.v1",
                "master_portfolio_id": self.policy.master_portfolio_id,
                "policy_fingerprint_sha256": self.policy.fingerprint_sha256,
                "opening_snapshot_fingerprint_sha256": self.opening_snapshot.fingerprint_sha256,
                "request_fingerprint_sha256": request_fingerprint,
            }
        )
        reservation = PortfolioReservation(
            reservation_id=reservation_id,
            request=request,
            status=ReservationRecordStatus.RESERVED,
            master_portfolio_id=self.policy.master_portfolio_id,
            policy_fingerprint_sha256=self.policy.fingerprint_sha256,
            opening_snapshot_fingerprint_sha256=self.opening_snapshot.fingerprint_sha256,
        )
        self._records[reservation_id] = reservation
        result = self._result(
            request=request,
            status=ReservationOutcomeStatus.RESERVED,
            reason_codes=(),
            reservation=reservation,
        )
        self._attempts[request.request_id] = (request_fingerprint, result)
        return result

    def commit(
        self,
        reservation_id: str,
        *,
        committed_at: datetime,
        commit_ref: str,
    ) -> PortfolioReservation:
        record = self._record(reservation_id)
        normalized_time = _utc(committed_at, field_name="committed_at")
        normalized_ref = _required_text(commit_ref, field_name="commit_ref")
        if record.status is ReservationRecordStatus.COMMITTED:
            if record.committed_at != normalized_time or record.commit_ref != normalized_ref:
                raise ReservationStateTransitionError(
                    "COMMITTED reservation cannot be recommitted with different metadata"
                )
            return record
        if record.status is ReservationRecordStatus.RELEASED:
            raise ReservationStateTransitionError("RELEASED reservation cannot be committed")
        updated = replace(
            record,
            status=ReservationRecordStatus.COMMITTED,
            committed_at=normalized_time,
            commit_ref=normalized_ref,
            fingerprint_sha256="",
        )
        self._records[record.reservation_id] = updated
        return updated

    def release(
        self,
        reservation_id: str,
        *,
        released_at: datetime,
        release_ref: str,
    ) -> PortfolioReservation:
        record = self._record(reservation_id)
        normalized_time = _utc(released_at, field_name="released_at")
        normalized_ref = _required_text(release_ref, field_name="release_ref")
        if record.status is ReservationRecordStatus.RELEASED:
            if record.released_at != normalized_time or record.release_ref != normalized_ref:
                raise ReservationStateTransitionError(
                    "RELEASED reservation cannot be rereleased with different metadata"
                )
            return record
        updated = replace(
            record,
            status=ReservationRecordStatus.RELEASED,
            released_at=normalized_time,
            release_ref=normalized_ref,
            fingerprint_sha256="",
        )
        self._records[record.reservation_id] = updated
        return updated

    def get(self, reservation_id: str) -> PortfolioReservation:
        return self._record(reservation_id)

    def records(self) -> tuple[PortfolioReservation, ...]:
        return tuple(sorted(self._records.values(), key=lambda item: item.reservation_id))

    def snapshot(self) -> ReservationLedgerSnapshot:
        records = self.records()
        reserved_capital = sum(
            (
                item.request.capital_amount
                for item in records
                if item.status is ReservationRecordStatus.RESERVED
            ),
            ZERO,
        )
        committed_capital = sum(
            (
                item.request.capital_amount
                for item in records
                if item.status is ReservationRecordStatus.COMMITTED
            ),
            ZERO,
        )
        active = reserved_capital + committed_capital
        crew_usage = tuple(
            self._crew_usage(member.system_id, records)
            for member in self.policy.members
        )
        payload = {
            "schema": "money-heist.master-reservation-ledger-snapshot.v1",
            "master_portfolio_id": self.policy.master_portfolio_id,
            "policy_fingerprint_sha256": self.policy.fingerprint_sha256,
            "opening_snapshot_fingerprint_sha256": self.opening_snapshot.fingerprint_sha256,
            "master_capital_capacity_amount": self.master_capital_capacity_amount,
            "reserved_capital_amount": reserved_capital,
            "committed_capital_amount": committed_capital,
            "active_capital_amount": active,
            "available_capital_amount": self.master_capital_capacity_amount - active,
            "crew_usage": [item.canonical_payload() for item in crew_usage],
            "reservations": [reservation_record_payload(item) for item in records],
        }
        return ReservationLedgerSnapshot(
            master_portfolio_id=self.policy.master_portfolio_id,
            policy_fingerprint_sha256=self.policy.fingerprint_sha256,
            opening_snapshot_fingerprint_sha256=self.opening_snapshot.fingerprint_sha256,
            master_capital_capacity_amount=self.master_capital_capacity_amount,
            reserved_capital_amount=reserved_capital,
            committed_capital_amount=committed_capital,
            active_capital_amount=active,
            available_capital_amount=self.master_capital_capacity_amount - active,
            crew_usage=crew_usage,
            reservations=records,
            fingerprint_sha256=stable_digest(payload),
        )

    @staticmethod
    def _crew_usage(
        system_id: str,
        records: tuple[PortfolioReservation, ...],
    ) -> CrewReservationUsage:
        reserved_capital = ZERO
        committed_capital = ZERO
        reserved_risk = ZERO
        committed_risk = ZERO
        reserved_gross = ZERO
        committed_gross = ZERO
        for record in records:
            if record.request.system_id != system_id:
                continue
            if record.status is ReservationRecordStatus.RESERVED:
                reserved_capital += record.request.capital_amount
                reserved_risk += record.request.open_risk_amount
                reserved_gross += record.request.gross_exposure_amount
            elif record.status is ReservationRecordStatus.COMMITTED:
                committed_capital += record.request.capital_amount
                committed_risk += record.request.open_risk_amount
                committed_gross += record.request.gross_exposure_amount
        return CrewReservationUsage(
            system_id=system_id,
            reserved_capital_amount=reserved_capital,
            committed_capital_amount=committed_capital,
            active_capital_amount=reserved_capital + committed_capital,
            reserved_open_risk_amount=reserved_risk,
            committed_open_risk_amount=committed_risk,
            active_open_risk_amount=reserved_risk + committed_risk,
            reserved_gross_exposure_amount=reserved_gross,
            committed_gross_exposure_amount=committed_gross,
            active_gross_exposure_amount=reserved_gross + committed_gross,
        )

    def _capacity_reasons(
        self,
        request: ReservationRequest,
    ) -> tuple[ReservationReasonCode, ...]:
        envelope = self._envelope(request.system_id)
        if envelope is None:
            return (ReservationReasonCode.UNKNOWN_CREW,)
        assert envelope.status is AllocationEnvelopeStatus.CONFIGURED
        assert envelope.capital_ceiling_amount is not None
        assert envelope.open_risk_ceiling_amount is not None
        assert envelope.gross_exposure_ceiling_amount is not None

        crew_capital, crew_risk, crew_gross, global_capital = self._active_usage(request.system_id)
        reasons: list[ReservationReasonCode] = []
        if crew_capital + request.capital_amount > envelope.capital_ceiling_amount:
            reasons.append(ReservationReasonCode.CAPITAL_ENVELOPE_EXCEEDED)
        if crew_risk + request.open_risk_amount > envelope.open_risk_ceiling_amount:
            reasons.append(ReservationReasonCode.OPEN_RISK_ENVELOPE_EXCEEDED)
        if crew_gross + request.gross_exposure_amount > envelope.gross_exposure_ceiling_amount:
            reasons.append(ReservationReasonCode.GROSS_EXPOSURE_ENVELOPE_EXCEEDED)
        if global_capital + request.capital_amount > self.master_capital_capacity_amount:
            reasons.append(ReservationReasonCode.MASTER_CAPITAL_EXCEEDED)
        return tuple(reasons)

    def _active_usage(self, system_id: str) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        crew_capital = ZERO
        crew_risk = ZERO
        crew_gross = ZERO
        global_capital = ZERO
        for record in self._records.values():
            if not record.consumes_capacity:
                continue
            global_capital += record.request.capital_amount
            if record.request.system_id != system_id:
                continue
            crew_capital += record.request.capital_amount
            crew_risk += record.request.open_risk_amount
            crew_gross += record.request.gross_exposure_amount
        return crew_capital, crew_risk, crew_gross, global_capital

    def _envelope(self, system_id: str) -> CrewAllocationEnvelope | None:
        for envelope in self.policy.envelopes:
            if envelope.system_id == system_id:
                return envelope
        return None

    def _record(self, reservation_id: str) -> PortfolioReservation:
        normalized = _required_text(reservation_id, field_name="reservation_id")
        try:
            return self._records[normalized]
        except KeyError as exc:
            raise KeyError(f"unknown reservation_id {normalized!r}") from exc

    @staticmethod
    def _result(
        *,
        request: ReservationRequest,
        status: ReservationOutcomeStatus,
        reason_codes: tuple[ReservationReasonCode, ...],
        reservation: PortfolioReservation | None,
    ) -> ReservationResult:
        payload = {
            "schema": "money-heist.master-reservation-result.v1",
            "request_fingerprint_sha256": request.fingerprint_sha256,
            "status": status,
            "reason_codes": reason_codes,
            "reservation_fingerprint_sha256": (
                reservation.fingerprint_sha256 if reservation is not None else None
            ),
        }
        return ReservationResult(
            request=request,
            status=status,
            reason_codes=reason_codes,
            reservation=reservation,
            fingerprint_sha256=stable_digest(payload),
        )


__all__ = [
    "CrewReservationUsage",
    "MasterReservationLedger",
    "PortfolioReservation",
    "ReservationIdempotencyConflict",
    "ReservationLedgerInitializationError",
    "ReservationLedgerSnapshot",
    "ReservationOutcomeStatus",
    "ReservationReasonCode",
    "ReservationRecordStatus",
    "ReservationRequest",
    "ReservationResult",
    "ReservationStateTransitionError",
    "reservation_ledger_snapshot_fingerprint",
    "reservation_record_fingerprint",
    "reservation_result_fingerprint",
]
