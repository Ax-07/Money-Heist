from __future__ import annotations

from collections.abc import Mapping

from app.analytics.indicators.models import AnalyticsIndicatorSnapshot
from app.analytics.indicators.registry import (
    ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT,
    ANALYTICS_INDICATOR_REGISTRY_VERSION,
)

from .models import TechnicalEventEvidence, TechnicalEventObservation
from .registry import (
    TECHNICAL_EVENT_REGISTRY,
    TechnicalEventCondition,
    TechnicalEventDefinition,
)


class TechnicalEventInputError(ValueError):
    """Raised when two indicator snapshots cannot form one causal event transition."""


class TechnicalEventEngine:
    """Detect descriptive technical transitions from consecutive Analytics snapshots."""

    def detect(
        self,
        previous_snapshot: AnalyticsIndicatorSnapshot | None,
        current_snapshot: AnalyticsIndicatorSnapshot,
        *,
        analytics_run_id: str,
    ) -> tuple[TechnicalEventObservation, ...]:
        self._validate_snapshot(current_snapshot, role="current")
        if previous_snapshot is None:
            return ()
        self._validate_snapshot(previous_snapshot, role="previous")
        self._validate_pair(previous_snapshot, current_snapshot)

        # A higher-timeframe snapshot can be re-materialized while no new closed source
        # candle exists yet. It must not emit an event until candle_count advances.
        if current_snapshot.candle_count == previous_snapshot.candle_count:
            return ()
        if current_snapshot.candle_count != previous_snapshot.candle_count + 1:
            raise TechnicalEventInputError(
                "technical event detection requires consecutive indicator snapshots"
            )

        observations: list[TechnicalEventObservation] = []
        for definition in TECHNICAL_EVENT_REGISTRY:
            transition = self._transition_values(
                definition,
                previous_snapshot=previous_snapshot,
                current_snapshot=current_snapshot,
            )
            if transition is None:
                continue
            previous_values, current_values = transition
            if not self._matches(definition, previous_values, current_values):
                continue
            evidence = TechnicalEventEvidence(
                previous_values=previous_values,
                current_values=current_values,
                parameters={
                    **definition.parameters,
                    "condition": definition.condition.value,
                },
            )
            observations.append(
                TechnicalEventObservation.create(
                    analytics_run_id=analytics_run_id,
                    event_type=definition.event_type,
                    family=definition.family,
                    direction=definition.direction,
                    symbol=current_snapshot.symbol,
                    timeframe=current_snapshot.timeframe,
                    event_at=current_snapshot.as_of,
                    available_at=current_snapshot.as_of,
                    source_indicator_snapshot_fingerprint=current_snapshot.snapshot_fingerprint,
                    source_cursor_fingerprint=current_snapshot.source_cursor_fingerprint,
                    evidence=evidence,
                    definition_version=definition.definition_version,
                )
            )
        return tuple(observations)

    @staticmethod
    def _validate_snapshot(snapshot: AnalyticsIndicatorSnapshot, *, role: str) -> None:
        if snapshot.registry_version != ANALYTICS_INDICATOR_REGISTRY_VERSION:
            raise TechnicalEventInputError(
                f"{role} indicator snapshot does not use the installed Analytics registry version"
            )
        if snapshot.registry_fingerprint != ANALYTICS_INDICATOR_REGISTRY_FINGERPRINT:
            raise TechnicalEventInputError(
                f"{role} indicator snapshot does not use the installed Analytics "
                "registry fingerprint"
            )

    @staticmethod
    def _validate_pair(
        previous_snapshot: AnalyticsIndicatorSnapshot,
        current_snapshot: AnalyticsIndicatorSnapshot,
    ) -> None:
        if previous_snapshot.symbol != current_snapshot.symbol:
            raise TechnicalEventInputError("indicator snapshot symbols differ")
        if previous_snapshot.timeframe != current_snapshot.timeframe:
            raise TechnicalEventInputError("indicator snapshot timeframes differ")
        if current_snapshot.as_of <= previous_snapshot.as_of:
            raise TechnicalEventInputError("current indicator snapshot must be later than previous")
        if current_snapshot.candle_count < previous_snapshot.candle_count:
            raise TechnicalEventInputError("indicator candle_count cannot move backward")

    @staticmethod
    def _transition_values(
        definition: TechnicalEventDefinition,
        *,
        previous_snapshot: AnalyticsIndicatorSnapshot,
        current_snapshot: AnalyticsIndicatorSnapshot,
    ) -> tuple[dict[str, float], dict[str, float]] | None:
        previous_values: dict[str, float] = {}
        current_values: dict[str, float] = {}
        for indicator_id in definition.required_indicators:
            previous = previous_snapshot.value(indicator_id)
            current = current_snapshot.value(indicator_id)
            if not (
                previous.available
                and previous.warmup_complete
                and previous.value is not None
                and current.available
                and current.warmup_complete
                and current.value is not None
            ):
                return None
            previous_values[indicator_id] = previous.value
            current_values[indicator_id] = current.value
        return previous_values, current_values

    @staticmethod
    def _matches(
        definition: TechnicalEventDefinition,
        previous: Mapping[str, float],
        current: Mapping[str, float],
    ) -> bool:
        condition = definition.condition
        required = definition.required_indicators
        if condition in {
            TechnicalEventCondition.PAIR_CROSS_ABOVE,
            TechnicalEventCondition.PAIR_CROSS_BELOW,
        }:
            left, right = required
            previous_left = previous[left]
            previous_right = previous[right]
            current_left = current[left]
            current_right = current[right]
            if condition == TechnicalEventCondition.PAIR_CROSS_ABOVE:
                return previous_left <= previous_right and current_left > current_right
            return previous_left >= previous_right and current_left < current_right

        indicator_id = required[0]
        previous_value = previous[indicator_id]
        current_value = current[indicator_id]
        threshold = float(definition.parameters["threshold"])

        if condition == TechnicalEventCondition.THRESHOLD_CROSS_ABOVE:
            return previous_value <= threshold and current_value > threshold
        if condition == TechnicalEventCondition.THRESHOLD_CROSS_BELOW:
            return previous_value >= threshold and current_value < threshold
        if condition == TechnicalEventCondition.ENTER_BELOW:
            return previous_value >= threshold and current_value < threshold
        if condition == TechnicalEventCondition.EXIT_BELOW:
            return previous_value < threshold and current_value >= threshold
        if condition == TechnicalEventCondition.ENTER_ABOVE:
            return previous_value <= threshold and current_value > threshold
        if condition == TechnicalEventCondition.EXIT_ABOVE:
            return previous_value > threshold and current_value <= threshold
        if condition == TechnicalEventCondition.ENTER_AT_OR_ABOVE:
            return previous_value < threshold and current_value >= threshold
        raise AssertionError(f"unhandled technical event condition {condition!r}")


__all__ = ["TechnicalEventEngine", "TechnicalEventInputError"]
