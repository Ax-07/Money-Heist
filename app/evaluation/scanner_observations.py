from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ScannerOutcomeClassification(StrEnum):
    """Causal Scanner state at one replay observation time."""

    NO_TRIGGER = "NO_TRIGGER"
    TRIGGER_BELOW_CANDIDATE_THRESHOLD = "TRIGGER_BELOW_CANDIDATE_THRESHOLD"
    CANDIDATE_OPPORTUNITY = "CANDIDATE_OPPORTUNITY"


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def normalize_scanner_triggers(scan_result: Any) -> tuple[str, ...]:
    """Return the Scanner triggers as a deterministic, unique tuple of strings."""

    return tuple(
        sorted(
            {
                str(_value(item))
                for item in tuple(getattr(scan_result, "triggers", ()) or ())
                if _value(item) is not None
            }
        )
    )


def classify_scanner_result(scan_result: Any) -> ScannerOutcomeClassification:
    """Classify an already-produced ScanResult without rerunning the Scanner."""

    opportunity = getattr(scan_result, "opportunity", None)
    if opportunity is not None:
        return ScannerOutcomeClassification.CANDIDATE_OPPORTUNITY
    if normalize_scanner_triggers(scan_result):
        return ScannerOutcomeClassification.TRIGGER_BELOW_CANDIDATE_THRESHOLD
    return ScannerOutcomeClassification.NO_TRIGGER


def resolve_replay_policy_version(run: Any, point: Any) -> str | None:
    """Resolve the causal MTF policy while enforcing replay/context parity."""

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
    """Resolve the source cursor from replay provenance, never by reconstruction."""

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


def validate_optional_decision_context(
    *,
    point: Any,
    observed_at: datetime,
    symbol: str,
    decision_timeframe: str,
    cursor_fingerprint: str | None,
) -> tuple[str | None, str | None]:
    """Validate optional DecisionContext parity and return its stable references."""

    context = getattr(point, "decision_context", None)
    if context is None:
        return None, None

    context_as_of = _as_utc(
        context.as_of,
        field_name="DecisionContext.as_of",
    )
    if context_as_of != observed_at:
        raise ValueError("DecisionContext.as_of must match replay point observed_at")
    if str(context.symbol) != symbol:
        raise ValueError("DecisionContext.symbol must match observation symbol")
    if str(context.primary_timeframe) != decision_timeframe:
        raise ValueError(
            "DecisionContext.primary_timeframe must match observation timeframe"
        )
    if cursor_fingerprint is not None:
        market = getattr(context, "market", None)
        context_cursor = getattr(market, "source_cursor_fingerprint", None)
        if context_cursor is None or str(context_cursor) != cursor_fingerprint:
            raise ValueError(
                "DecisionContext market cursor fingerprint must match replay point"
            )

    return str(context.context_id), str(context.context_fingerprint)


__all__ = [
    "ScannerOutcomeClassification",
    "classify_scanner_result",
    "normalize_scanner_triggers",
    "resolve_replay_cursor_fingerprint",
    "resolve_replay_policy_version",
    "validate_optional_decision_context",
]
