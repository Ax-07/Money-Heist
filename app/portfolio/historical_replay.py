from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from app.services.backtest.ids import stable_digest

from .allocation import AllocationEnvelopeStatus, MasterAllocationPolicy
from .arbitration import (
    MasterArbitrationPolicy,
    MasterArbitrationPolicyStatus,
)
from .risk_gate import MasterRiskGatePolicy, MasterRiskGatePolicyStatus

ZERO = Decimal("0")


class BacktestRunLike(Protocol):
    run_id: str
    dataset: Any
    config: Any
    period_start: datetime
    period_end: datetime


class MasterHistoricalReplayPlanStatus(StrEnum):
    READY = "READY"


class MasterHistoricalReplayMode(StrEnum):
    COORDINATED_SINGLE_DATASET_V1 = "COORDINATED_SINGLE_DATASET_V1"


def _required_text(value: str, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
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


def _positive_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= ZERO:
        raise ValueError(f"{field_name} must be a finite Decimal > 0")
    return value


def _non_negative_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < ZERO:
        raise ValueError(f"{field_name} must be a finite Decimal >= 0")
    return value


def _canonical_payload(value: Any, *, field_name: str) -> dict[str, object]:
    method = getattr(value, "canonical_payload", None)
    if not callable(method):
        raise ValueError(f"{field_name} must expose canonical_payload()")
    payload = method()
    if not isinstance(payload, dict):
        raise ValueError(f"{field_name}.canonical_payload() must return dict")
    return payload


def _enum_text(value: Any, *, field_name: str) -> str:
    raw = getattr(value, "value", value)
    return _required_text(str(raw), field_name=field_name)


def master_historical_replay_crew_payload(
    crew: MasterHistoricalReplayCrewRef,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-replay-crew.v1",
        "schema_version": crew.schema_version,
        "system_id": crew.system_id,
        "backtest_run_id": crew.backtest_run_id,
        "dataset_fingerprint_sha256": crew.dataset_fingerprint_sha256,
        "dataset_content_sha256": crew.dataset_content_sha256,
        "config_fingerprint_sha256": crew.config_fingerprint_sha256,
        "source_branch_initial_balance": crew.source_branch_initial_balance,
        "period_start": crew.period_start,
        "period_end": crew.period_end,
    }


def master_historical_replay_crew_fingerprint(
    crew: MasterHistoricalReplayCrewRef,
) -> str:
    return stable_digest(master_historical_replay_crew_payload(crew))


@dataclass(frozen=True, slots=True)
class MasterHistoricalReplayCrewRef:
    """One source BacktestRun binding; its branch balance is provenance, never Master cash."""

    system_id: str
    backtest_run_id: str
    dataset_fingerprint_sha256: str
    dataset_content_sha256: str
    config_fingerprint_sha256: str
    source_branch_initial_balance: Decimal
    period_start: datetime
    period_end: datetime
    fingerprint_sha256: str
    branch_capital_authority: bool = field(default=False, init=False)
    branch_equity_summable: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in ("system_id", "backtest_run_id"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "dataset_fingerprint_sha256",
            "dataset_content_sha256",
            "config_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "source_branch_initial_balance",
            _positive_decimal(
                self.source_branch_initial_balance,
                field_name="source_branch_initial_balance",
            ),
        )
        object.__setattr__(self, "period_start", _utc(self.period_start, field_name="period_start"))
        object.__setattr__(self, "period_end", _utc(self.period_end, field_name="period_end"))
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot precede period_start")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical replay crew schema_version")

        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_historical_replay_crew_fingerprint(self)
        if normalized != expected:
            raise ValueError("Master historical replay crew fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def master_historical_replay_plan_payload(
    plan: MasterHistoricalReplayPlan,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-replay-plan.v1",
        "schema_version": plan.schema_version,
        "plan_id": plan.plan_id,
        "master_portfolio_id": plan.master_portfolio_id,
        "created_at": plan.created_at,
        "status": plan.status,
        "mode": plan.mode,
        "master_initial_capital": plan.master_initial_capital,
        "dataset_fingerprint_sha256": plan.dataset_fingerprint_sha256,
        "dataset_content_sha256": plan.dataset_content_sha256,
        "symbol": plan.symbol,
        "timeframe": plan.timeframe,
        "period_start": plan.period_start,
        "period_end": plan.period_end,
        "execution_model_version": plan.execution_model_version,
        "maker_fee_bps": plan.maker_fee_bps,
        "taker_fee_bps": plan.taker_fee_bps,
        "market_slippage_bps": plan.market_slippage_bps,
        "intrabar_policy": plan.intrabar_policy,
        "allocation_policy_fingerprint_sha256": plan.allocation_policy_fingerprint_sha256,
        "gate_policy_fingerprint_sha256": plan.gate_policy_fingerprint_sha256,
        "arbitration_policy_fingerprint_sha256": plan.arbitration_policy_fingerprint_sha256,
        "crews": [master_historical_replay_crew_payload(crew) for crew in plan.crews],
    }


