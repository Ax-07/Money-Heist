from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from app.common.canonical import stable_uuid

from .models import (
    ShadowAttentionComparison,
    ShadowAttentionObservation,
    ShadowAttentionReason,
    ShadowAttentionReasonKind,
    ShadowAttentionReport,
    ShadowAttentionSummary,
)

CANDIDATE = "CANDIDATE_OPPORTUNITY"
MATCHED = "MATCHED"


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _reason(
    *,
    kind: ShadowAttentionReasonKind,
    key: str,
    source_id: str,
    available_at: datetime,
    metadata: dict[str, str] | None = None,
) -> ShadowAttentionReason:
    return ShadowAttentionReason(
        kind=kind,
        key=key,
        source_id=source_id,
        available_at=available_at,
        metadata=dict(sorted((metadata or {}).items())),
    )


def _reason_index(geometry: Any) -> dict[datetime, tuple[ShadowAttentionReason, ...]]:
    by_time: dict[datetime, dict[tuple[str, str, str], ShadowAttentionReason]] = defaultdict(dict)

    for item in tuple(geometry.technical_events or ()):
        available_at = _utc(item.available_at, field="TechnicalEvent.available_at")
        reason = _reason(
            kind=ShadowAttentionReasonKind.TECHNICAL_EVENT,
            key=_value(item.event_type),
            source_id=str(item.event_id),
            available_at=available_at,
            metadata={
                "family": _value(item.family),
                "direction": _value(item.direction),
                "timeframe": str(item.timeframe),
            },
        )
        by_time[available_at][(reason.kind.value, reason.key, reason.source_id)] = reason

    for item in tuple(geometry.zigzag_pivots or ()):
        confirmed_at = _utc(item.confirmed_at, field="ZigZagPivot.confirmed_at")
        reason = _reason(
            kind=ShadowAttentionReasonKind.ZIGZAG_CONFIRMATION,
            key=f"{_value(item.kind)}_CONFIRMED",
            source_id=str(item.pivot_id),
            available_at=confirmed_at,
            metadata={"timeframe": str(item.timeframe)},
        )
        by_time[confirmed_at][(reason.kind.value, reason.key, reason.source_id)] = reason

    for pattern in tuple(geometry.patterns or ()):
        for transition in tuple(pattern.transitions or ()):
            available_at = _utc(
                transition.available_at,
                field="PatternTransition.available_at",
            )
            reason = _reason(
                kind=ShadowAttentionReasonKind.PATTERN_TRANSITION,
                key=f"{_value(pattern.pattern_type)}:{_value(transition.status)}",
                source_id=str(transition.fingerprint),
                available_at=available_at,
                metadata={
                    "family": _value(pattern.family),
                    "direction": _value(pattern.direction),
                    "timeframe": str(pattern.timeframe),
                    "pattern_id": str(pattern.pattern_id),
                },
            )
            by_time[available_at][(reason.kind.value, reason.key, reason.source_id)] = reason

    return {
        at: tuple(items[key] for key in sorted(items))
        for at, items in sorted(by_time.items())
    }


def _comparison(
    *,
    matched: bool,
    scanner_wake: bool,
    shadow_wake: bool,
) -> ShadowAttentionComparison:
    if not matched:
        return ShadowAttentionComparison.UNAVAILABLE
    if scanner_wake and shadow_wake:
        return ShadowAttentionComparison.BOTH
    if scanner_wake:
        return ShadowAttentionComparison.SCANNER_ONLY
    if shadow_wake:
        return ShadowAttentionComparison.SHADOW_ONLY
    return ShadowAttentionComparison.NEITHER


