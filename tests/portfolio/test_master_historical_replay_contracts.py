from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

import pytest

from app.portfolio.allocation import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    build_master_allocation_policy,
)
from app.portfolio.arbitration import (
    MasterArbitrationOrderStrategy,
    build_master_arbitration_policy,
)
from app.portfolio.historical_replay import (
    MasterHistoricalReplayMode,
    MasterHistoricalReplayPlanStatus,
    build_master_historical_replay_plan,
)
from app.portfolio.models import PortfolioMemberRef
from app.portfolio.risk_gate import build_master_risk_gate_policy

MASTER_ID = "master-alpha"
START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 1, 5, tzinfo=UTC)
CREATED = datetime(2026, 2, 1, tzinfo=UTC)
CONTENT_SHA = "1" * 64


class Intrabar(StrEnum):
    STOP_FIRST = "STOP_FIRST"
    TARGET_FIRST = "TARGET_FIRST"


@dataclass(frozen=True)
class FakeDataset:
    symbol: str = "BTCUSDC"
    timeframe: str = "1h"
    content_sha256: str = CONTENT_SHA
    source: str = "fixture"
    start_at: datetime = START
    end_at: datetime = END
    candle_count: int = 96

    def canonical_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "content_sha256": self.content_sha256,
            "source": self.source,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "candle_count": self.candle_count,
        }


@dataclass(frozen=True)
class FakeConfig:
    system_id: str
    initial_balance: Decimal
    risk_version: str = "risk-v1"
    feature_version: str = "feature-v1"
    execution_model_version: str = "historical-ohlc-v1"
    maker_fee_bps: Decimal = Decimal("1")
    taker_fee_bps: Decimal = Decimal("2")
    market_slippage_bps: Decimal = Decimal("0.5")
    intrabar_policy: Intrabar = Intrabar.STOP_FIRST

    def canonical_payload(self) -> dict[str, object]:
        return {
            "system_id": self.system_id,
            "initial_balance": self.initial_balance,
            "risk_version": self.risk_version,
            "feature_version": self.feature_version,
            "execution_model_version": self.execution_model_version,
            "maker_fee_bps": self.maker_fee_bps,
            "taker_fee_bps": self.taker_fee_bps,
            "market_slippage_bps": self.market_slippage_bps,
            "intrabar_policy": self.intrabar_policy,
        }


@dataclass(frozen=True)
class FakeRun:
    run_id: str
    dataset: object
    config: object
    period_start: datetime = START
    period_end: datetime = END


def _allocation(*, configured: bool = True, master_id: str = MASTER_ID):
    members = (
        PortfolioMemberRef(system_id="crew-a"),
        PortfolioMemberRef(system_id="crew-b"),
    )
    if configured:
        envelopes = tuple(
            CrewAllocationEnvelope(
                system_id=member.system_id,
                status=AllocationEnvelopeStatus.CONFIGURED,
                capital_ceiling_amount=Decimal("70"),
                open_risk_ceiling_amount=Decimal("10"),
                gross_exposure_ceiling_amount=Decimal("100"),
            )
            for member in members
        )
    else:
        envelopes = tuple(
            CrewAllocationEnvelope(
                system_id=member.system_id,
                status=AllocationEnvelopeStatus.NOT_CONFIGURED,
                reason_code="operator-required",
            )
            for member in members
        )
    return build_master_allocation_policy(
        master_portfolio_id=master_id,
        policy_id="allocation-v1",
        members=members,
        envelopes=envelopes,
    )


def _policies(*, allocation=None):
    allocation = allocation or _allocation()
    gate = build_master_risk_gate_policy(
        master_portfolio_id=allocation.master_portfolio_id,
        gate_policy_id="gate-v1",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        max_total_open_risk_amount=Decimal("20"),
        max_total_gross_exposure_amount=Decimal("150"),
    )
    arbitration = build_master_arbitration_policy(
        master_portfolio_id=allocation.master_portfolio_id,
        arbitration_policy_id="arb-v1",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        order_strategy=MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST,
    )
    return allocation, gate, arbitration


def _runs() -> tuple[FakeRun, FakeRun]:
    dataset = FakeDataset()
    return (
        FakeRun(
            run_id="run-a",
            dataset=dataset,
            config=FakeConfig(
                system_id="crew-a",
                initial_balance=Decimal("100"),
                risk_version="risk-a",
                feature_version="feature-a",
            ),
        ),
        FakeRun(
            run_id="run-b",
            dataset=dataset,
            config=FakeConfig(
                system_id="crew-b",
                initial_balance=Decimal("250"),
                risk_version="risk-b",
                feature_version="feature-b",
            ),
        ),
    )


