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
from app.portfolio.historical_replay import build_master_historical_replay_plan
from app.portfolio.historical_replay_coordinator import (
    MasterHistoricalReplayBarrierPhase,
    MasterHistoricalReplayCoordinator,
    MasterHistoricalReplayTimelineStatus,
    build_master_historical_replay_timeline,
)
from app.portfolio.models import PortfolioMemberRef
from app.portfolio.risk_gate import build_master_risk_gate_policy
from app.services.backtest.dataset import DatasetRef
from app.services.backtest.ids import stable_digest

MASTER_ID = "master-alpha"
BASE = datetime(2026, 1, 1, tzinfo=UTC)


class Intrabar(StrEnum):
    STOP_FIRST = "STOP_FIRST"


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
    period_start: datetime
    period_end: datetime


def _candle(index: int, *, hours: int = 1, is_closed: bool = True) -> dict[str, object]:
    open_at = BASE + timedelta(hours=index)
    close_at = open_at + timedelta(hours=hours)
    price = Decimal("100") + Decimal(index)
    return {
        "symbol": "BTCUSDC",
        "timeframe": "1h",
        "open_time": open_at,
        "close_time": close_at,
        "open": price,
        "high": price + Decimal("2"),
        "low": price - Decimal("2"),
        "close": price + Decimal("1"),
        "volume": Decimal("10"),
        "is_closed": is_closed,
    }


def _candles() -> tuple[dict[str, object], ...]:
    return tuple(_candle(index) for index in range(4))


def _dataset(candles=None) -> DatasetRef:
    return DatasetRef.from_candles(
        _candles() if candles is None else candles,
        symbol="BTCUSDC",
        timeframe="1h",
        source="fixture",
    )


def _allocation():
    members = (
        PortfolioMemberRef(system_id="crew-a"),
        PortfolioMemberRef(system_id="crew-b"),
    )
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
    return build_master_allocation_policy(
        master_portfolio_id=MASTER_ID,
        policy_id="allocation-v1",
        members=members,
        envelopes=envelopes,
    )


def _plan(
    *,
    dataset=None,
    period_start=BASE + timedelta(hours=2),
    period_end=BASE + timedelta(hours=4),
    capital=Decimal("80"),
):
    dataset = dataset or _dataset()
    allocation = _allocation()
    gate = build_master_risk_gate_policy(
        master_portfolio_id=MASTER_ID,
        gate_policy_id="gate-v1",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        max_total_open_risk_amount=Decimal("20"),
        max_total_gross_exposure_amount=Decimal("150"),
    )
    arbitration = build_master_arbitration_policy(
        master_portfolio_id=MASTER_ID,
        arbitration_policy_id="arb-v1",
        allocation_policy_fingerprint_sha256=allocation.fingerprint_sha256,
        order_strategy=MasterArbitrationOrderStrategy.FIFO_RESERVATION_REQUEST,
    )
    runs = (
        FakeRun(
            run_id="run-a",
            dataset=dataset,
            config=FakeConfig(system_id="crew-a", initial_balance=Decimal("100")),
            period_start=period_start,
            period_end=period_end,
        ),
        FakeRun(
            run_id="run-b",
            dataset=dataset,
            config=FakeConfig(system_id="crew-b", initial_balance=Decimal("250")),
            period_start=period_start,
            period_end=period_end,
        ),
    )
    return build_master_historical_replay_plan(
        master_portfolio_id=MASTER_ID,
        master_initial_capital=capital,
        allocation_policy=allocation,
        gate_policy=gate,
        arbitration_policy=arbitration,
        backtest_runs=runs,
        created_at=BASE + timedelta(days=10),
    )


def _timeline(*, plan=None, dataset=None, candles=None):
    dataset = dataset or _dataset()
    plan = plan or _plan(dataset=dataset)
    return build_master_historical_replay_timeline(
        plan=plan,
        dataset=dataset,
        candles=_candles() if candles is None else candles,
    )


def test_builds_ready_shared_clock_timeline() -> None:
    timeline = _timeline()
    assert timeline.status is MasterHistoricalReplayTimelineStatus.READY
    assert timeline.shared_market_clock is True
    assert timeline.open_close_barriers is True
    assert timeline.candle_count == 4
    assert len(timeline.barriers) == 8


def test_barriers_alternate_open_then_close() -> None:
    phases = tuple(item.phase for item in _timeline().barriers)
    assert phases == (
        MasterHistoricalReplayBarrierPhase.CANDLE_OPEN,
        MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE,
    ) * 4


def test_barrier_sequences_and_candle_indexes_are_contiguous() -> None:
    timeline = _timeline()
    assert tuple(item.sequence for item in timeline.barriers) == tuple(range(1, 9))
    assert tuple(item.candle_index for item in timeline.barriers) == (1, 1, 2, 2, 3, 3, 4, 4)