def build_shadow_attention_report(
    *,
    period_role: str,
    scanner_projection: Any,
    geometry: Any,
) -> ShadowAttentionReport:
    """Compare Scanner wake-ups with causal Analytics attention, post-hoc only.

    The inputs are already-persistable 24C projections. V0 deliberately has no
    score, threshold, cooldown, direction, setup or trading authority. Technical
    Events, same-bar ZigZag confirmations and same-bar Pattern transitions are
    coalesced into one observation per existing Scanner evaluation. Market
    structure remains context-only and cannot wake V0 by itself.
    """

    if not bool(scanner_projection.analytics_available):
        raise ValueError("Shadow Attention requires an available Scanner Analytics projection")
    if scanner_projection.source_backtest_run_id is None:
        raise ValueError("Scanner Analytics projection is missing source_backtest_run_id")
    if scanner_projection.analytics_run_id is None:
        raise ValueError("Scanner Analytics projection is missing analytics_run_id")
    source_backtest_run_id = str(scanner_projection.source_backtest_run_id)
    analytics_run_id = str(scanner_projection.analytics_run_id)
    if str(geometry.analytics_run_id) != analytics_run_id:
        raise ValueError("Shadow Attention inputs belong to different Analytics runs")
    if str(scanner_projection.role) != str(period_role):
        raise ValueError("Scanner projection period role mismatch")
    if str(geometry.role) != str(period_role):
        raise ValueError("Analytics geometry period role mismatch")

    reasons_by_time = _reason_index(geometry)
    records: list[ShadowAttentionObservation] = []
    reason_wake_counts: Counter[ShadowAttentionReasonKind] = Counter()

    for scanner in scanner_projection.records:
        observed_at = _utc(scanner.observed_at, field="ScannerObservation.observed_at")
        scanner_id = str(scanner.scanner_evaluation_id)
        classification = _value(scanner.classification)
        scanner_wake = classification == CANDIDATE
        analytics = scanner.analytics
        if str(analytics.analytics_run_id) != analytics_run_id:
            raise ValueError("Scanner Analytics reference belongs to another Analytics run")

        matched = _value(analytics.status) == MATCHED
        snapshot_id = (
            str(analytics.analytics_snapshot_id)
            if matched and analytics.analytics_snapshot_id is not None
            else None
        )
        reasons: tuple[ShadowAttentionReason, ...] = ()
        if matched:
            if snapshot_id is None:
                raise ValueError("MATCHED Scanner Analytics attribution is missing snapshot_id")
            if analytics.analytics_as_of is None:
                raise ValueError("MATCHED Scanner Analytics attribution is missing analytics_as_of")
            analytics_as_of = _utc(
                analytics.analytics_as_of,
                field="ScannerAnalyticsRef.analytics_as_of",
            )
            if analytics_as_of != observed_at:
                raise ValueError("Shadow Attention requires exact Scanner ↔ Analytics as_of parity")
            reasons = reasons_by_time.get(observed_at, ())

        shadow_wake = bool(reasons)
        for kind in {reason.kind for reason in reasons}:
            reason_wake_counts[kind] += 1

        identity = {
            "policy": "shadow-attention-observation-only-v0",
            "source_backtest_run_id": source_backtest_run_id,
            "analytics_run_id": analytics_run_id,
            "period_role": str(period_role),
            "scanner_evaluation_id": scanner_id,
            "observed_at": observed_at,
            "analytics_snapshot_id": snapshot_id,
            "scanner_classification": classification,
            "reasons": tuple(
                (reason.kind.value, reason.key, reason.source_id, reason.available_at)
                for reason in reasons
            ),
        }
        records.append(
            ShadowAttentionObservation(
                observation_id=stable_uuid("shadow-attention-observation", identity),
                scanner_evaluation_id=scanner_id,
                observed_at=observed_at,
                analytics_matched=matched,
                analytics_snapshot_id=snapshot_id,
                scanner_classification=classification,
                scanner_score=int(scanner.score),
                scanner_triggers=tuple(sorted({_value(item) for item in scanner.triggers})),
                scanner_wake=scanner_wake,
                shadow_wake=shadow_wake,
                comparison=_comparison(
                    matched=matched,
                    scanner_wake=scanner_wake,
                    shadow_wake=shadow_wake,
                ),
                reasons=reasons,
            )
        )

    ordered = tuple(
        sorted(
            records,
            key=lambda item: (item.observed_at, item.scanner_evaluation_id),
        )
    )
    comparisons = Counter(item.comparison for item in ordered)
    summary = ShadowAttentionSummary(
        scanner_evaluations=len(ordered),
        analytics_matched=sum(item.analytics_matched for item in ordered),
        analytics_unmatched=sum(not item.analytics_matched for item in ordered),
        scanner_wakes=sum(item.scanner_wake for item in ordered),
        shadow_wakes=sum(item.shadow_wake for item in ordered),
        both=comparisons[ShadowAttentionComparison.BOTH],
        scanner_only=comparisons[ShadowAttentionComparison.SCANNER_ONLY],
        shadow_only=comparisons[ShadowAttentionComparison.SHADOW_ONLY],
        neither=comparisons[ShadowAttentionComparison.NEITHER],
        unavailable=comparisons[ShadowAttentionComparison.UNAVAILABLE],
        unavailable_scanner_wakes=sum(
            item.comparison is ShadowAttentionComparison.UNAVAILABLE and item.scanner_wake
            for item in ordered
        ),
        unavailable_scanner_sleeps=sum(
            item.comparison is ShadowAttentionComparison.UNAVAILABLE and not item.scanner_wake
            for item in ordered
        ),
        technical_event_wakes=reason_wake_counts[ShadowAttentionReasonKind.TECHNICAL_EVENT],
        zigzag_confirmation_wakes=reason_wake_counts[
            ShadowAttentionReasonKind.ZIGZAG_CONFIRMATION
        ],
        pattern_transition_wakes=reason_wake_counts[
            ShadowAttentionReasonKind.PATTERN_TRANSITION
        ],
    )
    return ShadowAttentionReport(
        source_backtest_run_id=source_backtest_run_id,
        analytics_run_id=analytics_run_id,
        period_role=str(period_role),
        summary=summary,
        records=ordered,
    )


def shadow_attention_export_name(period_role: str) -> str:
    normalized = str(getattr(period_role, "value", period_role)).strip().lower()
    if normalized not in {"design", "validation", "oos"}:
        raise ValueError("period_role must be DESIGN, VALIDATION or OOS")
    return f"shadow-attention-v0-{normalized}.json"


__all__ = ["build_shadow_attention_report", "shadow_attention_export_name"]
