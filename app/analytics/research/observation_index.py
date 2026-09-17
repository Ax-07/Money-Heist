from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from app.analytics.events import TechnicalEventObservation
from app.analytics.indicators import AnalyticsIndicatorSnapshot
from app.analytics.patterns import PatternOccurrence, PatternStatus, PatternType
from app.analytics.provenance import as_utc
from app.analytics.structure import AnalyticsMarketStructureObservation
from app.analytics.zigzag import CausalZigZagPivot

from .models import AnalyticsAnchorSpec, ResolvedAnchor
from .registry import ANALYTICS_OBSERVATION_INDEX_VERSION, AnalyticsAnchorType


@dataclass(frozen=True, slots=True)
class IndexedPatternTransition:
    pattern_id: str
    pattern_type: PatternType
    status: PatternStatus
    symbol: str
    timeframe: str
    available_at: datetime
    transition_fingerprint: str
    pattern_fingerprint: str


@dataclass(frozen=True, slots=True)
class AnalyticsObservationIndex:
    """Immutable causal view over already-computed Analytics observations."""

    as_of: datetime
    indicator_snapshots: tuple[AnalyticsIndicatorSnapshot, ...]
    technical_events: tuple[TechnicalEventObservation, ...]
    structure_observations: tuple[AnalyticsMarketStructureObservation, ...]
    zigzag_pivots: tuple[CausalZigZagPivot, ...]
    pattern_occurrences: tuple[PatternOccurrence, ...]
    pattern_transitions: tuple[IndexedPatternTransition, ...]
    version: str = ANALYTICS_OBSERVATION_INDEX_VERSION

    @classmethod
    def build(
        cls,
        *,
        as_of: datetime,
        indicator_snapshots: Iterable[AnalyticsIndicatorSnapshot] = (),
        technical_events: Iterable[TechnicalEventObservation] = (),
        structure_observations: Iterable[AnalyticsMarketStructureObservation] = (),
        zigzag_pivots: Iterable[CausalZigZagPivot] = (),
        pattern_occurrences: Iterable[PatternOccurrence] = (),
    ) -> AnalyticsObservationIndex:
        cutoff = as_utc(as_of, field_name="as_of")
        indicators = tuple(sorted(
            (item for item in indicator_snapshots if item.as_of <= cutoff),
            key=lambda item: (item.symbol, item.timeframe, item.as_of, item.snapshot_fingerprint),
        ))
        events = tuple(sorted(
            (item for item in technical_events if item.available_at <= cutoff),
            key=lambda item: (item.symbol, item.timeframe, item.available_at, item.event_id),
        ))
        structures = tuple(sorted(
            (item for item in structure_observations if item.as_of <= cutoff),
            key=lambda item: (item.symbol, item.as_of, item.fingerprint),
        ))
        pivots = tuple(sorted(
            (item for item in zigzag_pivots if item.confirmed_at <= cutoff),
            key=lambda item: (item.symbol, item.timeframe, item.confirmed_at, item.pivot_id),
        ))
        patterns = tuple(sorted(
            (item for item in pattern_occurrences if item.detected_at <= cutoff),
            key=lambda item: (item.symbol, item.timeframe, item.detected_at, item.pattern_id),
        ))
        transitions: list[IndexedPatternTransition] = []
        for pattern in patterns:
            for transition in pattern.transitions:
                if transition.available_at <= cutoff:
                    transitions.append(
                        IndexedPatternTransition(
                            pattern_id=pattern.pattern_id,
                            pattern_type=pattern.pattern_type,
                            status=transition.status,
                            symbol=pattern.symbol,
                            timeframe=pattern.timeframe,
                            available_at=transition.available_at,
                            transition_fingerprint=transition.fingerprint,
                            pattern_fingerprint=pattern.pattern_fingerprint,
                        )
                    )
        transitions.sort(
            key=lambda item: (
                item.symbol,
                item.timeframe,
                item.available_at,
                item.pattern_id,
                item.status.value,
            )
        )
        return cls(cutoff, indicators, events, structures, pivots, patterns, tuple(transitions))

    def with_as_of(self, as_of: datetime) -> AnalyticsObservationIndex:
        cutoff = as_utc(as_of, field_name="as_of")
        if cutoff > self.as_of:
            raise ValueError("with_as_of cannot reveal observations beyond the index cutoff")
        return self.build(
            as_of=cutoff,
            indicator_snapshots=self.indicator_snapshots,
            technical_events=self.technical_events,
            structure_observations=self.structure_observations,
            zigzag_pivots=self.zigzag_pivots,
            pattern_occurrences=self.pattern_occurrences,
        )

    def anchor_candidates(
        self,
        spec: AnalyticsAnchorSpec,
        *,
        symbol: str,
        as_of: datetime
    ) -> tuple[ResolvedAnchor, ...]:
        cutoff = min(as_utc(as_of, field_name="as_of"), self.as_of)
        anchors: list[ResolvedAnchor] = []
        if spec.anchor_type is AnalyticsAnchorType.TECHNICAL_EVENT:
            for item in self.technical_events:
                if (
                    item.symbol == symbol
                    and item.timeframe == spec.timeframe
                    and item.event_type == spec.event_type
                    and item.available_at <= cutoff
                ):
                    anchors.append(ResolvedAnchor(
                        source_type=spec.anchor_type,
                        source_ref=item.event_id,
                        symbol=item.symbol,
                        timeframe=item.timeframe,
                        anchor_at=item.available_at,
                        source_fingerprint=item.event_fingerprint,
                        evidence={
                            "event_type": item.event_type,
                            "event_at": item.event_at,
                            "direction": item.direction.value
                        },
                    ))
        elif spec.anchor_type is AnalyticsAnchorType.PATTERN_TRANSITION:
            for item in self.pattern_transitions:
                if (
                    item.symbol == symbol
                    and item.timeframe == spec.timeframe
                    and item.pattern_type == spec.pattern_type
                    and item.status == spec.pattern_status
                    and item.available_at <= cutoff
                ):
                    anchors.append(ResolvedAnchor(
                        source_type=spec.anchor_type,
                        source_ref=f"{item.pattern_id}:{item.transition_fingerprint[:16]}",
                        symbol=item.symbol,
                        timeframe=item.timeframe,
                        anchor_at=item.available_at,
                        source_fingerprint=item.transition_fingerprint,
                        evidence={
                            "pattern_id": item.pattern_id,
                            "pattern_type": item.pattern_type.value,
                            "status": item.status.value
                        },
                    ))
        else:
            for item in self.zigzag_pivots:
                if (
                    item.symbol == symbol
                    and item.timeframe == spec.timeframe
                    and item.kind == spec.pivot_kind
                    and item.confirmed_at <= cutoff
                ):
                    anchors.append(ResolvedAnchor(
                        source_type=spec.anchor_type,
                        source_ref=item.pivot_id,
                        symbol=item.symbol,
                        timeframe=item.timeframe,
                        anchor_at=item.confirmed_at,
                        source_fingerprint=item.pivot_fingerprint,
                        evidence={
                            "kind": item.kind.value,
                            "pivot_at": item.pivot_at,
                            "confirmed_at": item.confirmed_at,
                            "price": item.price
                        },
                    ))
        anchors.sort(key=lambda item: (item.anchor_at, item.source_ref))
        return tuple(anchors)

    def indicator_at(
        self,
        *,
        symbol: str,
        timeframe: str,
        at: datetime
    ) -> AnalyticsIndicatorSnapshot | None:
        cutoff = min(as_utc(at, field_name="at"), self.as_of)
        candidates = [
            item
            for item in self.indicator_snapshots
            if item.symbol == symbol
            and item.timeframe == timeframe
            and item.as_of <= cutoff
        ]
        return max(
            candidates,
            key=lambda item: (item.as_of, item.snapshot_fingerprint),
            default=None
        )

    def structure_at(
        self,
        *,
        symbol: str,
        at: datetime
    ) -> AnalyticsMarketStructureObservation | None:
        cutoff = min(as_utc(at, field_name="at"), self.as_of)
        candidates = [
            item
            for item in self.structure_observations
            if item.symbol == symbol and item.as_of <= cutoff
        ]
        return max(candidates, key=lambda item: (item.as_of, item.fingerprint), default=None)

    def bar_distance(
        self,
        *,
        symbol: str,
        timeframe: str,
        earlier: datetime,
        later: datetime
    ) -> int | None:
        earlier = as_utc(earlier, field_name="earlier")
        later = as_utc(later, field_name="later")
        if earlier > later:
            return None
        bars = sorted(
            {
                item.as_of
                for item in self.indicator_snapshots
                if item.symbol == symbol
                and item.timeframe == timeframe
                and item.as_of <= self.as_of
            }
        )
        try:
            return bars.index(later) - bars.index(earlier)
        except ValueError:
            return None

    @property
    def counts(self) -> MappingProxyType[str, int]:
        return MappingProxyType({
            "indicator_snapshots": len(self.indicator_snapshots),
            "technical_events": len(self.technical_events),
            "structure_observations": len(self.structure_observations),
            "zigzag_pivots": len(self.zigzag_pivots),
            "pattern_occurrences": len(self.pattern_occurrences),
            "pattern_transitions": len(self.pattern_transitions),
        })


__all__ = [
    "ANALYTICS_OBSERVATION_INDEX_VERSION",
    "AnalyticsObservationIndex",
    "IndexedPatternTransition"
]
