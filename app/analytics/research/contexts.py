from __future__ import annotations

from typing import Any

from app.analytics.events import TECHNICAL_EVENT_BY_TYPE
from app.analytics.indicators import INDICATOR_IDS
from app.market.structure import BreakoutState, RangeLocation, SwingStructure

from .models import (
    AnalyticsConditionSpec,
    AnalyticsContextDefinition,
    AnalyticsContextMatch,
    AnalyticsResearchRun,
    ConditionEvaluation,
    ResolvedAnchor,
)
from .observation_index import AnalyticsObservationIndex, IndexedPatternTransition
from .registry import (
    AnalyticsConditionType,
    IndicatorOperator,
    PatternConditionMode,
    StructureField,
    TemporalScope,
)


class AnalyticsContextResolver:
    def resolve(
        self,
        *,
        definition: AnalyticsContextDefinition,
        research_run: AnalyticsResearchRun,
        observation_index: AnalyticsObservationIndex,
        symbol: str,
        as_of,
    ) -> tuple[AnalyticsContextMatch, ...]:
        self._validate_definition(definition)
        if research_run.revision_id != definition.revision_id:
            raise ValueError("research run revision does not match context definition")
        index = (
            observation_index.with_as_of(as_of)
            if as_of < observation_index.as_of
            else observation_index
        )
        matches: list[AnalyticsContextMatch] = []
        seen: set[str] = set()
        for anchor in index.anchor_candidates(definition.anchor, symbol=symbol, as_of=as_of):
            evaluations = tuple(
                self.evaluate_condition(condition, anchor=anchor, observation_index=index)
                for condition in definition.conditions
            )
            if not all(item.matched for item in evaluations):
                continue
            match = AnalyticsContextMatch.create(
                research_run=research_run,
                definition=definition,
                anchor=anchor,
                as_of=as_of,
                condition_results=evaluations,
            )
            if match.match_id not in seen:
                seen.add(match.match_id)
                matches.append(match)
        matches.sort(key=lambda item: (item.anchor_at, item.match_id))
        return tuple(matches)

    def evaluate_condition(
        self,
        condition: AnalyticsConditionSpec,
        *,
        anchor: ResolvedAnchor,
        observation_index: AnalyticsObservationIndex,
    ) -> ConditionEvaluation:
        if condition.condition_type is AnalyticsConditionType.INDICATOR:
            return self._indicator(condition, anchor, observation_index)
        if condition.condition_type is AnalyticsConditionType.TECHNICAL_EVENT:
            return self._event(condition, anchor, observation_index)
        if condition.condition_type is AnalyticsConditionType.PATTERN_TRANSITION:
            return self._pattern(condition, anchor, observation_index)
        if condition.condition_type is AnalyticsConditionType.STRUCTURE:
            return self._structure(condition, anchor, observation_index)
        return self._zigzag(condition, anchor, observation_index)

    @staticmethod
    def _validate_definition(definition: AnalyticsContextDefinition) -> None:
        if (
            definition.anchor.event_type is not None
            and definition.anchor.event_type not in TECHNICAL_EVENT_BY_TYPE
        ):
            raise ValueError(f"unknown technical event anchor {definition.anchor.event_type!r}")
        for condition in definition.conditions:
            if condition.indicator_id is not None and condition.indicator_id not in INDICATOR_IDS:
                raise ValueError(f"unknown indicator id {condition.indicator_id!r}")
            if (
                condition.event_type is not None
                and condition.event_type not in TECHNICAL_EVENT_BY_TYPE
            ):
                raise ValueError(f"unknown technical event condition {condition.event_type!r}")
            if (
                condition.structure_field is StructureField.SWING_STRUCTURE
                and condition.expected_state not in {item.value for item in SwingStructure}
            ):
                raise ValueError(f"invalid swing structure {condition.expected_state!r}")
            if (
                condition.structure_field is StructureField.BREAKOUT_STATE
                and condition.expected_state not in {item.value for item in BreakoutState}
            ):
                raise ValueError(f"invalid breakout state {condition.expected_state!r}")
            if (
                condition.structure_field is StructureField.RANGE_LOCATION
                and condition.expected_state not in {item.value for item in RangeLocation}
            ):
                raise ValueError(f"invalid range location {condition.expected_state!r}")

    @staticmethod
    def _indicator(condition, anchor, index) -> ConditionEvaluation:
        snapshot = index.indicator_at(
            symbol=anchor.symbol,
            timeframe=condition.timeframe,
            at=anchor.anchor_at
        )
        if snapshot is None:
            return _miss(
                condition,
                expected=_expected(condition),
                evidence={"reason": "snapshot_unavailable"}
            )
        value = snapshot.value(condition.indicator_id)
        if not value.available or not value.warmup_complete or value.value is None:
            return _miss(
                condition,
                expected=_expected(condition),
                source_ref=snapshot.snapshot_fingerprint,
                source_available_at=snapshot.as_of,
                evidence={
                    "reason": "indicator_unavailable_or_warmup",
                    "indicator_id": condition.indicator_id
                },
            )
        matched = _numeric_match(value.value, condition)
        return ConditionEvaluation(
            condition_id=condition.condition_id,
            matched=matched,
            observed_value=value.value,
            operator=condition.operator.value,
            expected_value=_expected(condition),
            source_ref=snapshot.snapshot_fingerprint,
            source_available_at=snapshot.as_of,
            evidence={"indicator_id": condition.indicator_id, "timeframe": condition.timeframe},
        )

    @staticmethod
    def _event(condition, anchor, index) -> ConditionEvaluation:
        candidates = []
        for item in index.technical_events:
            if (
                item.symbol != anchor.symbol
                or item.timeframe != condition.timeframe
                or item.event_type != condition.event_type
            ):
                continue
            distance = index.bar_distance(
                symbol=anchor.symbol,
                timeframe=condition.timeframe,
                earlier=item.available_at,
                later=anchor.anchor_at
            )
            if distance is None:
                continue
            if _scope_accepts(condition, distance):
                candidates.append((distance, item))
        if not candidates:
            return _miss(
                condition,
                expected=condition.event_type,
                evidence={"scope": condition.scope.value}
            )
        _, item = min(
            candidates,
            key=lambda pair: (pair[0], pair[1].available_at, pair[1].event_id)
        )
        return ConditionEvaluation(
            condition.condition_id, True, item.event_type, "OCCURRED", condition.event_type,
            item.event_id, item.available_at,
            {
                "event_at": item.event_at,
                "direction": item.direction.value,
                "timeframe": item.timeframe
            },
        )

    @staticmethod
    def _pattern(condition, anchor, index) -> ConditionEvaluation:
        if condition.pattern_mode is PatternConditionMode.CURRENT_STATUS:
            candidates: list[tuple[Any, IndexedPatternTransition]] = []
            for pattern in index.pattern_occurrences:
                if (
                    pattern.symbol != anchor.symbol
                    or pattern.timeframe != condition.timeframe
                    or pattern.pattern_type != condition.pattern_type
                    or pattern.detected_at > anchor.anchor_at
                ):
                    continue
                visible = [
                    t for t in index.pattern_transitions
                    if t.pattern_id == pattern.pattern_id and t.available_at <= anchor.anchor_at
                ]
                if visible:
                    latest = max(
                        visible,
                        key=lambda item: (item.available_at, item.transition_fingerprint)
                    )
                    candidates.append((latest.available_at, latest))
            matching = [item for _, item in candidates if item.status == condition.pattern_status]
            if not matching:
                observed = max(
                    candidates,
                    key=lambda pair: pair[0]
                )[1].status.value if candidates else None
                return _miss(
                    condition,
                    observed=observed,
                    expected=condition.pattern_status.value,
                    evidence={"mode": condition.pattern_mode.value}
                )
            item = max(matching, key=lambda row: (row.available_at, row.pattern_id))
        else:
            matching = []
            for item in index.pattern_transitions:
                if (
                    item.symbol != anchor.symbol
                    or item.timeframe != condition.timeframe
                    or item.pattern_type != condition.pattern_type
                    or item.status != condition.pattern_status
                ):
                    continue
                distance = index.bar_distance(
                    symbol=anchor.symbol,
                    timeframe=condition.timeframe,
                    earlier=item.available_at,
                    later=anchor.anchor_at
                )
                if distance is not None and _scope_accepts(condition, distance):
                    matching.append((distance, item))
            if not matching:
                return _miss(
                    condition,
                    expected=condition.pattern_status.value,
                    evidence={"mode": condition.pattern_mode.value}
                )
            _, item = min(
                matching,
                key=lambda pair: (pair[0], pair[1].available_at, pair[1].pattern_id)
            )
        return ConditionEvaluation(
            condition.condition_id, True, item.status.value, "EQ", condition.pattern_status.value,
            f"{item.pattern_id}:{item.transition_fingerprint[:16]}", item.available_at,
            {
                "pattern_id": item.pattern_id,
                "pattern_type": item.pattern_type.value,
                "mode": condition.pattern_mode.value
            },
        )

    @staticmethod
    def _structure(condition, anchor, index) -> ConditionEvaluation:
        observation = index.structure_at(symbol=anchor.symbol, at=anchor.anchor_at)
        if observation is None:
            return _miss(
                condition,
                expected=condition.expected_state,
                evidence={"reason": "structure_unavailable"}
            )
        summary = observation.context.timeframes.get(condition.timeframe)
        if summary is None or not summary.structure_ready:
            return _miss(
                condition,
                expected=condition.expected_state,
                source_ref=observation.fingerprint,
                source_available_at=observation.as_of,
                evidence={"reason": "timeframe_unavailable_or_incomplete"},
            )
        observed = getattr(summary, condition.structure_field.value).value
        return ConditionEvaluation(
            condition.condition_id,
            observed == condition.expected_state,
            observed,
            "EQ",
            condition.expected_state,
            observation.fingerprint, observation.as_of,
            {"field": condition.structure_field.value, "timeframe": condition.timeframe},
        )

    @staticmethod
    def _zigzag(condition, anchor, index) -> ConditionEvaluation:
        candidates = []
        for item in index.zigzag_pivots:
            if (
                item.symbol != anchor.symbol
                or item.timeframe != condition.timeframe
                or item.kind != condition.pivot_kind
                or item.confirmed_at > anchor.anchor_at
            ):
                continue
            distance = index.bar_distance(
                symbol=anchor.symbol,
                timeframe=condition.timeframe,
                earlier=item.confirmed_at,
                later=anchor.anchor_at
            )
            if distance is None:
                continue
            if condition.scope is TemporalScope.AT_ANCHOR:
                if condition.max_bars_since is None or distance <= condition.max_bars_since:
                    candidates.append((distance, item))
            elif 1 <= distance <= condition.within_previous_bars:
                candidates.append((distance, item))
        if not candidates:
            return _miss(
                condition,
                expected=condition.pivot_kind.value,
                evidence={"max_bars_since": condition.max_bars_since}
            )
        distance, item = min(
            candidates,
            key=lambda pair: (pair[0], pair[1].confirmed_at, pair[1].pivot_id)
        )
        return ConditionEvaluation(
            condition.condition_id, True, item.kind.value, "EQ", condition.pivot_kind.value,
            item.pivot_id, item.confirmed_at,
            {
                "pivot_at": item.pivot_at,
                "confirmed_at": item.confirmed_at,
                "bars_since": distance,
                "price": item.price
            },
        )


