from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.services.backtest.ids import stable_digest
from app.trading.risk.models import RiskDecision, RiskDecisionStatus, RiskReasonCode

from .historical_replay import MasterHistoricalReplayPlan
from .historical_replay_coordinator import (
    MasterHistoricalReplayBarrier,
    MasterHistoricalReplayBarrierPhase,
    MasterHistoricalReplayTimeline,
)
from .risk_gate import local_risk_decision_fingerprint

ZERO = Decimal("0")
_LOCAL_AUTHORIZED = {RiskDecisionStatus.APPROVED, RiskDecisionStatus.RESIZED}


class HistoricalCrewDecisionStatus(StrEnum):
    NO_OPPORTUNITY = "NO_OPPORTUNITY"
    NO_ANALYSIS = "NO_ANALYSIS"
    NO_TRADE = "NO_TRADE"
    ORCHESTRATION_FAILED = "ORCHESTRATION_FAILED"
    LOCAL_RISK_REJECTED = "LOCAL_RISK_REJECTED"
    LOCAL_RISK_AUTHORIZED = "LOCAL_RISK_AUTHORIZED"


class MasterHistoricalDecisionBarrierStatus(StrEnum):
    READY_FOR_RESERVATION = "READY_FOR_RESERVATION"


def _required_text(value: object, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _optional_text(value: object | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name=field_name)


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


def _non_negative_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < ZERO:
        raise ValueError(f"{field_name} must be a finite Decimal >= 0")
    return value


def _enum_text(value: object, *, field_name: str) -> str:
    raw = getattr(value, "value", value)
    return _required_text(raw, field_name=field_name)


def _object_payload(value: object, *, field_name: str) -> object:
    canonical = getattr(value, "canonical_payload", None)
    if callable(canonical):
        return canonical()
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="python")
    if hasattr(value, "__dataclass_fields__"):
        return value
    raise ValueError(
        f"{field_name} must be a dataclass or expose canonical_payload()/model_dump()"
    )


def _object_fingerprint(value: object, *, field_name: str) -> str:
    return stable_digest(_object_payload(value, field_name=field_name))


def _risk_details(decision: RiskDecision) -> tuple[tuple[str, str], ...]:
    normalized: list[tuple[str, str]] = []
    for key, value in decision.details.items():
        key_text = _required_text(key, field_name="RiskDecision.details key")
        normalized.append((key_text, str(value)))
    return tuple(sorted(normalized))


def master_historical_candidate_seed_payload(
    seed: MasterHistoricalCandidateSeed,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-candidate-seed.v1",
        "schema_version": seed.schema_version,
        "master_portfolio_id": seed.master_portfolio_id,
        "plan_id": seed.plan_id,
        "timeline_id": seed.timeline_id,
        "barrier_sequence": seed.barrier_sequence,
        "barrier_fingerprint_sha256": seed.barrier_fingerprint_sha256,
        "observed_at": seed.observed_at,
        "system_id": seed.system_id,
        "opportunity_id": seed.opportunity_id,
        "source_snapshot_id": seed.source_snapshot_id,
        "market_context_fingerprint_sha256": seed.market_context_fingerprint_sha256,
        "opportunity_fingerprint_sha256": seed.opportunity_fingerprint_sha256,
        "orchestration_fingerprint_sha256": seed.orchestration_fingerprint_sha256,
        "proposal_id": seed.proposal_id,
        "proposal_fingerprint_sha256": seed.proposal_fingerprint_sha256,
        "local_risk_status": seed.local_risk_status,
        "local_risk_reason_codes": seed.local_risk_reason_codes,
        "local_approved_quantity": seed.local_approved_quantity,
        "local_approved_risk_amount": seed.local_approved_risk_amount,
        "local_approved_notional": seed.local_approved_notional,
        "local_risk_created_at": seed.local_risk_created_at,
        "local_risk_details": seed.local_risk_details,
        "local_risk_decision_fingerprint_sha256": (
            seed.local_risk_decision_fingerprint_sha256
        ),
    }


def master_historical_candidate_seed_fingerprint(seed: MasterHistoricalCandidateSeed) -> str:
    return stable_digest(master_historical_candidate_seed_payload(seed))