def test_open_and_close_observed_at_match_phase() -> None:
    timeline = _timeline()
    for open_barrier, close_barrier in zip(
        timeline.barriers[::2], timeline.barriers[1::2], strict=True
    ):
        assert open_barrier.observed_at == open_barrier.candle_open_at
        assert close_barrier.observed_at == close_barrier.candle_close_at


def test_each_barrier_pair_binds_same_candle() -> None:
    timeline = _timeline()
    for open_barrier, close_barrier in zip(
        timeline.barriers[::2], timeline.barriers[1::2], strict=True
    ):
        assert open_barrier.candle_fingerprint_sha256 == close_barrier.candle_fingerprint_sha256
        assert open_barrier.candle_open_at == close_barrier.candle_open_at
        assert open_barrier.candle_close_at == close_barrier.candle_close_at


def test_warmup_and_evaluation_counts_follow_close_time() -> None:
    timeline = _timeline()
    assert timeline.warmup_candle_count == 1
    assert timeline.evaluation_candle_count == 3
    close_barriers = timeline.barriers[1::2]
    assert tuple(item.decision_eligible for item in close_barriers) == (False, True, True, True)


def test_open_barriers_are_never_decision_eligible() -> None:
    assert all(item.decision_eligible is False for item in _timeline().barriers[::2])


def test_every_barrier_contains_canonical_crew_order() -> None:
    timeline = _timeline()
    assert timeline.crew_system_ids == ("crew-a", "crew-b")
    assert all(item.crew_system_ids == ("crew-a", "crew-b") for item in timeline.barriers)


def test_timeline_does_not_sum_branch_equities() -> None:
    timeline = _timeline()
    assert timeline.single_master_capital is True
    assert timeline.sums_branch_equities is False
    assert not hasattr(timeline, "branch_equity")


def test_timeline_has_no_pipeline_risk_broker_or_live_authority() -> None:
    timeline = _timeline()
    assert timeline.executes_branch_pipeline is False
    assert timeline.mutation_applied is False
    assert timeline.risk_authority is False
    assert timeline.admission_authority is False
    assert timeline.reservation_mutation is False
    assert timeline.broker_authority is False
    assert timeline.registry_mutation is False
    assert timeline.live_authority is False
    assert timeline.auto_execute is False


def test_coordinator_is_read_only() -> None:
    coordinator = MasterHistoricalReplayCoordinator(plan=_plan())
    assert coordinator.risk_authority is False
    assert coordinator.admission_authority is False
    assert coordinator.reservation_mutation is False
    assert coordinator.broker_authority is False
    assert coordinator.live_authority is False


def test_coordinator_builds_same_timeline_as_function() -> None:
    dataset = _dataset()
    plan = _plan(dataset=dataset)
    expected = _timeline(plan=plan, dataset=dataset)
    actual = MasterHistoricalReplayCoordinator(plan=plan).build_timeline(
        dataset=dataset,
        candles=_candles(),
    )
    assert actual == expected


def test_input_candle_order_is_canonicalized() -> None:
    candles = _candles()
    dataset = _dataset(candles)
    plan = _plan(dataset=dataset)
    first = _timeline(plan=plan, dataset=dataset, candles=candles)
    second = _timeline(plan=plan, dataset=dataset, candles=tuple(reversed(candles)))
    assert first.fingerprint_sha256 == second.fingerprint_sha256
    assert first.timeline_id == second.timeline_id


def test_same_inputs_produce_same_fingerprint() -> None:
    first = _timeline()
    second = _timeline()
    assert first.timeline_id == second.timeline_id
    assert first.fingerprint_sha256 == second.fingerprint_sha256


def test_plan_identity_changes_timeline_identity() -> None:
    dataset = _dataset()
    first = _timeline(plan=_plan(dataset=dataset, capital=Decimal("80")), dataset=dataset)
    second = _timeline(plan=_plan(dataset=dataset, capital=Decimal("81")), dataset=dataset)
    assert first.timeline_id != second.timeline_id
    assert first.fingerprint_sha256 != second.fingerprint_sha256


def test_dataset_fingerprint_mismatch_rejected() -> None:
    dataset = _dataset()
    plan = _plan(dataset=dataset)
    changed = replace(dataset, version="sha256:" + "f" * 64)
    with pytest.raises(ValueError, match="dataset fingerprint"):
        _timeline(plan=plan, dataset=changed)


def test_wrong_candle_content_rejected() -> None:
    candles = list(_candles())
    candles[2] = {**candles[2], "close": Decimal("102.5")}
    dataset = _dataset()
    plan = _plan(dataset=dataset)
    with pytest.raises(ValueError, match="candle content"):
        _timeline(plan=plan, dataset=dataset, candles=tuple(candles))


def test_wrong_candle_symbol_rejected() -> None:
    candles = list(_candles())
    candles[0] = {**candles[0], "symbol": "ETHUSDC"}
    with pytest.raises(ValueError, match="symbol"):
        _timeline(candles=tuple(candles))


def test_wrong_candle_timeframe_rejected() -> None:
    candles = list(_candles())
    candles[0] = {**candles[0], "timeframe": "5m"}
    with pytest.raises(ValueError, match="timeframe"):
        _timeline(candles=tuple(candles))