def _build(*, runs=None, capital=Decimal("80"), created_at=CREATED, policies=None):
    allocation, gate, arbitration = policies or _policies()
    return build_master_historical_replay_plan(
        master_portfolio_id=MASTER_ID,
        master_initial_capital=capital,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        backtest_runs=_runs() if runs is None else runs,
        created_at=created_at,
    )


def test_builds_ready_single_dataset_plan() -> None:
    plan = _build()
    assert plan.status is MasterHistoricalReplayPlanStatus.READY
    assert plan.mode is MasterHistoricalReplayMode.COORDINATED_SINGLE_DATASET_V1
    assert plan.master_initial_capital == Decimal("80")
    assert tuple(crew.system_id for crew in plan.crews) == ("crew-a", "crew-b")


def test_branch_balances_are_provenance_not_master_capital() -> None:
    plan = _build(capital=Decimal("37"))
    assert tuple(crew.source_branch_initial_balance for crew in plan.crews) == (
        Decimal("100"),
        Decimal("250"),
    )
    assert plan.master_initial_capital == Decimal("37")
    assert plan.sums_branch_equities is False
    assert plan.branch_initial_balance_is_master_capital is False
    assert all(crew.branch_equity_summable is False for crew in plan.crews)


def test_plan_has_no_risk_broker_or_live_authority() -> None:
    plan = _build()
    assert plan.risk_authority is False
    assert plan.admission_authority is False
    assert plan.reservation_mutation is False
    assert plan.broker_authority is False
    assert plan.registry_mutation is False
    assert plan.live_authority is False
    assert plan.auto_execute is False


def test_input_run_order_does_not_change_plan() -> None:
    runs = _runs()
    first = _build(runs=runs)
    second = _build(runs=tuple(reversed(runs)))
    assert first.fingerprint_sha256 == second.fingerprint_sha256


def test_created_at_is_part_of_plan_identity() -> None:
    first = _build()
    second = _build(created_at=CREATED + timedelta(seconds=1))
    assert first.plan_id != second.plan_id
    assert first.fingerprint_sha256 != second.fingerprint_sha256


def test_different_crew_configs_are_preserved_independently() -> None:
    plan = _build()
    assert plan.crews[0].config_fingerprint_sha256 != plan.crews[1].config_fingerprint_sha256


def test_duplicate_backtest_run_id_rejected() -> None:
    first, second = _runs()
    with pytest.raises(ValueError, match="BacktestRun IDs must be unique"):
        _build(runs=(first, replace(second, run_id=first.run_id)))


def test_missing_allocation_member_rejected() -> None:
    with pytest.raises(ValueError, match="membership exactly"):
        _build(runs=(_runs()[0],))


def test_duplicate_system_rejected() -> None:
    first, second = _runs()
    duplicated = replace(second, config=replace(second.config, system_id="crew-a"))
    with pytest.raises(ValueError, match="membership exactly"):
        _build(runs=(first, duplicated))


def test_dataset_mismatch_rejected() -> None:
    first, second = _runs()
    changed = replace(second, dataset=replace(second.dataset, candle_count=95))
    with pytest.raises(ValueError, match="exact shared DatasetRef"):
        _build(runs=(first, changed))


def test_dataset_content_mismatch_rejected() -> None:
    first, second = _runs()
    changed = replace(second, dataset=replace(second.dataset, content_sha256="2" * 64))
    with pytest.raises(ValueError, match="exact shared DatasetRef"):
        _build(runs=(first, changed))


def test_period_start_mismatch_rejected() -> None:
    first, second = _runs()
    changed = replace(second, period_start=START + timedelta(hours=1))
    with pytest.raises(ValueError, match="exact shared period"):
        _build(runs=(first, changed))


