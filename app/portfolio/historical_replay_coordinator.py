from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.services.backtest.dataset import DatasetRef, canonical_candle_rows
from app.services.backtest.ids import stable_digest

from .historical_replay import (
    MasterHistoricalReplayMode,
    MasterHistoricalReplayPlan,
    MasterHistoricalReplayPlanStatus,
)


class HistoricalReplayDatasetLike(Protocol):
    content_sha256: str
    symbol: str
    timeframe: str
    source: str
    candle_count: int
    start_at: datetime
    end_at: datetime

    def canonical_payload(self) -> dict[str, object]: ...


class MasterHistoricalReplayBarrierPhase(StrEnum):
    CANDLE_OPEN = "CANDLE_OPEN"
    CANDLE_CLOSE = "CANDLE_CLOSE"


class MasterHistoricalReplayTimelineStatus(StrEnum):
    READY = "READY"


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


def _canonical_payload(value: Any, *, field_name: str) -> dict[str, object]:
    method = getattr(value, "canonical_payload", None)
    if not callable(method):
        raise ValueError(f"{field_name} must expose canonical_payload()")
    payload = method()
    if not isinstance(payload, dict):
        raise ValueError(f"{field_name}.canonical_payload() must return dict")
    return payload


def _row_time(row: dict[str, Any], field_name: str) -> datetime:
    value = row[field_name]
    if not isinstance(value, str):
        raise ValueError(f"canonical {field_name} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"canonical {field_name} must be ISO-8601 text") from exc
    return _utc(parsed, field_name=field_name)


def master_historical_replay_barrier_payload(
    barrier: MasterHistoricalReplayBarrier,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-replay-barrier.v1",
        "schema_version": barrier.schema_version,
        "sequence": barrier.sequence,
        "candle_index": barrier.candle_index,
        "phase": barrier.phase,
        "observed_at": barrier.observed_at,
        "candle_open_at": barrier.candle_open_at,
        "candle_close_at": barrier.candle_close_at,
        "visible_candle_count": barrier.visible_candle_count,
        "decision_eligible": barrier.decision_eligible,
        "candle_fingerprint_sha256": barrier.candle_fingerprint_sha256,
        "crew_system_ids": barrier.crew_system_ids,
    }


def master_historical_replay_barrier_fingerprint(
    barrier: MasterHistoricalReplayBarrier,
) -> str:
    return stable_digest(master_historical_replay_barrier_payload(barrier))


@dataclass(frozen=True, slots=True)
class MasterHistoricalReplayBarrier:
    """One deterministic shared-clock barrier for every crew in the Master replay."""

    sequence: int
    candle_index: int
    phase: MasterHistoricalReplayBarrierPhase
    observed_at: datetime
    candle_open_at: datetime
    candle_close_at: datetime
    visible_candle_count: int
    decision_eligible: bool
    candle_fingerprint_sha256: str
    crew_system_ids: tuple[str, ...]
    fingerprint_sha256: str
    risk_authority: bool = field(default=False, init=False)
    admission_authority: bool = field(default=False, init=False)
    reservation_mutation: bool = field(default=False, init=False)
    broker_authority: bool = field(default=False, init=False)
    live_authority: bool = field(default=False, init=False)
    auto_execute: bool = field(default=False, init=False)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("Master replay barrier sequence must be >= 1")
        if self.candle_index < 1:
            raise ValueError("Master replay barrier candle_index must be >= 1")
        if self.visible_candle_count != self.candle_index:
            raise ValueError("visible_candle_count must equal candle_index")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, field_name="observed_at"))
        object.__setattr__(
            self,
            "candle_open_at",
            _utc(self.candle_open_at, field_name="candle_open_at"),
        )
        object.__setattr__(
            self,
            "candle_close_at",
            _utc(self.candle_close_at, field_name="candle_close_at"),
        )
        if self.candle_close_at <= self.candle_open_at:
            raise ValueError("Master replay barrier candle close must follow candle open")
        expected_observed_at = (
            self.candle_open_at
            if self.phase is MasterHistoricalReplayBarrierPhase.CANDLE_OPEN
            else self.candle_close_at
        )
        if self.observed_at != expected_observed_at:
            raise ValueError("Master replay barrier observed_at does not match its phase")
        if self.phase is MasterHistoricalReplayBarrierPhase.CANDLE_OPEN and self.decision_eligible:
            raise ValueError("CANDLE_OPEN barriers cannot be decision eligible")
        if not self.crew_system_ids:
            raise ValueError("Master replay barrier requires at least one crew")
        normalized_crews = tuple(
            _required_text(system_id, field_name="crew_system_ids")
            for system_id in self.crew_system_ids
        )
        if normalized_crews != tuple(sorted(normalized_crews)):
            raise ValueError("Master replay barrier crews must be sorted by system_id")
        if len(set(normalized_crews)) != len(normalized_crews):
            raise ValueError("Master replay barrier crews must be unique")
        object.__setattr__(self, "crew_system_ids", normalized_crews)
        object.__setattr__(
            self,
            "candle_fingerprint_sha256",
            _sha256(
                self.candle_fingerprint_sha256,
                field_name="candle_fingerprint_sha256",
            ),
        )
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical replay barrier schema_version")

        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_historical_replay_barrier_fingerprint(self)
        if normalized != expected:
            raise ValueError("Master historical replay barrier fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_historical_replay_barrier_payload(self)


def master_historical_replay_timeline_payload(
    timeline: MasterHistoricalReplayTimeline,
) -> dict[str, object]:
    return {
        "schema": "money-heist.master-historical-replay-timeline.v1",
        "schema_version": timeline.schema_version,
        "timeline_id": timeline.timeline_id,
        "master_portfolio_id": timeline.master_portfolio_id,
        "plan_id": timeline.plan_id,
        "status": timeline.status,
        "mode": timeline.mode,
        "plan_fingerprint_sha256": timeline.plan_fingerprint_sha256,
        "dataset_fingerprint_sha256": timeline.dataset_fingerprint_sha256,
        "dataset_content_sha256": timeline.dataset_content_sha256,
        "period_start": timeline.period_start,
        "period_end": timeline.period_end,
        "crew_system_ids": timeline.crew_system_ids,
        "candle_count": timeline.candle_count,
        "warmup_candle_count": timeline.warmup_candle_count,
        "evaluation_candle_count": timeline.evaluation_candle_count,
        "barriers": [master_historical_replay_barrier_payload(item) for item in timeline.barriers],
    }


def master_historical_replay_timeline_fingerprint(
    timeline: MasterHistoricalReplayTimeline,
) -> str:
    return stable_digest(master_historical_replay_timeline_payload(timeline))


@dataclass(frozen=True, slots=True)
class MasterHistoricalReplayTimeline:
    """Immutable OPEN/CLOSE barrier schedule for one coordinated Master replay."""

    timeline_id: str
    master_portfolio_id: str
    plan_id: str
    status: MasterHistoricalReplayTimelineStatus
    mode: MasterHistoricalReplayMode
    plan_fingerprint_sha256: str
    dataset_fingerprint_sha256: str
    dataset_content_sha256: str
    period_start: datetime
    period_end: datetime
    crew_system_ids: tuple[str, ...]
    candle_count: int
    warmup_candle_count: int
    evaluation_candle_count: int
    barriers: tuple[MasterHistoricalReplayBarrier, ...]
    fingerprint_sha256: str
    shared_market_clock: bool = field(default=True, init=False)
    open_close_barriers: bool = field(default=True, init=False)
    single_master_capital: bool = field(default=True, init=False)
    sums_branch_equities: bool = field(default=False, init=False)
    executes_branch_pipeline: bool = field(default=False, init=False)
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
        for field_name in ("timeline_id", "master_portfolio_id", "plan_id"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        if self.status is not MasterHistoricalReplayTimelineStatus.READY:
            raise ValueError("Master historical replay timeline status must be READY")
        if self.mode is not MasterHistoricalReplayMode.COORDINATED_SINGLE_DATASET_V1:
            raise ValueError("unsupported Master historical replay timeline mode")
        object.__setattr__(self, "period_start", _utc(self.period_start, field_name="period_start"))
        object.__setattr__(self, "period_end", _utc(self.period_end, field_name="period_end"))
        if self.period_end < self.period_start:
            raise ValueError("Master replay timeline period_end cannot precede period_start")
        for field_name in (
            "plan_fingerprint_sha256",
            "dataset_fingerprint_sha256",
            "dataset_content_sha256",
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
        if normalized_crews != tuple(sorted(normalized_crews)):
            raise ValueError("Master replay timeline crews must be sorted by system_id")
        if len(set(normalized_crews)) != len(normalized_crews) or not normalized_crews:
            raise ValueError("Master replay timeline crews must be unique and non-empty")
        object.__setattr__(self, "crew_system_ids", normalized_crews)

        for field_name in ("candle_count", "warmup_candle_count", "evaluation_candle_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be an integer >= 0")
        if self.warmup_candle_count + self.evaluation_candle_count != self.candle_count:
            raise ValueError("Master replay timeline candle counters are inconsistent")
        if len(self.barriers) != self.candle_count * 2:
            raise ValueError("Master replay timeline requires two barriers per candle")

        for offset, barrier in enumerate(self.barriers):
            expected_sequence = offset + 1
            expected_candle_index = (offset // 2) + 1
            expected_phase = (
                MasterHistoricalReplayBarrierPhase.CANDLE_OPEN
                if offset % 2 == 0
                else MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE
            )
            if barrier.sequence != expected_sequence:
                raise ValueError("Master replay barrier sequence is not contiguous")
            if barrier.candle_index != expected_candle_index:
                raise ValueError("Master replay barrier candle order is inconsistent")
            if barrier.phase is not expected_phase:
                raise ValueError("Master replay barriers must alternate OPEN then CLOSE")
            if barrier.crew_system_ids != self.crew_system_ids:
                raise ValueError("Master replay barrier crews do not match timeline crews")
            expected_eligible = (
                expected_phase is MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE
                and self.period_start <= barrier.candle_close_at <= self.period_end
            )
            if barrier.decision_eligible is not expected_eligible:
                raise ValueError("Master replay barrier decision eligibility is inconsistent")
            if (
                offset >= 2
                and expected_phase is MasterHistoricalReplayBarrierPhase.CANDLE_OPEN
                and barrier.candle_open_at < self.barriers[offset - 1].candle_close_at
            ):
                raise ValueError("Master replay candles must not overlap")

        actual_evaluation_count = sum(
            1
            for barrier in self.barriers
            if barrier.phase is MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE
            and barrier.decision_eligible
        )
        if actual_evaluation_count != self.evaluation_candle_count:
            raise ValueError("Master replay evaluation candle count is inconsistent")
        if self.schema_version != "1.0":
            raise ValueError("unsupported Master historical replay timeline schema_version")

        normalized = _sha256(self.fingerprint_sha256, field_name="fingerprint_sha256")
        expected = master_historical_replay_timeline_fingerprint(self)
        if normalized != expected:
            raise ValueError("Master historical replay timeline fingerprint does not match payload")
        object.__setattr__(self, "fingerprint_sha256", normalized)

    def canonical_payload(self) -> dict[str, object]:
        return master_historical_replay_timeline_payload(self)


class MasterHistoricalReplayCoordinator:
    """Build the shared historical clock without executing any crew pipeline or broker."""

    def __init__(self, *, plan: MasterHistoricalReplayPlan) -> None:
        if plan.status is not MasterHistoricalReplayPlanStatus.READY:
            raise ValueError("Master historical replay coordinator requires READY plan")
        if plan.mode is not MasterHistoricalReplayMode.COORDINATED_SINGLE_DATASET_V1:
            raise ValueError("unsupported Master historical replay coordinator mode")
        self.plan = plan

    def build_timeline(
        self,
        *,
        dataset: HistoricalReplayDatasetLike,
        candles: Sequence[Any],
    ) -> MasterHistoricalReplayTimeline:
        return build_master_historical_replay_timeline(
            plan=self.plan,
            dataset=dataset,
            candles=candles,
        )

    @property
    def risk_authority(self) -> bool:
        return False

    @property
    def admission_authority(self) -> bool:
        return False

    @property
    def reservation_mutation(self) -> bool:
        return False

    @property
    def broker_authority(self) -> bool:
        return False

    @property
    def live_authority(self) -> bool:
        return False


def _validate_dataset_binding(
    *,
    plan: MasterHistoricalReplayPlan,
    dataset: HistoricalReplayDatasetLike,
) -> None:
    dataset_payload = _canonical_payload(dataset, field_name="dataset")
    if stable_digest(dataset_payload) != plan.dataset_fingerprint_sha256:
        raise ValueError("historical dataset fingerprint does not match Master replay plan")
    if _sha256(dataset.content_sha256, field_name="dataset.content_sha256") != (
        plan.dataset_content_sha256
    ):
        raise ValueError("historical dataset content does not match Master replay plan")
    if _required_text(dataset.symbol, field_name="dataset.symbol") != plan.symbol:
        raise ValueError("historical dataset symbol does not match Master replay plan")
    if _required_text(dataset.timeframe, field_name="dataset.timeframe") != plan.timeframe:
        raise ValueError("historical dataset timeframe does not match Master replay plan")


def _validated_rows(
    *,
    plan: MasterHistoricalReplayPlan,
    dataset: HistoricalReplayDatasetLike,
    candles: Sequence[Any],
) -> tuple[dict[str, Any], ...]:
    rows = canonical_candle_rows(
        candles,
        expected_symbol=plan.symbol,
        expected_timeframe=plan.timeframe,
    )
    if any(not bool(row["is_closed"]) for row in rows):
        raise ValueError("Master historical replay requires closed candles only")

    actual_ref = DatasetRef.from_candles(
        rows,
        symbol=plan.symbol,
        timeframe=plan.timeframe,
        source=_required_text(dataset.source, field_name="dataset.source"),
    )
    if actual_ref.content_sha256 != plan.dataset_content_sha256:
        raise ValueError("historical candle content does not match Master replay dataset")
    if actual_ref.candle_count != dataset.candle_count:
        raise ValueError("historical candle count does not match Master replay dataset")
    if actual_ref.start_at != _utc(dataset.start_at, field_name="dataset.start_at"):
        raise ValueError("historical candle start does not match Master replay dataset")
    if actual_ref.end_at != _utc(dataset.end_at, field_name="dataset.end_at"):
        raise ValueError("historical candle end does not match Master replay dataset")
    return rows


def _build_barrier(
    *,
    sequence: int,
    candle_index: int,
    phase: MasterHistoricalReplayBarrierPhase,
    open_at: datetime,
    close_at: datetime,
    decision_eligible: bool,
    candle_fingerprint_sha256: str,
    crew_system_ids: tuple[str, ...],
) -> MasterHistoricalReplayBarrier:
    observed_at = (
        open_at if phase is MasterHistoricalReplayBarrierPhase.CANDLE_OPEN else close_at
    )
    payload = {
        "schema": "money-heist.master-historical-replay-barrier.v1",
        "schema_version": "1.0",
        "sequence": sequence,
        "candle_index": candle_index,
        "phase": phase,
        "observed_at": observed_at,
        "candle_open_at": open_at,
        "candle_close_at": close_at,
        "visible_candle_count": candle_index,
        "decision_eligible": decision_eligible,
        "candle_fingerprint_sha256": candle_fingerprint_sha256,
        "crew_system_ids": crew_system_ids,
    }
    return MasterHistoricalReplayBarrier(
        sequence=sequence,
        candle_index=candle_index,
        phase=phase,
        observed_at=observed_at,
        candle_open_at=open_at,
        candle_close_at=close_at,
        visible_candle_count=candle_index,
        decision_eligible=decision_eligible,
        candle_fingerprint_sha256=candle_fingerprint_sha256,
        crew_system_ids=crew_system_ids,
        fingerprint_sha256=stable_digest(payload),
    )


def build_master_historical_replay_timeline(
    *,
    plan: MasterHistoricalReplayPlan,
    dataset: HistoricalReplayDatasetLike,
    candles: Sequence[Any],
) -> MasterHistoricalReplayTimeline:
    """Build exact OPEN/CLOSE barriers shared by every crew in one Master replay plan."""

    if plan.status is not MasterHistoricalReplayPlanStatus.READY:
        raise ValueError("Master historical replay timeline requires READY plan")
    if plan.mode is not MasterHistoricalReplayMode.COORDINATED_SINGLE_DATASET_V1:
        raise ValueError("unsupported Master historical replay timeline mode")
    _validate_dataset_binding(plan=plan, dataset=dataset)
    rows = _validated_rows(plan=plan, dataset=dataset, candles=candles)

    crew_system_ids = tuple(crew.system_id for crew in plan.crews)
    included_rows: list[tuple[dict[str, Any], datetime, datetime]] = []
    previous_close: datetime | None = None
    for row in rows:
        open_at = _row_time(row, "open_time")
        close_at = _row_time(row, "close_time")
        if close_at > plan.period_end:
            break
        if previous_close is not None and open_at < previous_close:
            raise ValueError("V1 Master historical replay requires non-overlapping candles")
        previous_close = close_at
        included_rows.append((row, open_at, close_at))

    barriers: list[MasterHistoricalReplayBarrier] = []
    warmup_count = 0
    evaluation_count = 0
    for candle_index, (row, open_at, close_at) in enumerate(included_rows, start=1):
        eligible = close_at >= plan.period_start
        if eligible:
            evaluation_count += 1
        else:
            warmup_count += 1
        candle_fingerprint = stable_digest(row)
        barriers.append(
            _build_barrier(
                sequence=len(barriers) + 1,
                candle_index=candle_index,
                phase=MasterHistoricalReplayBarrierPhase.CANDLE_OPEN,
                open_at=open_at,
                close_at=close_at,
                decision_eligible=False,
                candle_fingerprint_sha256=candle_fingerprint,
                crew_system_ids=crew_system_ids,
            )
        )
        barriers.append(
            _build_barrier(
                sequence=len(barriers) + 1,
                candle_index=candle_index,
                phase=MasterHistoricalReplayBarrierPhase.CANDLE_CLOSE,
                open_at=open_at,
                close_at=close_at,
                decision_eligible=eligible,
                candle_fingerprint_sha256=candle_fingerprint,
                crew_system_ids=crew_system_ids,
            )
        )

    identity_payload = {
        "schema": "money-heist.master-historical-replay-timeline-id.v1",
        "master_portfolio_id": plan.master_portfolio_id,
        "plan_id": plan.plan_id,
        "plan_fingerprint_sha256": plan.fingerprint_sha256,
        "dataset_fingerprint_sha256": plan.dataset_fingerprint_sha256,
        "dataset_content_sha256": plan.dataset_content_sha256,
        "barrier_fingerprints_sha256": [item.fingerprint_sha256 for item in barriers],
    }
    timeline_id = "master-replay:" + stable_digest(identity_payload)
    timeline_payload = {
        "schema": "money-heist.master-historical-replay-timeline.v1",
        "schema_version": "1.0",
        "timeline_id": timeline_id,
        "master_portfolio_id": plan.master_portfolio_id,
        "plan_id": plan.plan_id,
        "status": MasterHistoricalReplayTimelineStatus.READY,
        "mode": plan.mode,
        "plan_fingerprint_sha256": plan.fingerprint_sha256,
        "dataset_fingerprint_sha256": plan.dataset_fingerprint_sha256,
        "dataset_content_sha256": plan.dataset_content_sha256,
        "period_start": plan.period_start,
        "period_end": plan.period_end,
        "crew_system_ids": crew_system_ids,
        "candle_count": len(included_rows),
        "warmup_candle_count": warmup_count,
        "evaluation_candle_count": evaluation_count,
        "barriers": [master_historical_replay_barrier_payload(item) for item in barriers],
    }
    return MasterHistoricalReplayTimeline(
        timeline_id=timeline_id,
        master_portfolio_id=plan.master_portfolio_id,
        plan_id=plan.plan_id,
        status=MasterHistoricalReplayTimelineStatus.READY,
        mode=plan.mode,
        plan_fingerprint_sha256=plan.fingerprint_sha256,
        dataset_fingerprint_sha256=plan.dataset_fingerprint_sha256,
        dataset_content_sha256=plan.dataset_content_sha256,
        period_start=plan.period_start,
        period_end=plan.period_end,
        crew_system_ids=crew_system_ids,
        candle_count=len(included_rows),
        warmup_candle_count=warmup_count,
        evaluation_candle_count=evaluation_count,
        barriers=tuple(barriers),
        fingerprint_sha256=stable_digest(timeline_payload),
    )


__all__ = [
    "HistoricalReplayDatasetLike",
    "MasterHistoricalReplayBarrier",
    "MasterHistoricalReplayBarrierPhase",
    "MasterHistoricalReplayCoordinator",
    "MasterHistoricalReplayTimeline",
    "MasterHistoricalReplayTimelineStatus",
    "build_master_historical_replay_timeline",
    "master_historical_replay_barrier_fingerprint",
    "master_historical_replay_timeline_fingerprint",
]
