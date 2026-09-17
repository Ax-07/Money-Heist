from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


class ScannerOutcomeClassification(StrEnum):
    NO_TRIGGER = "NO_TRIGGER"
    TRIGGER_BELOW_CANDIDATE_THRESHOLD = "TRIGGER_BELOW_CANDIDATE_THRESHOLD"
    CANDIDATE_OPPORTUNITY = "CANDIDATE_OPPORTUNITY"


def scanner_trigger_values(scan_result: Any) -> tuple[str, ...]:
    values = {
        text
        for item in tuple(getattr(scan_result, "triggers", ()) or ())
        if (text := _value(item)) is not None
    }
    return tuple(sorted(values))


def classify_scan_result(scan_result: Any) -> ScannerOutcomeClassification:
    opportunity = getattr(scan_result, "opportunity", None)
    if opportunity is not None:
        return ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY
    if tuple(getattr(scan_result, "triggers", ()) or ()):
        return ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD
    return ScannerOutcomeClassification.NO_TRIGGER


def resolve_replay_policy_version(run: Any, point: Any) -> str | None:
    assumptions = getattr(getattr(run, "config", None), "execution_assumptions", {})
    configured = str(assumptions.get("mtf_policy_version", "")).strip()
    context = getattr(point, "decision_context", None)
    context_policy = (
        str(getattr(context, "timeframe_policy_version", "")).strip()
        if context is not None
        else ""
    )
    if configured and context_policy and configured != context_policy:
        raise ValueError("DecisionContext timeframe policy conflicts with BacktestRun")
    return configured or context_policy or None


def resolve_replay_cursor_fingerprint(point: Any) -> str | None:
    point_cursor = getattr(point, "mtf_cursor_fingerprint", None)
    context = getattr(point, "decision_context", None)
    context_cursor = None
    if context is not None:
        market = getattr(context, "market", None)
        context_cursor = getattr(market, "source_cursor_fingerprint", None)
    if (
        point_cursor is not None
        and context_cursor is not None
        and str(point_cursor) != str(context_cursor)
    ):
        raise ValueError(
            "DecisionContext market cursor fingerprint conflicts with replay point"
        )
    value = point_cursor if point_cursor is not None else context_cursor
    return str(value) if value is not None else None


def validate_replay_decision_context(
    *,
    point: Any,
    observed_at: datetime,
    symbol: str,
    decision_timeframe: str,
    cursor_fingerprint: str | None,
) -> tuple[str | None, str | None]:
    context = getattr(point, "decision_context", None)
    if context is None:
        return None, None

    context_as_of = _as_utc(context.as_of, field_name="DecisionContext.as_of")
    if context_as_of != observed_at:
        raise ValueError("DecisionContext.as_of must match replay point observed_at")
    if str(context.symbol) != symbol:
        raise ValueError("DecisionContext.symbol must match replay observation symbol")
    if str(context.primary_timeframe) != decision_timeframe:
        raise ValueError(
            "DecisionContext.primary_timeframe must match replay decision_timeframe"
        )
    if cursor_fingerprint is not None:
        market = getattr(context, "market", None)
        context_cursor = getattr(market, "source_cursor_fingerprint", None)
        if context_cursor is None or str(context_cursor) != cursor_fingerprint:
            raise ValueError(
                "DecisionContext market cursor fingerprint must match replay point"
            )

    context_id = getattr(context, "context_id", None)
    context_fingerprint = getattr(context, "context_fingerprint", None)
    if (context_id is None) != (context_fingerprint is None):
        raise ValueError(
            "DecisionContext id and fingerprint provenance must be set together"
        )
    return (
        str(context_id) if context_id is not None else None,
        str(context_fingerprint) if context_fingerprint is not None else None,
    )