def master_historical_replay_plan_fingerprint(plan: MasterHistoricalReplayPlan) -> str:
    return stable_digest(master_historical_replay_plan_payload(plan))


@dataclass(frozen=True, slots=True)
class MasterHistoricalReplayPlan:
    """Immutable coordinated replay plan with one explicit physical Master capital truth."""

    plan_id: str
    master_portfolio_id: str
    created_at: datetime
    status: MasterHistoricalReplayPlanStatus
    mode: MasterHistoricalReplayMode
    master_initial_capital: Decimal
    dataset_fingerprint_sha256: str
    dataset_content_sha256: str
    symbol: str
    timeframe: str
    period_start: datetime
    period_end: datetime
    execution_model_version: str
    maker_fee_bps: Decimal
    taker_fee_bps: Decimal
    market_slippage_bps: Decimal
    intrabar_policy: str
    allocation_policy_fingerprint_sha256: str
    gate_policy_fingerprint_sha256: str
    arbitration_policy_fingerprint_sha256: str
    crews: tuple[MasterHistoricalReplayCrewRef, ...]
    fingerprint_sha256: str
    single_master_capital: bool = field(default=True, init=False)
    sums_branch_equities: bool = field(default=False, init=False)
    branch_initial_balance_is_master_capital: bool = field(default=False, init=False)
    source_runners_are_single_system: bool = field(default=True, init=False)
    mutation_applied: bool = field(default=False, init=False)
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    registry_mutation: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field_name in (
            "plan_id",
            "master_portfolio_id",
            "symbol",
            "timeframe",
            "execution_model_version",
            "intrabar_policy",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(self, "created_at", _utc(self.created_at, field_name="created_at"))
        object.__setattr__(self, "period_start", _utc(self.period_start, field_name="period_start"))
        object.__setattr__(self, "period_end", _utc(self.period_end, field_name="period_end"))
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot precede period_start")
        object.__setattr__(
            self,
            "master_initial_capital",
            _positive_decimal(self.master_initial_capital, field_name="master_initial_capital"),
        )
        for field_name in ("maker_fee_bps", "taker_fee_bps", "market_slippage_bps"):
            object.__setattr__(
                self,
                field_name,
                _non_negative_decimal(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "dataset_fingerprint_sha256",
            "dataset_content_sha256",
            "allocation_policy_fingerprint_sha256",
            "gate_policy_fingerprint_sha256",
            "arbitration_policy_fingerprint_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha256(getattr(self, field_name), field_name=field_name),
            )
        if self.status is not MasterHistoricalReplayPlanStatus.READY:
            raise ValueError("Master historical replay plan status must be READY")
        if self.mode is not MasterHistoricalReplayMode.COORDINATED_SINGLE_DATASET_V1:
            raise ValueError("unsupported Master historical replay mode")
        if not self.crews:
            raise ValueError("Master historical replay plan requires at least one crew")
        expected_order = tuple(sorted(self.crews, key=lambda item: item.system_id))
        if self.crews != expected_order:
            raise ValueError("Master historical replay crews must be sorted by system_id")
        system_ids = tuple(crew.system_id for crew in self.crews)
        if len(set(system_ids)) != len(system_ids):
            raise ValueError("Master historical replay crew system_id values must be unique")
        run_ids = tuple(crew.backtest_run_id for crew in self.crews)
        if len(set(run_ids)) != len(run_ids):
            raise ValueError("Master historical replay backtest_run_id values must be unique")
        for crew in self.crews:
            if crew.dataset_fingerprint_sha256 != self.dataset_fingerprint_sha256:
                raise ValueError("crew dataset fingerprint must match Master replay dataset")
            if crew.dataset_content_sha256 != self.dataset_content_sha256:
                raise ValueError("crew dataset content must match Master replay dataset")
            if crew.period_start != self.period_start or crew.period_end != self.period_end:
                raise ValueError("crew replay period must match Master replay period")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical replay plan schema_version")

        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_historical_replay_plan_fingerprint(self)
        if normalized != expected:
            raise ValueError("Master historical replay plan fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)


def _build_crew_ref(run: BacktestRunLike) -> MasterHistoricalReplayCrewRef:
    run_id = _required_text(run.run_id, field_name="BacktestRun.run_id")
    system_id = _required_text(run.config.system_id, field_name="BacktestConfig.system_id")
    dataset_payload = _canonical_payload(run.dataset, field_name="BacktestRun.dataset")
    config_payload = _canonical_payload(run.config, field_name="BacktestRun.config")
    dataset_fingerprint = stable_digest(dataset_payload)
    content_sha = _sha256(
        run.dataset.content_sha256,
        field_name="DatasetRef.content_sha256",
    )
    initial_balance = _positive_decimal(
        run.config.initial_balance,
        field_name="BacktestConfig.initial_balance",
    )
    period_start = _utc(run.period_start, field_name="BacktestRun.period_start")
    period_end = _utc(run.period_end, field_name="BacktestRun.period_end")
    payload = {
        "schema": "money-heist.master-historical-replay-crew.v1",
        "schema_version": "1.0",
        "system_id": system_id,
        "backtest_run_id": run_id,
        "dataset_fingerprint_sha256": dataset_fingerprint,
        "dataset_content_sha256": content_sha,
        "config_fingerprint_sha256": stable_digest(config_payload),
        "source_branch_initial_balance": initial_balance,
        "period_start": period_start,
        "period_end": period_end,
    }
    return MasterHistoricalReplayCrewRef(
        system_id=system_id,
        backtest_run_id=run_id,
        dataset_fingerprint_sha256=dataset_fingerprint,
        dataset_content_sha256=content_sha,
        config_fingerprint_sha256=stable_digest(config_payload),
        source_branch_initial_balance=initial_balance,
        period_start=period_start,
        period_end=period_end,
        fingerprint_sha256=stable_digest(payload),
    )


def _execution_environment(run: BacktestRunLike) -> tuple[object, ...]:
    config = run.config
    return (
        _required_text(config.execution_model_version, field_name="execution_model_version"),
        _non_negative_decimal(config.maker_fee_bps, field_name="maker_fee_bps"),
        _non_negative_decimal(config.taker_fee_bps, field_name="taker_fee_bps"),
        _non_negative_decimal(config.market_slippage_bps, field_name="market_slippage_bps"),
        _enum_text(config.intrabar_policy, field_name="intrabar_policy"),
    )


def build_master_historical_replay_plan(
    *,
    master_portfolio_id: str,
    master_initial_capital: Decimal,
    allocation_policy: MasterAllocationPolicy,
    gate_policy: MasterRiskGatePolicy,
    arbitration_policy: MasterArbitrationPolicy,
    backtest_runs: Sequence[BacktestRunLike],
    created_at: datetime,
) -> MasterHistoricalReplayPlan:
    """Bind synchronized single-system BacktestRuns into one shared-capital Master replay plan."""

    master_id = _required_text(master_portfolio_id, field_name="master_portfolio_id")
    master_capital = _positive_decimal(
        master_initial_capital,
        field_name="master_initial_capital",
    )
    normalized_created_at = _utc(created_at, field_name="created_at")
    runs = tuple(backtest_runs)
    if not runs:
        raise ValueError("Master historical replay requires at least one BacktestRun")

    if allocation_policy.status is not AllocationEnvelopeStatus.CONFIGURED:
        raise ValueError("Master historical replay requires CONFIGURED allocation policy")
    if gate_policy.status is not MasterRiskGatePolicyStatus.CONFIGURED:
        raise ValueError("Master historical replay requires CONFIGURED Master Risk Gate policy")
    if arbitration_policy.status is not MasterArbitrationPolicyStatus.CONFIGURED:
        raise ValueError("Master historical replay requires CONFIGURED arbitration policy")
    if any(
        policy_id != master_id
        for policy_id in (
            allocation_policy.master_portfolio_id,
            gate_policy.master_portfolio_id,
            arbitration_policy.master_portfolio_id,
        )
    ):
        raise ValueError("Master historical replay policies must share master_portfolio_id")
    if gate_policy.allocation_policy_fingerprint_sha256 != allocation_policy.fingerprint_sha256:
        raise ValueError("Master Risk Gate policy does not bind to allocation policy")
    if (
        arbitration_policy.allocation_policy_fingerprint_sha256
        != allocation_policy.fingerprint_sha256
    ):
        raise ValueError("arbitration policy does not bind to allocation policy")

    crews = tuple(sorted((_build_crew_ref(run) for run in runs), key=lambda item: item.system_id))
    member_ids = tuple(member.system_id for member in allocation_policy.members)
    crew_ids = tuple(crew.system_id for crew in crews)
    if crew_ids != member_ids:
        raise ValueError("BacktestRun systems must match allocation policy membership exactly")
    if len(set(crew.backtest_run_id for crew in crews)) != len(crews):
        raise ValueError("Master historical replay BacktestRun IDs must be unique")

    run_by_system = {run.config.system_id: run for run in runs}
    first_run = run_by_system[crews[0].system_id]
    dataset_payload = _canonical_payload(first_run.dataset, field_name="BacktestRun.dataset")
    dataset_fingerprint = stable_digest(dataset_payload)
    dataset_content_sha = _sha256(
        first_run.dataset.content_sha256,
        field_name="DatasetRef.content_sha256",
    )
    symbol = _required_text(first_run.dataset.symbol, field_name="DatasetRef.symbol")
    timeframe = _required_text(first_run.dataset.timeframe, field_name="DatasetRef.timeframe")
    period_start = _utc(first_run.period_start, field_name="BacktestRun.period_start")
    period_end = _utc(first_run.period_end, field_name="BacktestRun.period_end")
    environment = _execution_environment(first_run)

    for crew in crews:
        run = run_by_system[crew.system_id]
        if stable_digest(_canonical_payload(run.dataset, field_name="BacktestRun.dataset")) != (
            dataset_fingerprint
        ):
            raise ValueError("V1 Master historical replay requires one exact shared DatasetRef")
        if _utc(run.period_start, field_name="BacktestRun.period_start") != period_start or _utc(
            run.period_end,
            field_name="BacktestRun.period_end",
        ) != period_end:
            raise ValueError("V1 Master historical replay requires one exact shared period")
        if _execution_environment(run) != environment:
            raise ValueError(
                "V1 Master historical replay requires one shared execution environment"
            )

    execution_model_version, maker_fee, taker_fee, slippage, intrabar_policy = environment
    assert isinstance(execution_model_version, str)
    assert isinstance(maker_fee, Decimal)
    assert isinstance(taker_fee, Decimal)
    assert isinstance(slippage, Decimal)
    assert isinstance(intrabar_policy, str)

    identity_payload = {
        "schema": "money-heist.master-historical-replay-plan-id.v1",
        "master_portfolio_id": master_id,
        "created_at": normalized_created_at,
        "master_initial_capital": master_capital,
        "dataset_fingerprint_sha256": dataset_fingerprint,
        "period_start": period_start,
        "period_end": period_end,
        "allocation_policy_fingerprint_sha256": allocation_policy.fingerprint_sha256,
        "gate_policy_fingerprint_sha256": gate_policy.fingerprint_sha256,
        "arbitration_policy_fingerprint_sha256": arbitration_policy.fingerprint_sha256,
        "crew_fingerprints_sha256": [crew.fingerprint_sha256 for crew in crews],
    }
    plan_id = "master-replay:" + stable_digest(identity_payload)
    payload = {
        "schema": "money-heist.master-historical-replay-plan.v1",
        "schema_version": "1.0",
        "plan_id": plan_id,
        "master_portfolio_id": master_id,
        "created_at": normalized_created_at,
        "status": MasterHistoricalReplayPlanStatus.READY,
        "mode": MasterHistoricalReplayMode.COORDINATED_SINGLE_DATASET_V1,
        "master_initial_capital": master_capital,
        "dataset_fingerprint_sha256": dataset_fingerprint,
        "dataset_content_sha256": dataset_content_sha,
        "symbol": symbol,
        "timeframe": timeframe,
        "period_start": period_start,
        "period_end": period_end,
        "execution_model_version": execution_model_version,
        "maker_fee_bps": maker_fee,
        "taker_fee_bps": taker_fee,
        "market_slippage_bps": slippage,
        "intrabar_policy": intrabar_policy,
        "allocation_policy_fingerprint_sha256": allocation_policy.fingerprint_sha256,
        "gate_policy_fingerprint_sha256": gate_policy.fingerprint_sha256,
        "arbitration_policy_fingerprint_sha256": arbitration_policy.fingerprint_sha256,
        "crews": [master_historical_replay_crew_payload(crew) for crew in crews],
    }
    return MasterHistoricalReplayPlan(
        plan_id=plan_id,
        master_portfolio_id=master_id,
        created_at=normalized_created_at,
        status=MasterHistoricalReplayPlanStatus.READY,
        mode=MasterHistoricalReplayMode.COORDINATED_SINGLE_DATASET_V1,
        master_initial_capital=master_capital,
        dataset_fingerprint_sha256=dataset_fingerprint,
        dataset_content_sha256=dataset_content_sha,
        symbol=symbol,
        timeframe=timeframe,
        period_start=period_start,
        period_end=period_end,
        execution_model_version=execution_model_version,
        maker_fee_bps=maker_fee,
        taker_fee_bps=taker_fee,
        market_slippage_bps=slippage,
        intrabar_policy=intrabar_policy,
        allocation_policy_fingerprint_sha256=allocation_policy.fingerprint_sha256,
        gate_policy_fingerprint_sha256=gate_policy.fingerprint_sha256,
        arbitration_policy_fingerprint_sha256=arbitration_policy.fingerprint_sha256,
        crews=crews,
        fingerprint_sha256=stable_digest(payload),
    )


__all__ = [
    "BacktestRunLike",
    "MasterHistoricalReplayCrewRef",
    "MasterHistoricalReplayMode",
    "MasterHistoricalReplayPlan",
    "MasterHistoricalReplayPlanStatus",
    "build_master_historical_replay_plan",
    "master_historical_replay_crew_fingerprint",
    "master_historical_replay_plan_fingerprint",
]
