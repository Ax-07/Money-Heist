from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.analytics.events import TECHNICAL_EVENT_REGISTRY
from app.analytics.models import AnalyticsPeriodRole
from app.analytics.research import (
    AnalyticsAnchorSpec,
    AnalyticsContextDefinition,
    AnalyticsResearchRun,
)
from app.analytics.research.registry import AnalyticsAnchorType

ZERO_FP = "0" * 64
ONE_FP = "1" * 64


@dataclass(frozen=True)
class FakeIndicatorValue:
    value: float | None
    available: bool
    warmup_complete: bool


class FakeIndicatorSnapshot:
    def __init__(
        self,
        *,
        symbol: str,
        timeframe: str,
        as_of: datetime,
        values: dict[str, FakeIndicatorValue],
        fp: str
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.as_of = as_of
        self.values_map = values
        self.snapshot_fingerprint = fp

    def value(self, indicator_id: str):
        return self.values_map[indicator_id]


class FakeEvent:
    def __init__(
        self,
        event_type: str,
        at: datetime,
        *,
        event_id: str,
        fp: str,
        symbol="BTC/EUR",
        timeframe="1h"
    ):
        self.event_type = event_type
        self.event_at = at
        self.available_at = at
        self.event_id = event_id
        self.event_fingerprint = fp
        self.symbol = symbol
        self.timeframe = timeframe
        self.direction = SimpleNamespace(value="BULLISH")


@pytest.fixture
def t0():
    return datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def event_types():
    return tuple(item.event_type for item in TECHNICAL_EVENT_REGISTRY[:4])


def fake_research_run(definition):
    return AnalyticsResearchRun(
        research_run_id=f"research-{definition.revision_id}",
        analytics_run_id="analytics-run",
        definition_id=definition.definition_id,
        revision_id=definition.revision_id,
        definition_fingerprint=definition.definition_fingerprint,
        resolver_version=definition.resolver_version,
        origin_period_role=definition.origin_period_role,
        identity_fingerprint=ZERO_FP,
    )


def context_definition(event_type: str, conditions=()):
    return AnalyticsContextDefinition.create(
        definition_id="ctx-test",
        revision_number=1,
        name="test context",
        description="causal test",
        anchor=AnalyticsAnchorSpec(
            AnalyticsAnchorType.TECHNICAL_EVENT,
            "1h",
            event_type=event_type
        ),
        conditions=conditions,
        timeframe="1h",
        origin_period_role=AnalyticsPeriodRole.DESIGN,
    )


def bars(t0, count=12):
    return tuple(t0 + timedelta(hours=i) for i in range(count))