def test_unclosed_candle_rejected() -> None:
    candles = list(_candles())
    candles[1] = {**candles[1], "is_closed": False}
    dataset = _dataset(candles)
    plan = _plan(dataset=dataset)
    with pytest.raises(ValueError, match="closed candles only"):
        _timeline(plan=plan, dataset=dataset, candles=tuple(candles))


def test_duplicate_candle_open_time_rejected() -> None:
    candles = list(_candles())
    candles[1] = {**candles[1], "open_time": candles[0]["open_time"]}
    with pytest.raises(ValueError, match="duplicate candle open_time"):
        _timeline(candles=tuple(candles))


def test_overlapping_replayed_candles_rejected() -> None:
    candles = list(_candles())
    candles[0] = {**candles[0], "close_time": BASE + timedelta(hours=2)}
    dataset = _dataset(candles)
    plan = _plan(dataset=dataset)
    with pytest.raises(ValueError, match="non-overlapping"):
        _timeline(plan=plan, dataset=dataset, candles=tuple(candles))


def test_overlap_after_period_end_is_not_replayed() -> None:
    candles = list(_candles())
    candles[3] = {
        **candles[3],
        "open_time": BASE + timedelta(hours=2, minutes=30),
        "close_time": BASE + timedelta(hours=4),
    }
    dataset = _dataset(candles)
    plan = _plan(
        dataset=dataset,
        period_start=BASE + timedelta(hours=1),
        period_end=BASE + timedelta(hours=3),
    )
    timeline = _timeline(plan=plan, dataset=dataset, candles=tuple(candles))
    assert timeline.candle_count == 3


def test_period_end_truncates_timeline_like_historical_runner() -> None:
    dataset = _dataset()
    plan = _plan(
        dataset=dataset,
        period_start=BASE + timedelta(hours=1),
        period_end=BASE + timedelta(hours=3),
    )
    timeline = _timeline(plan=plan, dataset=dataset)
    assert timeline.candle_count == 3
    assert timeline.barriers[-1].candle_close_at == BASE + timedelta(hours=3)


def test_period_can_have_no_completed_candle() -> None:
    dataset = _dataset()
    plan = _plan(dataset=dataset, period_start=BASE, period_end=BASE)
    timeline = _timeline(plan=plan, dataset=dataset)
    assert timeline.candle_count == 0
    assert timeline.warmup_candle_count == 0
    assert timeline.evaluation_candle_count == 0
    assert timeline.barriers == ()


def test_manual_barrier_fingerprint_tamper_rejected() -> None:
    barrier = _timeline().barriers[0]
    with pytest.raises(ValueError, match="barrier fingerprint"):
        replace(barrier, fingerprint_sha256="f" * 64)


def test_manual_barrier_observed_time_tamper_rejected() -> None:
    barrier = _timeline().barriers[0]
    with pytest.raises(ValueError, match="observed_at does not match"):
        replace(barrier, observed_at=barrier.observed_at + timedelta(seconds=1))


def test_manual_open_barrier_eligibility_tamper_rejected() -> None:
    barrier = _timeline().barriers[0]
    with pytest.raises(ValueError, match="cannot be decision eligible"):
        replace(barrier, decision_eligible=True)


def test_manual_timeline_fingerprint_tamper_rejected() -> None:
    timeline = _timeline()
    with pytest.raises(ValueError, match="timeline fingerprint"):
        replace(timeline, fingerprint_sha256="f" * 64)


def test_manual_timeline_counter_tamper_rejected() -> None:
    timeline = _timeline()
    with pytest.raises(ValueError, match="candle counters"):
        replace(timeline, warmup_candle_count=0)


def test_manual_barrier_order_tamper_rejected() -> None:
    timeline = _timeline()
    swapped = (timeline.barriers[1], timeline.barriers[0], *timeline.barriers[2:])
    with pytest.raises(ValueError, match="sequence is not contiguous|alternate OPEN then CLOSE"):
        replace(timeline, barriers=swapped)


def test_manual_barrier_crew_tamper_rejected() -> None:
    timeline = _timeline()
    first = timeline.barriers[0]
    payload = first.canonical_payload()
    payload["crew_system_ids"] = ("crew-a",)
    changed = replace(
        first,
        crew_system_ids=("crew-a",),
        fingerprint_sha256=stable_digest(payload),
    )
    with pytest.raises(ValueError, match="barrier crews"):
        replace(timeline, barriers=(changed, *timeline.barriers[1:]))


def test_dataset_requires_canonical_payload() -> None:
    class BadDataset:
        content_sha256 = "f" * 64
        symbol = "BTCUSDC"
        timeframe = "1h"
        source = "fixture"
        candle_count = 4
        start_at = BASE
        end_at = BASE + timedelta(hours=4)

    with pytest.raises(ValueError, match="canonical_payload"):
        build_master_historical_replay_timeline(
            plan=_plan(),
            dataset=BadDataset(),
            candles=_candles(),
        )