class ScannerObservation(FrozenModel):
    """State-at-T Scanner facts emitted by Historical Replay without rerunning Scanner."""

    scanner_evaluation_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    observed_at: datetime
    symbol: str = Field(min_length=1)
    decision_timeframe: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    scanner_version: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
    candidate_threshold: int = Field(ge=0, le=100)
    score_margin: int = Field(ge=-100, le=100)
    triggers: tuple[str, ...] = ()
    market_regime: str | None = None
    classification: ScannerOutcomeClassification
    candidate_opportunity_id: str | None = None

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _as_utc(value, field_name="observed_at")

    @model_validator(mode="after")
    def validate_contract(self) -> ScannerObservation:
        if self.scanner_evaluation_id != self.snapshot_id:
            raise ValueError(
                "scanner_evaluation_id must equal canonical FeatureSnapshot.snapshot_id"
            )
        if tuple(sorted(set(self.triggers))) != self.triggers:
            raise ValueError("triggers must be sorted and unique")
        if self.score_margin != self.score - self.candidate_threshold:
            raise ValueError("score_margin must equal score - candidate_threshold")

        if self.classification is ScannerOutcomeClassification.NO_TRIGGER:
            if self.triggers:
                raise ValueError("NO_TRIGGER cannot contain triggers")
            if self.candidate_opportunity_id is not None:
                raise ValueError("NO_TRIGGER cannot contain a candidate opportunity")
        elif (
            self.classification
            is ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD
        ):
            if not self.triggers:
                raise ValueError("below-threshold classification requires triggers")
            if self.candidate_opportunity_id is not None:
                raise ValueError(
                    "below-threshold classification cannot contain a candidate"
                )
            if self.score >= self.candidate_threshold:
                raise ValueError(
                    "below-threshold classification requires score < threshold"
                )
        else:
            if not self.triggers:
                raise ValueError("candidate classification requires triggers")
            if self.candidate_opportunity_id is None:
                raise ValueError("candidate classification requires opportunity id")
            if self.score < self.candidate_threshold:
                raise ValueError(
                    "candidate classification requires score >= threshold"
                )
        return self


def build_scanner_observation(
    point: Any,
    *,
    scanner_version: str,
    min_priority_score: int,
) -> ScannerObservation:
    """Project an existing replay point into the canonical Scanner State@T contract."""

    scan_result = getattr(point, "scan_result", None)
    feature = getattr(point, "feature_snapshot", None)
    if scan_result is None or feature is None:
        raise ValueError(
            "Scanner observation requires scan_result and feature_snapshot "
            "for every replay point"
        )

    observed_at = _as_utc(point.observed_at, field_name="replay point observed_at")
    feature_observed_at = _as_utc(
        feature.observed_at,
        field_name="FeatureSnapshot.observed_at",
    )
    if observed_at != feature_observed_at:
        raise ValueError("FeatureSnapshot.observed_at must match replay point observed_at")

    configured_scanner_version = str(scanner_version)
    snapshot_id = str(feature.snapshot_id)
    score = int(scan_result.score)
    triggers = scanner_trigger_values(scan_result)
    classification = classify_scan_result(scan_result)
    opportunity = getattr(scan_result, "opportunity", None)

    candidate_id = None
    if opportunity is not None:
        candidate_id = str(opportunity.opportunity_id)
        if str(opportunity.snapshot_id) != snapshot_id:
            raise ValueError(
                "CandidateOpportunity.snapshot_id must match FeatureSnapshot.snapshot_id"
            )
        if int(opportunity.priority_score) != score:
            raise ValueError(
                "CandidateOpportunity.priority_score must match ScanResult.score"
            )
        if str(opportunity.scanner_version) != configured_scanner_version:
            raise ValueError(
                "CandidateOpportunity.scanner_version must match configured Scanner"
            )
        if (
            _as_utc(
                opportunity.created_at,
                field_name="CandidateOpportunity.created_at",
            )
            != observed_at
        ):
            raise ValueError(
                "CandidateOpportunity.created_at must match replay point observed_at"
            )
        candidate_triggers = tuple(
            sorted(
                text
                for item in opportunity.triggers
                if (text := _value(item)) is not None
            )
        )
        if candidate_triggers != triggers:
            raise ValueError(
                "CandidateOpportunity.triggers must match ScanResult.triggers"
            )

    decision_timeframe = str(
        getattr(point, "decision_timeframe", None) or feature.timeframe
    )
    feature_timeframe = str(feature.timeframe)
    if decision_timeframe != feature_timeframe:
        raise ValueError("replay decision_timeframe must match FeatureSnapshot.timeframe")

    return ScannerObservation(
        scanner_evaluation_id=snapshot_id,
        snapshot_id=snapshot_id,
        observed_at=observed_at,
        symbol=str(feature.symbol),
        decision_timeframe=decision_timeframe,
        feature_version=str(feature.feature_version),
        scanner_version=configured_scanner_version,
        score=score,
        candidate_threshold=int(min_priority_score),
        score_margin=score - int(min_priority_score),
        triggers=triggers,
        market_regime=_value(getattr(feature, "regime", None)),
        classification=classification,
        candidate_opportunity_id=candidate_id,
    )


__all__ = [
    "ScannerObservation",
    "ScannerOutcomeClassification",
    "build_scanner_observation",
    "classify_scan_result",
    "resolve_replay_cursor_fingerprint",
    "resolve_replay_policy_version",
    "scanner_trigger_values",
    "validate_replay_decision_context",
]