def test_period_end_mismatch_rejected() -> None:
    first, second = _runs()
    changed = replace(second, period_end=END - timedelta(hours=1))
    with pytest.raises(ValueError, match="exact shared period"):
        _build(runs=(first, changed))


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("execution_model_version", "other-model"),
        ("maker_fee_bps", Decimal("3")),
        ("taker_fee_bps", Decimal("4")),
        ("market_slippage_bps", Decimal("1.5")),
        ("intrabar_policy", Intrabar.TARGET_FIRST),
    ],
)
def test_execution_environment_mismatch_rejected(field_name: str, value: object) -> None:
    first, second = _runs()
    changed_config = replace(second.config, **{field_name: value})
    with pytest.raises(ValueError, match="shared execution environment"):
        _build(runs=(first, replace(second, config=changed_config)))


def test_unconfigured_allocation_policy_rejected() -> None:
    allocation = _allocation(configured=False)
    _, gate, arbitration = _policies(allocation=allocation)
    with pytest.raises(ValueError, match="CONFIGURED allocation policy"):
        _build(policies=(allocation, gate, arbitration))


def test_unconfigured_gate_policy_rejected() -> None:
    allocation = _allocation()
    gate = build_master_risk_gate_policy(
        master_portfolio_id=MASTER_ID,
        gate_policy_id="gate-off",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        reason_code="operator-required",
    )
    arbitration = _policies(allocation=allocation)[2]
    with pytest.raises(ValueError, match="CONFIGURED Master Risk Gate"):
        _build(policies=(allocation, gate, arbitration))


def test_unconfigured_arbitration_policy_rejected() -> None:
    allocation, gate, _ = _policies()
    arbitration = build_master_arbitration_policy(
        master_portfolio_id=MASTER_ID,
        arbitration_policy_id="arb-off",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        reason_code="operator-required",
    )
    with pytest.raises(ValueError, match="CONFIGURED arbitration"):
        _build(policies=(allocation, gate, arbitration))


def test_master_portfolio_id_mismatch_rejected() -> None:
    allocation = _allocation(master_id="other-master")
    _, gate, arbitration = _policies(allocation=allocation)
    with pytest.raises(ValueError, match="share master_portfolio_id"):
        _build(policies=(allocation, gate, arbitration))


def test_gate_allocation_provenance_mismatch_rejected() -> None:
    allocation = _allocation()
    gate = build_master_risk_gate_policy(
        master_portfolio_id=MASTER_ID,
        gate_policy_id="gate-wrong",
        allocation_policy_fingerprint_sha256="a" * 64,
        max_total_open_risk_amount=Decimal("20"),
        max_total_gross_exposure_amount=Decimal("150"),
    )
    arbitration = _policies(allocation=allocation)[2]
    with pytest.raises(ValueError, match="does not bind to allocation"):
        _build(policies=(allocation, gate, arbitration))


def test_arbitration_allocation_provenance_mismatch_rejected() -> None:
    allocation, gate, _ = _policies()
    arbitration = build_master_arbitration_policy(
        master_portfolio_id=MASTER_ID,
        arbitration_policy_id="arb-wrong",
        allocation_policy_fingerprint_sha256="b" * 64,
        order_strategy=MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST,
    )
    with pytest.raises(ValueError, match="does not bind to allocation"):
        _build(policies=(allocation, gate, arbitration))


def test_empty_runs_rejected() -> None:
    with pytest.raises(ValueError, match="at least one BacktestRun"):
        _build(runs=())


@pytest.mark.parametrize("capital", [Decimal("0"), Decimal("-1"), Decimal("NaN")])
def test_invalid_master_capital_rejected(capital: Decimal) -> None:
    with pytest.raises(ValueError, match="master_initial_capital"):
        _build(capital=capital)


def test_naive_created_at_rejected() -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        _build(created_at=datetime(2026, 2, 1))


def test_invalid_source_branch_balance_rejected() -> None:
    first, second = _runs()
    changed = replace(first, config=replace(first.config, initial_balance=Decimal("0")))
    with pytest.raises(ValueError, match="BacktestConfig.initial_balance"):
        _build(runs=(changed, second))


def test_dataset_requires_canonical_payload() -> None:
    first, second = _runs()
    changed = replace(first, dataset=object())
    with pytest.raises(ValueError, match="canonical_payload"):
        _build(runs=(changed, second))


def test_config_requires_canonical_payload() -> None:
    first, second = _runs()

    @dataclass(frozen=True)
    class BadConfig:
        system_id: str = "crew-a"
        initial_balance: Decimal = Decimal("100")

    changed = replace(first, config=BadConfig())
    with pytest.raises(ValueError, match="canonical_payload"):
        _build(runs=(changed, second))