def _scope_accepts(condition: AnalyticsConditionSpec, distance: int) -> bool:
    if condition.scope is TemporalScope.AT_ANCHOR:
        return distance == 0
    return 1 <= distance <= condition.within_previous_bars


def _numeric_match(value: float, condition: AnalyticsConditionSpec) -> bool:
    op = condition.operator
    if op is IndicatorOperator.GT:
        return value > condition.value
    if op is IndicatorOperator.GTE:
        return value >= condition.value
    if op is IndicatorOperator.LT:
        return value < condition.value
    if op is IndicatorOperator.LTE:
        return value <= condition.value
    if op is IndicatorOperator.EQ:
        return value == condition.value
    if op is IndicatorOperator.BETWEEN:
        return condition.min_value <= value <= condition.max_value
    raise AssertionError("unsupported indicator operator")


def _expected(condition: AnalyticsConditionSpec) -> Any:
    if condition.operator is IndicatorOperator.BETWEEN:
        return (condition.min_value, condition.max_value)
    return condition.value


def _miss(condition: AnalyticsConditionSpec, *, observed=None, expected=None, source_ref=None,
          source_available_at=None, evidence=None) -> ConditionEvaluation:
    return ConditionEvaluation(
        condition_id=condition.condition_id,
        matched=False,
        observed_value=observed,
        operator=condition.operator.value if condition.operator is not None else None,
        expected_value=expected,
        source_ref=source_ref,
        source_available_at=source_available_at,
        evidence=evidence or {},
    )


__all__ = ["AnalyticsContextResolver"]
