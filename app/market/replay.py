from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from app.market.features import FeatureEngine, FeatureSnapshot
from app.market.scanner import CandidateOpportunity, DeterministicScanner


@dataclass(frozen=True, slots=True)
class ReplayPoint:
    feature_snapshot: FeatureSnapshot
    opportunity: CandidateOpportunity | None


def replay_scanner(
    candles: Sequence[Any],
    *,
    symbol: str,
    timeframe: str,
    system_id: str,
    feature_engine: FeatureEngine | None = None,
    scanner: DeterministicScanner | None = None,
    min_history: int | None = None,
) -> tuple[ReplayPoint, ...]:
    """Chronologically replay the same production feature/scanner code.

    No future candle is visible to a replay step. This helper is intentionally
    simple: it is a deterministic test/replay primitive, not the Batch 10 backtest
    engine.
    """

    engine = feature_engine or FeatureEngine()
    scanner_service = scanner or DeterministicScanner()
    start = min_history or engine.config.warmup_bars
    if start <= 0:
        raise ValueError("min_history must be greater than zero")

    points: list[ReplayPoint] = []
    previous: FeatureSnapshot | None = None
    for end in range(start, len(candles) + 1):
        feature = engine.compute(
            candles[:end],
            symbol=symbol,
            timeframe=timeframe,
        )
        result = scanner_service.scan(feature, system_id=system_id, previous=previous)
        points.append(ReplayPoint(feature_snapshot=feature, opportunity=result.opportunity))
        previous = feature
    return tuple(points)


def opportunities_from_replay(points: Iterable[ReplayPoint]) -> tuple[CandidateOpportunity, ...]:
    return tuple(point.opportunity for point in points if point.opportunity is not None)
