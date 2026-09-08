from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from .clock import as_utc
from .dataset import DatasetRef
from .ids import stable_uuid
from .models import BacktestConfig, BacktestRun


class BacktestPeriodRole(StrEnum):
    DESIGN = "DESIGN"
    VALIDATION = "VALIDATION"
    OOS = "OOS"


@dataclass(frozen=True, slots=True)
class BacktestPeriod:
    role: BacktestPeriodRole
    start_at: datetime
    end_at: datetime
    label: str = ""

    def __post_init__(self) -> None:
        start_at = as_utc(self.start_at, field="start_at")
        end_at = as_utc(self.end_at, field="end_at")
        if end_at < start_at:
            raise ValueError("period end_at cannot precede start_at")
        object.__setattr__(self, "start_at", start_at)
        object.__setattr__(self, "end_at", end_at)
        object.__setattr__(self, "label", self.label.strip())

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class BacktestRunSet:
    split_id: str
    design: BacktestRun
    validation: BacktestRun
    oos: BacktestRun

    def by_role(self, role: BacktestPeriodRole) -> BacktestRun:
        if role is BacktestPeriodRole.DESIGN:
            return self.design
        if role is BacktestPeriodRole.VALIDATION:
            return self.validation
        if role is BacktestPeriodRole.OOS:
            return self.oos
        raise ValueError(f"unsupported backtest period role: {role}")


@dataclass(frozen=True, slots=True)
class BacktestSplitPlan:
    split_id: str
    dataset: DatasetRef
    design: BacktestPeriod
    validation: BacktestPeriod
    oos: BacktestPeriod

    def __post_init__(self) -> None:
        if not self.split_id.strip():
            raise ValueError("split_id must not be empty")
        expected_roles = (
            (self.design, BacktestPeriodRole.DESIGN),
            (self.validation, BacktestPeriodRole.VALIDATION),
            (self.oos, BacktestPeriodRole.OOS),
        )
        for period, expected_role in expected_roles:
            if period.role is not expected_role:
                raise ValueError(f"{expected_role.value} period has incorrect role")
            if period.start_at < self.dataset.start_at or period.end_at > self.dataset.end_at:
                raise ValueError("split periods must stay within dataset bounds")
        if self.design.end_at >= self.validation.start_at:
            raise ValueError("DESIGN and VALIDATION periods must not overlap")
        if self.validation.end_at >= self.oos.start_at:
            raise ValueError("VALIDATION and OOS periods must not overlap")

    @classmethod
    def create(
        cls,
        *,
        dataset: DatasetRef,
        design_start: datetime,
        design_end: datetime,
        validation_start: datetime,
        validation_end: datetime,
        oos_start: datetime,
        oos_end: datetime,
        label_prefix: str = "",
    ) -> BacktestSplitPlan:
        prefix = label_prefix.strip()
        design = BacktestPeriod(
            BacktestPeriodRole.DESIGN,
            design_start,
            design_end,
            f"{prefix} design".strip(),
        )
        validation = BacktestPeriod(
            BacktestPeriodRole.VALIDATION,
            validation_start,
            validation_end,
            f"{prefix} validation".strip(),
        )
        oos = BacktestPeriod(
            BacktestPeriodRole.OOS,
            oos_start,
            oos_end,
            f"{prefix} oos".strip(),
        )
        payload = {
            "schema": "money-heist.backtest-split.v1",
            "dataset": dataset.canonical_payload(),
            "design": design.canonical_payload(),
            "validation": validation.canonical_payload(),
            "oos": oos.canonical_payload(),
        }
        return cls(
            split_id=stable_uuid("backtest-split", payload),
            dataset=dataset,
            design=design,
            validation=validation,
            oos=oos,
        )

    def runs(self, config: BacktestConfig) -> BacktestRunSet:
        return BacktestRunSet(
            split_id=self.split_id,
            design=BacktestRun.create(
                dataset=self.dataset,
                config=config,
                period_start=self.design.start_at,
                period_end=self.design.end_at,
            ),
            validation=BacktestRun.create(
                dataset=self.dataset,
                config=config,
                period_start=self.validation.start_at,
                period_end=self.validation.end_at,
            ),
            oos=BacktestRun.create(
                dataset=self.dataset,
                config=config,
                period_start=self.oos.start_at,
                period_end=self.oos.end_at,
            ),
        )


__all__ = [
    "BacktestPeriod",
    "BacktestPeriodRole",
    "BacktestRunSet",
    "BacktestSplitPlan",
]