@dataclass(frozen=True, slots=True)
class MasterHistoricalCandidateSeed:
    """Locally Risk-authorized historical proposal before any Master reservation exists."""

    master_portfolio_id: str
    plan_id: str
    timeline_id: str
    barrier_sequence: int
    barrier_fingerprint_sha256: str
    observed_at: datetime
    system_id: str
    opportunity_id: str
    source_snapshot_id: str
    market_context_fingerprint_sha256: str
    opportunity_fingerprint_sha256: str
    orchestration_fingerprint_sha256: str
    proposal_id: str
    proposal_fingerprint_sha256: str
    local_risk_status: RiskDecisionStatus
    local_risk_reason_codes: tuple[RiskReasonCode, ...]
    local_approved_quantity: Decimal
    local_approved_risk_amount: Decimal
    local_approved_notional: Decimal
    local_risk_created_at: datetime
    local_risk_details: tuple[tuple[str, str], ...]
    local_risk_decision_fingerprint_sha256: str
    fingerprint_sha256: str
    reservation_required: bool = field(default=True, init=False)
    reservation_id_present: bool = field(default=False, init=False)
    capital_requirement_inferred: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in (
            "master_portfolio_id",
            "plan_id",
            "timeline_id",
            "system_id",
            "opportunity_id",
            "source_snapshot_id",
            "proposal_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        if self.barrier_sequence < 1:
            raise ValueError("historical candidate seed barrier_sequence must be >= 1")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, field_name="observed_at"))
        object.__setattr__(
            self,
            "local_risk_created_at",
            _utc(self.local_risk_created_at, field_name="local_risk_created_at"),
        )
        if self.local_risk_created_at != self.observed_at:
            raise ValueError("historical local Risk decision must be created at CLOSE barrier time")
        if self.local_risk_status not in _LOCAL_AUTHORIZED:
            raise ValueError("historical candidate seed requires locally authorized Risk decision")
        if not self.local_risk_reason_codes:
            raise ValueError("historical candidate seed requires local Risk reason codes")
        if len(set(self.local_risk_reason_codes)) != len(self.local_risk_reason_codes):
            raise ValueError("historical candidate seed local Risk reason codes must be unique")
        for field_name in (
            "local_approved_quantity",
            "local_approved_risk_amount",
            "local_approved_notional",
        ):
            value = _non_negative_decimal(getattr(self, field_name), field_name=field_name)
            if value <= ZERO:
                raise ValueError(f"{field_name} must be > 0 for authorized historical candidate")
        normalized_details = tuple(
            sorted(
                (
                    _required_text(key, field_name="local_risk_details key"),
                    str(value),
                )
                for key, value in self.local_risk_details
            )
        )
        if len({key for key, _ in normalized_details}) != len(normalized_details):
            raise ValueError("historical candidate seed local Risk detail keys must be unique")
        object.__setattr__(self, "local_risk_details", normalized_details)
        for field_name in (
            "barrier_fingerprint_sha256",
            "market_context_fingerprint_sha256",
            "opportunity_fingerprint_sha256",
            "orchestration_fingerprint_sha256",
            "proposal_fingerprint_sha256",
            "local_risk_decision_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical candidate seed schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_historical_candidate_seed_fingerprint(self)
        if normalized != expected:
            raise ValueError("historical candidate seed fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def to_local_risk_decision(self) -> RiskDecision:
        return RiskDecision(
            proposal_id=self.proposal_id,
            status=self.local_risk_status,
            reason_codes=self.local_risk_reason_codes,
            approved_quantity=self.local_approved_quantity,
            approved_risk_amount=self.local_approved_risk_amount,
            approved_notional=self.local_approved_notional,
            created_at=self.local_risk_created_at,
            details=dict(self.local_risk_details),
        )


@dataclass(frozen=True, slots=True)
class HistoricalCrewPreExecutionEvidence:
    """Caller-supplied result of one crew stopped strictly before broker execution."""

    system_id: str
    market_context: object
    opportunity: object | None = None
    orchestration_result: object | None = None
    local_risk_decision: RiskDecision | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        if self.market_context is None:
            raise ValueError("historical pre-execution evidence requires market_context")


def historical_crew_decision_outcome_payload(
    outcome: HistoricalCrewDecisionOutcome,
) -> dict[str, object]:
    return {
        "schema": "money-heist.historical-crew-decision-outcome.v1",
        "schema_version": outcome.schema_version,
        "system_id": outcome.system_id,
        "status": outcome.status,
        "barrier_sequence": outcome.barrier_sequence,
        "barrier_fingerprint_sha256": outcome.barrier_fingerprint_sha256,
        "observed_at": outcome.observed_at,
        "market_context_fingerprint_sha256": outcome.market_context_fingerprint_sha256,
        "opportunity_id": outcome.opportunity_id,
        "opportunity_fingerprint_sha256": outcome.opportunity_fingerprint_sha256,
        "orchestration_status": outcome.orchestration_status,
        "orchestration_fingerprint_sha256": outcome.orchestration_fingerprint_sha256,
        "proposal_id": outcome.proposal_id,
        "proposal_fingerprint_sha256": outcome.proposal_fingerprint_sha256,
        "local_risk_status": outcome.local_risk_status,
        "local_risk_decision_fingerprint_sha256": (
            outcome.local_risk_decision_fingerprint_sha256
        ),
        "candidate_seed_fingerprint_sha256": outcome.candidate_seed_fingerprint_sha256,
        "failure_code": outcome.failure_code,
    }


def historical_crew_decision_outcome_fingerprint(
    outcome: HistoricalCrewDecisionOutcome,
) -> str:
    return stable_digest(historical_crew_decision_outcome_payload(outcome))


@dataclass(frozen=True, slots=True)
class HistoricalCrewDecisionOutcome:
    system_id: str
    status: HistoricalCrewDecisionStatus
    barrier_sequence: int
    barrier_fingerprint_sha256: str
    observed_at: datetime
    market_context_fingerprint_sha256: str
    opportunity_id: str | None
    opportunity_fingerprint_sha256: str | None
    orchestration_status: str | None
    orchestration_fingerprint_sha256: str | None
    proposal_id: str | None
    proposal_fingerprint_sha256: str | None
    local_risk_status: RiskDecisionStatus | None
    local_risk_decision_fingerprint_sha256: str | None
    candidate_seed_fingerprint_sha256: str | None
    failure_code: str | None
    fingerprint_sha256: str
    broker_called: bool = field(default=False, init=False)
    reservation_created: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "system_id",
            _required_text(self.system_id, field_name="system_id"),
        )
        if self.barrier_sequence < 1:
            raise ValueError("historical crew outcome barrier_sequence must be >= 1")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, field_name="observed_at"))
        object.__setattr__(
            self,
            "barrier_fingerprint_sha256",
            _sha256(self.barrier_fingerprint_sha256, field_name="barrier_fingerprint_sha256"),
        )
        object.__setattr__(
            self,
            "market_context_fingerprint_sha256",
            _sha256(
                self.market_context_fingerprint_sha256,
                field_name="market_context_fingerprint_sha256",
            ),
        )
        for field_name in (
            "opportunity_fingerprint_sha256",
            "orchestration_fingerprint_sha256",
            "proposal_fingerprint_sha256",
            "local_risk_decision_fingerprint_sha256",
            "candidate_seed_fingerprint_sha256",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _sha256(value, field_name=field_name))
        for field_name in (
            "opportunity_id",
            "orchestration_status",
            "proposal_id",
            "failure_code",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_text(getattr(self, field_name), field_name=field_name),
            )
        self._validate_shape()
        if self.schema_version != "1.0":
            raise ValueError("unsupported historical crew decision outcome schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = historical_crew_decision_outcome_fingerprint(self)
        if normalized != expected:
            raise ValueError("historical crew decision outcome fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def _validate_shape(self) -> None:
        has_opportunity = self.opportunity_id is not None
        has_orchestration = self.orchestration_status is not None
        has_proposal = self.proposal_id is not None
        has_risk = self.local_risk_status is not None
        has_seed = self.candidate_seed_fingerprint_sha256 is not None
        if self.status is HistoricalCrewDecisionStatus.NO_OPPORTUNITY:
            downstream = (
                has_opportunity,
                self.opportunity_fingerprint_sha256 is not None,
                has_orchestration,
                self.orchestration_fingerprint_sha256 is not None,
                has_proposal,
                self.proposal_fingerprint_sha256 is not None,
                has_risk,
                self.local_risk_decision_fingerprint_sha256 is not None,
                has_seed,
                self.failure_code is not None,
            )
            if any(downstream):
                raise ValueError("NO_OPPORTUNITY outcome cannot carry downstream evidence")
            return
        if not has_opportunity or self.opportunity_fingerprint_sha256 is None:
            raise ValueError("historical crew outcome requires opportunity evidence")
        if not has_orchestration or self.orchestration_fingerprint_sha256 is None:
            raise ValueError("historical crew outcome requires orchestration evidence")
        if self.status in {
            HistoricalCrewDecisionStatus.NO_ANALYSIS,
            HistoricalCrewDecisionStatus.NO_TRADE,
            HistoricalCrewDecisionStatus.ORCHESTRATION_FAILED,
        }:
            if has_proposal or has_risk or has_seed:
                raise ValueError(
                    "terminal orchestration outcome cannot carry Risk or candidate seed"
                )
            if self.proposal_fingerprint_sha256 is not None:
                raise ValueError("terminal orchestration outcome cannot carry proposal fingerprint")
            if self.local_risk_decision_fingerprint_sha256 is not None:
                raise ValueError("terminal orchestration outcome cannot carry Risk fingerprint")
            if (
                self.status is HistoricalCrewDecisionStatus.ORCHESTRATION_FAILED
                and self.failure_code is None
            ):
                raise ValueError("ORCHESTRATION_FAILED outcome requires failure_code")
            if (
                self.status is not HistoricalCrewDecisionStatus.ORCHESTRATION_FAILED
                and self.failure_code is not None
            ):
                raise ValueError("non-failed orchestration outcome cannot carry failure_code")
            return
        if not has_proposal or self.proposal_fingerprint_sha256 is None or not has_risk:
            raise ValueError("local Risk outcome requires proposal and Risk evidence")
        if self.local_risk_decision_fingerprint_sha256 is None:
            raise ValueError("local Risk outcome requires Risk decision fingerprint")
        if self.failure_code is not None:
            raise ValueError("local Risk outcome cannot carry orchestration failure_code")
        if self.status is HistoricalCrewDecisionStatus.LOCAL_RISK_REJECTED:
            if self.local_risk_status is not RiskDecisionStatus.REJECTED or has_seed:
                raise ValueError("LOCAL_RISK_REJECTED requires rejected Risk and no seed")
            return
        if self.status is HistoricalCrewDecisionStatus.LOCAL_RISK_AUTHORIZED:
            if self.local_risk_status not in _LOCAL_AUTHORIZED or not has_seed:
                raise ValueError(
                    "LOCAL_RISK_AUTHORIZED requires authorized Risk and candidate seed"
                )
            return
        raise ValueError(f"unsupported historical crew decision status: {self.status}")


def master_historical_decision_barrier_payload(
    result: MasterHistoricalDecisionBarrier,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-decision-barrier.v1",
        "schema_version": result.schema_version,
        "barrier_result_id": result.barrier_result_id,
        "master_portfolio_id": result.master_portfolio_id,
        "plan_id": result.plan_id,
        "timeline_id": result.timeline_id,
        "status": result.status,
        "barrier_sequence": result.barrier_sequence,
        "barrier_fingerprint_sha256": result.barrier_fingerprint_sha256,
        "observed_at": result.observed_at,
        "plan_fingerprint_sha256": result.plan_fingerprint_sha256,
        "timeline_fingerprint_sha256": result.timeline_fingerprint_sha256,
        "crew_system_ids": result.crew_system_ids,
        "outcomes": [historical_crew_decision_outcome_payload(item) for item in result.outcomes],
        "candidate_seeds": [
            master_historical_candidate_seed_payload(item) for item in result.candidate_seeds
        ],
    }


def master_historical_decision_barrier_fingerprint(
    result: MasterHistoricalDecisionBarrier,
) -> str:
    return stable_digest(master_historical_decision_barrier_payload(result))


@dataclass(frozen=True, slots=True)
class MasterHistoricalDecisionBarrier:
    """Immutable CLOSE-barrier result stopped before reservation, Master admission and broker."""

    barrier_result_id: str
    master_portfolio_id: str
    plan_id: str
    timeline_id: str
    status: MasterHistoricalDecisionBarrierStatus
    barrier_sequence: int
    barrier_fingerprint_sha256: str
    observed_at: datetime
    plan_fingerprint_sha256: str
    timeline_fingerprint_sha256: str
    crew_system_ids: tuple[str, ...]
    outcomes: tuple[HistoricalCrewDecisionOutcome, ...]
    candidate_seeds: tuple[MasterHistoricalCandidateSeed, ...]
    fingerprint_sha256: str
    single_master_capital: bool = field(default=True, init=False)
    sums_branch_equities: bool = field(default=False, init=False)
    local_risk_completed: bool = field(default=True, init=False)
    reservation_required_before_master_gate: bool = field(default=True, init=False)
    mutation_applied: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    broker_called: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in (
            "barrier_result_id",
            "master_portfolio_id",
            "plan_id",
            "timeline_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        if self.status is not MasterHistoricalDecisionBarrierStatus.READY_FOR_RESERVATION:
            raise ValueError("Master historical decision barrier must be READY_FOR_RESERVATION")
        if self.barrier_sequence < 1:
            raise ValueError("Master historical decision barrier sequence must be >= 1")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, field_name="observed_at"))
        for field_name in (
            "barrier_fingerprint_sha256",
            "plan_fingerprint_sha256",
            "timeline_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        normalized_crews = tuple(
            _required_text(system_id, field_name="crew_system_ids")
            for system_id in self.crew_system_ids
        )
        if not normalized_crews:
            raise ValueError("Master historical decision barrier requires crews")
        if normalized_crews != tuple(sorted(normalized_crews)):
            raise ValueError("Master historical decision barrier crews must be sorted")
        if len(set(normalized_crews)) != len(normalized_crews):
            raise ValueError("Master historical decision barrier crews must be unique")
        object.__setattr__(self, "crew_system_ids", normalized_crews)
        if not self.outcomes:
            raise ValueError("Master historical decision barrier requires crew outcomes")
        if self.outcomes != tuple(sorted(self.outcomes, key=lambda item: item.system_id)):
            raise ValueError("Master historical decision barrier outcomes must be sorted")
        outcome_system_ids = tuple(item.system_id for item in self.outcomes)
        if len(set(outcome_system_ids)) != len(outcome_system_ids):
            raise ValueError("Master historical decision barrier outcome crews must be unique")
        if outcome_system_ids != self.crew_system_ids:
            raise ValueError("Master historical decision barrier outcomes must cover every crew")
        if self.candidate_seeds != tuple(
            sorted(self.candidate_seeds, key=lambda item: item.system_id)
        ):
            raise ValueError("Master historical candidate seeds must be sorted")
        seed_system_ids = tuple(item.system_id for item in self.candidate_seeds)
        if len(set(seed_system_ids)) != len(seed_system_ids):
            raise ValueError("Master historical candidate seed crews must be unique")
        expected_seed_ids = tuple(
            item.system_id
            for item in self.outcomes
            if item.status is HistoricalCrewDecisionStatus.LOCAL_RISK_AUTHORIZED
        )
        if seed_system_ids != expected_seed_ids:
            raise ValueError("candidate seeds must match locally authorized crew outcomes")
        for outcome in self.outcomes:
            if outcome.barrier_sequence != self.barrier_sequence:
                raise ValueError("crew outcome barrier sequence does not match barrier result")
            if outcome.barrier_fingerprint_sha256 != self.barrier_fingerprint_sha256:
                raise ValueError("crew outcome barrier fingerprint does not match barrier result")
            if outcome.observed_at != self.observed_at:
                raise ValueError("crew outcome time does not match barrier result")
        for seed in self.candidate_seeds:
            if seed.master_portfolio_id != self.master_portfolio_id:
                raise ValueError("candidate seed Master Portfolio does not match barrier result")
            if seed.plan_id != self.plan_id or seed.timeline_id != self.timeline_id:
                raise ValueError("candidate seed plan/timeline does not match barrier result")
            if seed.barrier_sequence != self.barrier_sequence:
                raise ValueError("candidate seed barrier sequence does not match barrier result")
            if seed.barrier_fingerprint_sha256 != self.barrier_fingerprint_sha256:
                raise ValueError("candidate seed barrier fingerprint does not match barrier result")
            if seed.observed_at != self.observed_at:
                raise ValueError("candidate seed time does not match barrier result")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical decision barrier schema_version")
        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_historical_decision_barrier_fingerprint(self)
        if normalized != expected:
            raise ValueError(
                "Master historical decision barrier fingerprint does not match payload"
            )
        object.__setattr__(self, "fingerprint_sha256", normalized)

    @property
    def authorized_count(self) -> int:
        return len(self.candidate_seeds)

    @property
    def rejected_count(self) -> int:
        return sum(
            item.status is HistoricalCrewDecisionStatus.LOCAL_RISK_REJECTED
            for item in self.outcomes
        )


def _validate_plan_timeline_barrier(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    barrier: MasterHistoricalReplayBarrier,
) -> None:
    if timeline.master_portfolio_id != plan.master_portfolio_id:
        raise ValueError("historical decision timeline Master Portfolio does not match plan")
    if timeline.plan_id != plan.plan_id:
        raise ValueError("historical decision timeline plan_id does not match plan")
    if timeline.plan_fingerprint_sha256 != plan.fingerprint_sha256:
        raise ValueError("historical decision timeline plan fingerprint does not match plan")
    if barrier.phase is not MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE:
        raise ValueError("historical decision barrier requires CANDLE_CLOSE phase")
    if not barrier.decision_eligible:
        raise ValueError("historical decision barrier requires decision-eligible CLOSE")
    if barrier.sequence > len(timeline.barriers):
        raise ValueError("historical decision barrier is not present in timeline")
    source_barrier = timeline.barriers[barrier.sequence - 1]
    if source_barrier != barrier:
        raise ValueError("historical decision barrier does not match exact timeline barrier")
    if barrier.crew_system_ids != timeline.crew_system_ids:
        raise ValueError("historical decision barrier crews do not match timeline")


def _context_fields(
    evidence: HistoricalCrewPreExecutionEvidence,
    *,
    plan: MasterHistoricalReplayPlan,
    barrier: MasterHistoricalReplayBarrier,
) -> tuple[str, str]:
    context = evidence.market_context
    snapshot_id = _required_text(
        getattr(context, "snapshot_id", ""),
        field_name="market_context.snapshot_id",
    )
    symbol = _required_text(getattr(context, "symbol", ""), field_name="market_context.symbol")
    timeframe = _required_text(
        getattr(context, "timeframe", ""),
        field_name="market_context.timeframe",
    )
    observed_at = getattr(context, "observed_at", None)
    if not isinstance(observed_at, datetime):
        raise ValueError("market_context.observed_at must be datetime")
    if _utc(observed_at, field_name="market_context.observed_at") != barrier.observed_at:
        raise ValueError("market context must be observed at exact CLOSE barrier time")
    if symbol != plan.symbol or timeframe != plan.timeframe:
        raise ValueError("market context symbol/timeframe does not match Master replay plan")
    return snapshot_id, _object_fingerprint(context, field_name="market_context")


def _opportunity_fields(
    evidence: HistoricalCrewPreExecutionEvidence,
    *,
    plan: MasterHistoricalReplayPlan,
    snapshot_id: str,
) -> tuple[str, str] | None:
    opportunity = evidence.opportunity
    if opportunity is None:
        return None
    if _required_text(
        getattr(opportunity, "system_id", ""),
        field_name="opportunity.system_id",
    ) != evidence.system_id:
        raise ValueError("historical opportunity system_id does not match evidence crew")
    if _required_text(getattr(opportunity, "symbol", ""), field_name="opportunity.symbol") != (
        plan.symbol
    ):
        raise ValueError("historical opportunity symbol does not match Master replay plan")
    if _required_text(
        getattr(opportunity, "timeframe", ""),
        field_name="opportunity.timeframe",
    ) != plan.timeframe:
        raise ValueError("historical opportunity timeframe does not match Master replay plan")
    if _required_text(
        getattr(opportunity, "snapshot_id", ""),
        field_name="opportunity.snapshot_id",
    ) != snapshot_id:
        raise ValueError("historical opportunity snapshot does not match market context")
    opportunity_id = _required_text(
        getattr(opportunity, "opportunity_id", ""),
        field_name="opportunity.opportunity_id",
    )
    return opportunity_id, _object_fingerprint(opportunity, field_name="opportunity")


def _orchestration_fields(
    evidence: HistoricalCrewPreExecutionEvidence,
    *,
    opportunity_id: str,
    snapshot_id: str,
    plan: MasterHistoricalReplayPlan,
) -> tuple[str, str]:
    result = evidence.orchestration_result
    if result is None:
        raise ValueError("historical opportunity requires orchestration_result")
    status = _enum_text(getattr(result, "status", ""), field_name="orchestration_result.status")
    checks = (
        (
            _required_text(
                getattr(result, "opportunity_id", ""),
                field_name="orchestration_result.opportunity_id",
            )
            == opportunity_id,
            "orchestration opportunity_id does not match opportunity",
        ),
        (
            _required_text(
                getattr(result, "source_snapshot_id", ""),
                field_name="orchestration_result.source_snapshot_id",
            )
            == snapshot_id,
            "orchestration source snapshot does not match market context",
        ),
        (
            _required_text(
                getattr(result, "system_id", ""),
                field_name="orchestration_result.system_id",
            )
            == evidence.system_id,
            "orchestration system_id does not match evidence crew",
        ),
        (
            _required_text(
                getattr(result, "symbol", ""),
                field_name="orchestration_result.symbol",
            )
            == plan.symbol,
            "orchestration symbol does not match Master replay plan",
        ),
    )
    for valid, message in checks:
        if not valid:
            raise ValueError(message)
    return status, _object_fingerprint(result, field_name="orchestration_result")


def _proposal_fields(
    evidence: HistoricalCrewPreExecutionEvidence,
    *,
    opportunity_id: str,
    snapshot_id: str,
    plan: MasterHistoricalReplayPlan,
    barrier: MasterHistoricalReplayBarrier,
) -> tuple[str, str]:
    result = evidence.orchestration_result
    assert result is not None
    proposal = getattr(result, "trade_proposal", None)
    if proposal is None:
        raise ValueError("TRADE_PROPOSAL orchestration requires trade_proposal")
    proposal_id = _required_text(getattr(proposal, "proposal_id", ""), field_name="proposal_id")
    checks = (
        (
            _required_text(
                getattr(proposal, "opportunity_id", ""),
                field_name="proposal.opportunity_id",
            )
            == opportunity_id,
            "proposal opportunity mismatch",
        ),
        (
            _required_text(
                getattr(proposal, "source_snapshot_id", ""),
                field_name="proposal.source_snapshot_id",
            )
            == snapshot_id,
            "proposal snapshot mismatch",
        ),
        (
            _required_text(getattr(proposal, "system_id", ""), field_name="proposal.system_id")
            == evidence.system_id,
            "proposal crew mismatch",
        ),
        (
            _required_text(getattr(proposal, "symbol", ""), field_name="proposal.symbol")
            == plan.symbol,
            "proposal symbol mismatch",
        ),
        (
            _required_text(getattr(proposal, "timeframe", ""), field_name="proposal.timeframe")
            == plan.timeframe,
            "proposal timeframe mismatch",
        ),
    )
    for valid, message in checks:
        if not valid:
            raise ValueError(message)
    created_at = getattr(proposal, "created_at", None)
    if not isinstance(created_at, datetime):
        raise ValueError("historical proposal.created_at must be datetime")
    if _utc(created_at, field_name="proposal.created_at") > barrier.observed_at:
        raise ValueError("historical proposal cannot be created after CLOSE barrier")
    return proposal_id, _object_fingerprint(proposal, field_name="trade_proposal")


def _build_seed(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    barrier: MasterHistoricalReplayBarrier,
    evidence: HistoricalCrewPreExecutionEvidence,
    snapshot_id: str,
    context_fingerprint: str,
    opportunity_id: str,
    opportunity_fingerprint: str,
    orchestration_fingerprint: str,
    proposal_id: str,
    proposal_fingerprint: str,
    decision: RiskDecision,
) -> MasterHistoricalCandidateSeed:
    local_fingerprint = local_risk_decision_fingerprint(
        system_id=evidence.system_id,
        decision=decision,
    )
    details = _risk_details(decision)
    payload = {
        "schema": "money-heist.master-historical-candidate-seed.v1",
        "schema_version": "1.0",
        "master_portfolio_id": plan.master_portfolio_id,
        "plan_id": plan.plan_id,
        "timeline_id": timeline.timeline_id,
        "barrier_sequence": barrier.sequence,
        "barrier_fingerprint_sha256": barrier.fingerprint_sha256,
        "observed_at": barrier.observed_at,
        "system_id": evidence.system_id,
        "opportunity_id": opportunity_id,
        "source_snapshot_id": snapshot_id,
        "market_context_fingerprint_sha256": context_fingerprint,
        "opportunity_fingerprint_sha256": opportunity_fingerprint,
        "orchestration_fingerprint_sha256": orchestration_fingerprint,
        "proposal_id": proposal_id,
        "proposal_fingerprint_sha256": proposal_fingerprint,
        "local_risk_status": decision.status,
        "local_risk_reason_codes": decision.reason_codes,
        "local_approved_quantity": decision.approved_quantity,
        "local_approved_risk_amount": decision.approved_risk_amount,
        "local_approved_notional": decision.approved_notional,
        "local_risk_created_at": decision.created_at,
        "local_risk_details": details,
        "local_risk_decision_fingerprint_sha256": local_fingerprint,
    }
    return MasterHistoricalCandidateSeed(
        master_portfolio_id=plan.master_portfolio_id,
        plan_id=plan.plan_id,
        timeline_id=timeline.timeline_id,
        barrier_sequence=barrier.sequence,
        barrier_fingerprint_sha256=barrier.fingerprint_sha256,
        observed_at=barrier.observed_at,
        system_id=evidence.system_id,
        opportunity_id=opportunity_id,
        source_snapshot_id=snapshot_id,
        market_context_fingerprint_sha256=context_fingerprint,
        opportunity_fingerprint_sha256=opportunity_fingerprint,
        orchestration_fingerprint_sha256=orchestration_fingerprint,
        proposal_id=proposal_id,
        proposal_fingerprint_sha256=proposal_fingerprint,
        local_risk_status=decision.status,
        local_risk_reason_codes=decision.reason_codes,
        local_approved_quantity=decision.approved_quantity,
        local_approved_risk_amount=decision.approved_risk_amount,
        local_approved_notional=decision.approved_notional,
        local_risk_created_at=decision.created_at,
        local_risk_details=details,
        local_risk_decision_fingerprint_sha256=local_fingerprint,
        fingerprint_sha256=stable_digest(payload),
    )


def _outcome(
    *,
    evidence: HistoricalCrewPreExecutionEvidence,
    barrier: MasterHistoricalReplayBarrier,
    status: HistoricalCrewDecisionStatus,
    context_fingerprint: str,
    opportunity_id: str | None = None,
    opportunity_fingerprint: str | None = None,
    orchestration_status: str | None = None,
    orchestration_fingerprint: str | None = None,
    proposal_id: str | None = None,
    proposal_fingerprint: str | None = None,
    local_risk_status: RiskDecisionStatus | None = None,
    local_risk_fingerprint: str | None = None,
    seed_fingerprint: str | None = None,
    failure_code: str | None = None,
) -> HistoricalCrewDecisionOutcome:
    payload = {
        "schema": "money-heist.historical-crew-decision-outcome.v1",
        "schema_version": "1.0",
        "system_id": evidence.system_id,
        "status": status,
        "barrier_sequence": barrier.sequence,
        "barrier_fingerprint_sha256": barrier.fingerprint_sha256,
        "observed_at": barrier.observed_at,
        "market_context_fingerprint_sha256": context_fingerprint,
        "opportunity_id": opportunity_id,
        "opportunity_fingerprint_sha256": opportunity_fingerprint,
        "orchestration_status": orchestration_status,
        "orchestration_fingerprint_sha256": orchestration_fingerprint,
        "proposal_id": proposal_id,
        "proposal_fingerprint_sha256": proposal_fingerprint,
        "local_risk_status": local_risk_status,
        "local_risk_decision_fingerprint_sha256": local_risk_fingerprint,
        "candidate_seed_fingerprint_sha256": seed_fingerprint,
        "failure_code": failure_code,
    }
    return HistoricalCrewDecisionOutcome(
        system_id=evidence.system_id,
        status=status,
        barrier_sequence=barrier.sequence,
        barrier_fingerprint_sha256=barrier.fingerprint_sha256,
        observed_at=barrier.observed_at,
        market_context_fingerprint_sha256=context_fingerprint,
        opportunity_id=opportunity_id,
        opportunity_fingerprint_sha256=opportunity_fingerprint,
        orchestration_status=orchestration_status,
        orchestration_fingerprint_sha256=orchestration_fingerprint,
        proposal_id=proposal_id,
        proposal_fingerprint_sha256=proposal_fingerprint,
        local_risk_status=local_risk_status,
        local_risk_decision_fingerprint_sha256=local_risk_fingerprint,
        candidate_seed_fingerprint_sha256=seed_fingerprint,
        failure_code=failure_code,
        fingerprint_sha256=stable_digest(payload),
    )


def _build_evidence_outcome(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    barrier: MasterHistoricalReplayBarrier,
    evidence: HistoricalCrewPreExecutionEvidence,
) -> tuple[HistoricalCrewDecisionOutcome, MasterHistoricalCandidateSeed | None]:
    snapshot_id, context_fingerprint = _context_fields(
        evidence,
        plan=plan,
        barrier=barrier,
    )
    opportunity_fields = _opportunity_fields(
        evidence,
        plan=plan,
        snapshot_id=snapshot_id,
    )
    if opportunity_fields is None:
        if evidence.orchestration_result is not None or evidence.local_risk_decision is not None:
            raise ValueError("no-opportunity evidence cannot carry orchestration or Risk result")
        return (
            _outcome(
                evidence=evidence,
                barrier=barrier,
                status=HistoricalCrewDecisionStatus.NO_OPPORTUNITY,
                context_fingerprint=context_fingerprint,
            ),
            None,
        )

    opportunity_id, opportunity_fingerprint = opportunity_fields
    orchestration_status, orchestration_fingerprint = _orchestration_fields(
        evidence,
        opportunity_id=opportunity_id,
        snapshot_id=snapshot_id,
        plan=plan,
    )
    if orchestration_status in {"NO_ANALYSIS", "NO_TRADE", "FAILED"}:
        if evidence.local_risk_decision is not None:
            raise ValueError("terminal orchestration result cannot carry local Risk decision")
        if getattr(evidence.orchestration_result, "trade_proposal", None) is not None:
            raise ValueError("terminal orchestration result cannot carry trade_proposal")
        failure = getattr(evidence.orchestration_result, "failure", None)
        if orchestration_status == "FAILED" and failure is None:
            raise ValueError("FAILED orchestration result requires failure evidence")
        if orchestration_status != "FAILED" and failure is not None:
            raise ValueError("non-failed orchestration result cannot carry failure evidence")
        status_map = {
            "NO_ANALYSIS": HistoricalCrewDecisionStatus.NO_ANALYSIS,
            "NO_TRADE": HistoricalCrewDecisionStatus.NO_TRADE,
            "FAILED": HistoricalCrewDecisionStatus.ORCHESTRATION_FAILED,
        }
        failure_code = None
        if orchestration_status == "FAILED":
            assert failure is not None
            failure_code = _enum_text(getattr(failure, "code", ""), field_name="failure.code")
        return (
            _outcome(
                evidence=evidence,
                barrier=barrier,
                status=status_map[orchestration_status],
                context_fingerprint=context_fingerprint,
                opportunity_id=opportunity_id,
                opportunity_fingerprint=opportunity_fingerprint,
                orchestration_status=orchestration_status,
                orchestration_fingerprint=orchestration_fingerprint,
                failure_code=failure_code,
            ),
            None,
        )
    if orchestration_status != "TRADE_PROPOSAL":
        raise ValueError(f"unsupported orchestration status: {orchestration_status}")

    proposal_id, proposal_fingerprint = _proposal_fields(
        evidence,
        opportunity_id=opportunity_id,
        snapshot_id=snapshot_id,
        plan=plan,
        barrier=barrier,
    )
    decision = evidence.local_risk_decision
    if decision is None:
        raise ValueError("TRADE_PROPOSAL evidence requires local Risk decision")
    if decision.proposal_id != proposal_id:
        raise ValueError("local Risk decision proposal_id does not match trade proposal")
    if _utc(decision.created_at, field_name="RiskDecision.created_at") != barrier.observed_at:
        raise ValueError("historical local Risk decision must use exact CLOSE barrier time")
    if not decision.reason_codes:
        raise ValueError("historical local Risk decision requires reason codes")
    if len(set(decision.reason_codes)) != len(decision.reason_codes):
        raise ValueError("historical local Risk reason codes must be unique")
    local_fingerprint = local_risk_decision_fingerprint(
        system_id=evidence.system_id,
        decision=decision,
    )
    if decision.status is RiskDecisionStatus.REJECTED:
        if any(
            value != ZERO
            for value in (
                decision.approved_quantity,
                decision.approved_risk_amount,
                decision.approved_notional,
            )
        ):
            raise ValueError("rejected local Risk decision cannot carry approved amounts")
        return (
            _outcome(
                evidence=evidence,
                barrier=barrier,
                status=HistoricalCrewDecisionStatus.LOCAL_RISK_REJECTED,
                context_fingerprint=context_fingerprint,
                opportunity_id=opportunity_id,
                opportunity_fingerprint=opportunity_fingerprint,
                orchestration_status=orchestration_status,
                orchestration_fingerprint=orchestration_fingerprint,
                proposal_id=proposal_id,
                proposal_fingerprint=proposal_fingerprint,
                local_risk_status=decision.status,
                local_risk_fingerprint=local_fingerprint,
            ),
            None,
        )
    if decision.status not in _LOCAL_AUTHORIZED:
        raise ValueError(f"unsupported local Risk decision status: {decision.status}")

    seed = _build_seed(
        plan=plan,
        timeline=timeline,
        barrier=barrier,
        evidence=evidence,
        snapshot_id=snapshot_id,
        context_fingerprint=context_fingerprint,
        opportunity_id=opportunity_id,
        opportunity_fingerprint=opportunity_fingerprint,
        orchestration_fingerprint=orchestration_fingerprint,
        proposal_id=proposal_id,
        proposal_fingerprint=proposal_fingerprint,
        decision=decision,
    )
    return (
        _outcome(
            evidence=evidence,
            barrier=barrier,
            status=HistoricalCrewDecisionStatus.LOCAL_RISK_AUTHORIZED,
            context_fingerprint=context_fingerprint,
            opportunity_id=opportunity_id,
            opportunity_fingerprint=opportunity_fingerprint,
            orchestration_status=orchestration_status,
            orchestration_fingerprint=orchestration_fingerprint,
            proposal_id=proposal_id,
            proposal_fingerprint=proposal_fingerprint,
            local_risk_status=decision.status,
            local_risk_fingerprint=local_fingerprint,
            seed_fingerprint=seed.fingerprint_sha256,
        ),
        seed,
    )


def build_master_historical_decision_barrier(
    *,
    plan: MasterHistoricalReplayPlan,
    timeline: MasterHistoricalReplayTimeline,
    barrier: MasterHistoricalReplayBarrier,
    crew_evidence: tuple[HistoricalCrewPreExecutionEvidence, ...],
) -> MasterHistoricalDecisionBarrier:
    """Seal all crew pre-execution outcomes at one exact historical CLOSE barrier."""

    _validate_plan_timeline_barrier(plan=plan, timeline=timeline, barrier=barrier)
    if not crew_evidence:
        raise ValueError("historical decision barrier requires crew evidence")
    ordered_evidence = tuple(sorted(crew_evidence, key=lambda item: item.system_id))
    evidence_system_ids = tuple(item.system_id for item in ordered_evidence)
    if len(set(evidence_system_ids)) != len(evidence_system_ids):
        raise ValueError("historical decision barrier crew evidence must be unique")
    if evidence_system_ids != timeline.crew_system_ids:
        raise ValueError("historical decision barrier requires exactly one evidence per crew")

    outcomes: list[HistoricalCrewDecisionOutcome] = []
    seeds: list[MasterHistoricalCandidateSeed] = []
    for evidence in ordered_evidence:
        outcome, seed = _build_evidence_outcome(
            plan=plan,
            timeline=timeline,
            barrier=barrier,
            evidence=evidence,
        )
        outcomes.append(outcome)
        if seed is not None:
            seeds.append(seed)

    identity_payload = {
        "schema": "money-heist.master-historical-decision-barrier-id.v1",
        "master_portfolio_id": plan.master_portfolio_id,
        "plan_id": plan.plan_id,
        "timeline_id": timeline.timeline_id,
        "barrier_sequence": barrier.sequence,
        "barrier_fingerprint_sha256": barrier.fingerprint_sha256,
        "outcome_fingerprints_sha256": [item.fingerprint_sha256 for item in outcomes],
        "candidate_seed_fingerprints_sha256": [item.fingerprint_sha256 for item in seeds],
    }
    barrier_result_id = "master-historical-decision:" + stable_digest(identity_payload)
    payload = {
        "schema": "money-heist.master-historical-decision-barrier.v1",
        "schema_version": "1.0",
        "barrier_result_id": barrier_result_id,
        "master_portfolio_id": plan.master_portfolio_id,
        "plan_id": plan.plan_id,
        "timeline_id": timeline.timeline_id,
        "status": MasterHistoricalDecisionBarrierStatus.READY_FOR_RESERVATION,
        "barrier_sequence": barrier.sequence,
        "barrier_fingerprint_sha256": barrier.fingerprint_sha256,
        "observed_at": barrier.observed_at,
        "plan_fingerprint_sha256": plan.fingerprint_sha256,
        "timeline_fingerprint_sha256": timeline.fingerprint_sha256,
        "crew_system_ids": timeline.crew_system_ids,
        "outcomes": [historical_crew_decision_outcome_payload(item) for item in outcomes],
        "candidate_seeds": [master_historical_candidate_seed_payload(item) for item in seeds],
    }
    return MasterHistoricalDecisionBarrier(
        barrier_result_id=barrier_result_id,
        master_portfolio_id=plan.master_portfolio_id,
        plan_id=plan.plan_id,
        timeline_id=timeline.timeline_id,
        status=MasterHistoricalDecisionBarrierStatus.READY_FOR_RESERVATION,
        barrier_sequence=barrier.sequence,
        barrier_fingerprint_sha256=barrier.fingerprint_sha256,
        observed_at=barrier.observed_at,
        plan_fingerprint_sha256=plan.fingerprint_sha256,
        timeline_fingerprint_sha256=timeline.fingerprint_sha256,
        crew_system_ids=timeline.crew_system_ids,
        outcomes=tuple(outcomes),
        candidate_seeds=tuple(seeds),
        fingerprint_sha256=stable_digest(payload),
    )


__all__ = [
    "HistoricalCrewDecisionOutcome",
    "HistoricalCrewDecisionStatus",
    "HistoricalCrewPreExecutionEvidence",
    "MasterHistoricalCandidateSeed",
    "MasterHistoricalDecisionBarrier",
    "MasterHistoricalDecisionBarrierStatus",
    "build_master_historical_decision_barrier",
    "historical_crew_decision_outcome_fingerprint",
    "master_historical_candidate_seed_fingerprint",
    "master_historical_decision_barrier_fingerprint",
]
