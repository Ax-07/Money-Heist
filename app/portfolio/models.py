from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.services.backtest.ids import stable_digest


class SnapshotDataStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


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


def _finite_decimal(
    value: Decimal,
    *,
    field_name: str,
    non_negative: bool = False,
) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if non_negative and value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


@dataclass(frozen=True, slots=True)
class PortfolioMemberRef:
    """One explicitly enrolled local system; membership grants no execution authority."""

    system_id: str
    membership_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        object.__setattr__(
            self,
            "membership_ref",
            _optional_text(self.membership_ref, field_name="membership_ref"),
        )

    def canonical_payload(self) -> dict[str, object]:
        return {
            "system_id": self.system_id,
            "membership_ref": self.membership_ref,
        }


@dataclass(frozen=True, slots=True)
class MasterCapitalSnapshot:
    """The single physical/logical capital source for one Master Portfolio snapshot."""

    master_portfolio_id: str
    observed_at: datetime
    status: SnapshotDataStatus
    source: str
    equity: Decimal | None = None
    cash_balance: Decimal | None = None
    day_start_equity: Decimal | None = None
    equity_peak: Decimal | None = None
    source_ref: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "master_portfolio_id",
            _required_text(self.master_portfolio_id, field_name="master_portfolio_id"),
        )
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, field_name="observed_at"),
        )
        object.__setattr__(self, "source", _required_text(self.source, field_name="source"))
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

        values = {
            "equity": self.equity,
            "cash_balance": self.cash_balance,
            "day_start_equity": self.day_start_equity,
            "equity_peak": self.equity_peak,
        }
        if self.status is SnapshotDataStatus.AVAILABLE:
            if any(value is None for value in values.values()):
                raise ValueError("AVAILABLE master capital requires every capital value")
            if self.reason_code is not None:
                raise ValueError("AVAILABLE master capital cannot carry reason_code")
            for field_name, value in values.items():
                assert value is not None
                _finite_decimal(value, field_name=field_name)
            return

        if self.status is not SnapshotDataStatus.UNAVAILABLE:
            raise ValueError(f"unsupported master capital status: {self.status}")
        if any(value is not None for value in values.values()):
            raise ValueError("UNAVAILABLE master capital cannot carry numeric capital values")
        if self.reason_code is None:
            raise ValueError("UNAVAILABLE master capital requires reason_code")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "master_portfolio_id": self.master_portfolio_id,
            "observed_at": self.observed_at,
            "status": self.status,
            "source": self.source,
            "equity": self.equity,
            "cash_balance": self.cash_balance,
            "day_start_equity": self.day_start_equity,
            "equity_peak": self.equity_peak,
            "source_ref": self.source_ref,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class CrewExposureSnapshot:
    """Crew-attributed exposure only. Capital/equity is intentionally absent."""

    system_id: str
    observed_at: datetime
    status: SnapshotDataStatus
    source: str
    open_positions: int | None = None
    gross_exposure_amount: Decimal | None = None
    open_risk_amount: Decimal | None = None
    source_ref: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, field_name="observed_at"),
        )
        object.__setattr__(self, "source", _required_text(self.source, field_name="source"))
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

        values = {
            "open_positions": self.open_positions,
            "gross_exposure_amount": self.gross_exposure_amount,
            "open_risk_amount": self.open_risk_amount,
        }
        if self.status is SnapshotDataStatus.AVAILABLE:
            if any(value is None for value in values.values()):
                raise ValueError("AVAILABLE crew exposure requires every exposure value")
            if self.reason_code is not None:
                raise ValueError("AVAILABLE crew exposure cannot carry reason_code")
            assert self.open_positions is not None
            if self.open_positions < 0:
                raise ValueError("open_positions must be >= 0")
            assert self.gross_exposure_amount is not None
            assert self.open_risk_amount is not None
            _finite_decimal(
                self.gross_exposure_amount,
                field_name="gross_exposure_amount",
                non_negative=True,
            )
            _finite_decimal(
                self.open_risk_amount,
                field_name="open_risk_amount",
                non_negative=True,
            )
            return

        if self.status is not SnapshotDataStatus.UNAVAILABLE:
            raise ValueError(f"unsupported crew exposure status: {self.status}")
        if any(value is not None for value in values.values()):
            raise ValueError("UNAVAILABLE crew exposure cannot carry numeric exposure values")
        if self.reason_code is None:
            raise ValueError("UNAVAILABLE crew exposure requires reason_code")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "system_id": self.system_id,
            "observed_at": self.observed_at,
            "status": self.status,
            "source": self.source,
            "open_positions": self.open_positions,
            "gross_exposure_amount": self.gross_exposure_amount,
            "open_risk_amount": self.open_risk_amount,
            "source_ref": self.source_ref,
            "reason_code": self.reason_code,
        }


def _expected_reason_codes(
    master_capital: MasterCapitalSnapshot,
    crew_exposures: tuple[CrewExposureSnapshot, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if master_capital.status is SnapshotDataStatus.UNAVAILABLE:
        assert master_capital.reason_code is not None
        reasons.append(f"MASTER_CAPITAL_UNAVAILABLE:{master_capital.reason_code}")
    for exposure in crew_exposures:
        if exposure.status is SnapshotDataStatus.UNAVAILABLE:
            assert exposure.reason_code is not None
            reasons.append(
                f"CREW_EXPOSURE_UNAVAILABLE:{exposure.system_id}:{exposure.reason_code}"
            )
    return tuple(sorted(reasons))


def master_portfolio_snapshot_payload(
    *,
    master_portfolio_id: str,
    observed_at: datetime,
    members: tuple[PortfolioMemberRef, ...],
    master_capital: MasterCapitalSnapshot,
    crew_exposures: tuple[CrewExposureSnapshot, ...],
    status: SnapshotDataStatus,
    aggregate_exposure_status: SnapshotDataStatus,
    total_open_positions: int | None,
    total_gross_exposure_amount: Decimal | None,
    total_open_risk_amount: Decimal | None,
    reason_codes: tuple[str, ...],
    schema_version: str,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-portfolio-snapshot.v1",
        "schema_version": schema_version,
        "master_portfolio_id": master_portfolio_id,
        "observed_at": observed_at,
        "members": [member.canonical_payload() for member in members],
        "master_capital": master_capital.canonical_payload(),
        "crew_exposures": [exposure.canonical_payload() for exposure in crew_exposures],
        "status": status,
        "aggregate_exposure_status": aggregate_exposure_status,
        "total_open_positions": total_open_positions,
        "total_gross_exposure_amount": total_gross_exposure_amount,
        "total_open_risk_amount": total_open_risk_amount,
        "reason_codes": reason_codes,
    }


def master_portfolio_snapshot_fingerprint(
    *,
    master_portfolio_id: str,
    observed_at: datetime,
    members: tuple[PortfolioMemberRef, ...],
    master_capital: MasterCapitalSnapshot,
    crew_exposures: tuple[CrewExposureSnapshot, ...],
    status: SnapshotDataStatus,
    aggregate_exposure_status: SnapshotDataStatus,
    total_open_positions: int | None,
    total_gross_exposure_amount: Decimal | None,
    total_open_risk_amount: Decimal | None,
    reason_codes: tuple[str, ...],
    schema_version: str,
) -> str:
    return stable_digest(
        master_portfolio_snapshot_payload(
            master_portfolio_id=master_portfolio_id,
            observed_at=observed_at,
            members=members,
            master_capital=master_capital,
            crew_exposures=crew_exposures,
            status=status,
            aggregate_exposure_status=aggregate_exposure_status,
            total_open_positions=total_open_positions,
            total_gross_exposure_amount=total_gross_exposure_amount,
            total_open_risk_amount=total_open_risk_amount,
            reason_codes=reason_codes,
            schema_version=schema_version,
        )
    )


@dataclass(frozen=True, slots=True)
class MasterPortfolioSnapshot:
    """Read-only Master Portfolio state. No allocation, Risk, broker, or LIVE authority."""

    master_portfolio_id: str
    observed_at: datetime
    members: tuple[PortfolioMemberRef, ...]
    master_capital: MasterCapitalSnapshot
    crew_exposures: tuple[CrewExposureSnapshot, ...]
    status: SnapshotDataStatus
    aggregate_exposure_status: SnapshotDataStatus
    total_open_positions: int | None
    total_gross_exposure_amount: Decimal | None
    total_open_risk_amount: Decimal | None
    reason_codes: tuple[str, ...]
    fingerprint_sha256: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        normalized_id = _required_text(self.master_portfolio_id, field_name="master_portfolio_id")
        object.__setattr__(self, "master_portfolio_id", normalized_id)
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master Portfolio snapshot schema_version")
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, field_name="observed_at"),
        )
        if not self.members:
            raise ValueError("Master Portfolio requires at least one member")
        member_ids = tuple(member.system_id for member in self.members)
        exposure_ids = tuple(exposure.system_id for exposure in self.crew_exposures)
        if member_ids != tuple(sorted(member_ids)):
            raise ValueError("members must be sorted by system_id")
        if exposure_ids != tuple(sorted(exposure_ids)):
            raise ValueError("crew_exposures must be sorted by system_id")
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("Master Portfolio member system_id values must be unique")
        if len(set(exposure_ids)) != len(exposure_ids):
            raise ValueError("crew exposure system_id values must be unique")
        if set(member_ids) != set(exposure_ids):
            raise ValueError("every Master Portfolio member requires exactly one crew exposure")
        if self.master_capital.master_portfolio_id != self.master_portfolio_id:
            raise ValueError("master capital belongs to another Master Portfolio")
        if self.master_capital.observed_at != self.observed_at:
            raise ValueError("master capital observed_at must match the Master snapshot")
        if any(exposure.observed_at != self.observed_at for exposure in self.crew_exposures):
            raise ValueError("crew exposure observed_at values must match the Master snapshot")

        exposures_available = all(
            exposure.status is SnapshotDataStatus.AVAILABLE for exposure in self.crew_exposures
        )
        expected_aggregate_status = (
            SnapshotDataStatus.AVAILABLE
            if exposures_available
            else SnapshotDataStatus.UNAVAILABLE
        )
        if self.aggregate_exposure_status is not expected_aggregate_status:
            raise ValueError("aggregate_exposure_status does not match crew exposure availability")

        if exposures_available:
            expected_positions = sum(
                exposure.open_positions or 0 for exposure in self.crew_exposures
            )
            expected_gross = sum(
                (
                    exposure.gross_exposure_amount or Decimal("0")
                    for exposure in self.crew_exposures
                ),
                Decimal("0"),
            )
            expected_risk = sum(
                (exposure.open_risk_amount or Decimal("0") for exposure in self.crew_exposures),
                Decimal("0"),
            )
            if self.total_open_positions != expected_positions:
                raise ValueError("total_open_positions does not match crew exposures")
            if self.total_gross_exposure_amount != expected_gross:
                raise ValueError("total_gross_exposure_amount does not match crew exposures")
            if self.total_open_risk_amount != expected_risk:
                raise ValueError("total_open_risk_amount does not match crew exposures")
        elif any(
            value is not None
            for value in (
                self.total_open_positions,
                self.total_gross_exposure_amount,
                self.total_open_risk_amount,
            )
        ):
            raise ValueError("unavailable exposure aggregate cannot carry invented totals")

        expected_status = (
            SnapshotDataStatus.AVAILABLE
            if self.master_capital.status is SnapshotDataStatus.AVAILABLE and exposures_available
            else SnapshotDataStatus.UNAVAILABLE
        )
        if self.status is not expected_status:
            raise ValueError("Master Portfolio status does not match input availability")

        expected_reasons = _expected_reason_codes(self.master_capital, self.crew_exposures)
        if self.reason_codes != expected_reasons:
            raise ValueError("reason_codes do not match unavailable inputs")

        normalized_fingerprint = self.fingerprint_sha256.lower()
        if len(normalized_fingerprint) != 64 or any(
            char not in "0123456789abcdef" for char in normalized_fingerprint
        ):
            raise ValueError("fingerprint_sha256 must be a SHA-256 hex digest")
        object.__setattr__(self, "fingerprint_sha256", normalized_fingerprint)

        expected_fingerprint = master_portfolio_snapshot_fingerprint(
            master_portfolio_id=self.master_portfolio_id,
            observed_at=self.observed_at,
            members=self.members,
            master_capital=self.master_capital,
            crew_exposures=self.crew_exposures,
            status=self.status,
            aggregate_exposure_status=self.aggregate_exposure_status,
            total_open_positions=self.total_open_positions,
            total_gross_exposure_amount=self.total_gross_exposure_amount,
            total_open_risk_amount=self.total_open_risk_amount,
            reason_codes=self.reason_codes,
            schema_version=self.schema_version,
        )
        if self.fingerprint_sha256 != expected_fingerprint:
            raise ValueError("Master Portfolio fingerprint does not match payload")
