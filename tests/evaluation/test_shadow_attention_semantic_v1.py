from __future__ import annotations

from datetime import UTC, datetime

from app.evaluation.shadow_attention.models import (
    ShadowAttentionComparison,
    ShadowAttentionObservation,
    ShadowAttentionReason,
    ShadowAttentionReasonKind,
    ShadowAttentionReport,
    ShadowAttentionSummary,
)
from app.evaluation.shadow_attention.semantic_v1 import (
    SemanticAttentionClause,
    build_semantic_attention_v1_report,
)

AT = datetime(2026, 1, 1, tzinfo=UTC)


def reason(
    kind: ShadowAttentionReasonKind,
    key: str,
    source_id: str,
    **metadata: str,
) -> ShadowAttentionReason:
    return ShadowAttentionReason(
        kind=kind,
        key=key,
        source_id=source_id,
        available_at=AT,
        metadata=metadata,
    )


def source_report(
    reasons: tuple[ShadowAttentionReason, ...],
    *,
    scanner_wake: bool = False,
    matched: bool = True,
) -> ShadowAttentionReport:
    reasons = tuple(sorted(reasons, key=lambda item: (item.kind.value, item.key, item.source_id)))
    v0_wake = bool(reasons) if matched else False
    if not matched:
        comparison = ShadowAttentionComparison.UNAVAILABLE
    elif scanner_wake and v0_wake:
        comparison = ShadowAttentionComparison.BOTH
    elif scanner_wake:
        comparison = ShadowAttentionComparison.SCANNER_ONLY
    elif v0_wake:
        comparison = ShadowAttentionComparison.SHADOW_ONLY
    else:
        comparison = ShadowAttentionComparison.NEITHER
    observation = ShadowAttentionObservation(
        observation_id="v0-observation",
        scanner_evaluation_id="scan-1",
        observed_at=AT,
        analytics_matched=matched,
        analytics_snapshot_id="snapshot-1" if matched else None,
        scanner_classification=(
            "CANDIDATE_OPPORTUNITY" if scanner_wake else "NO_TRIGGER"
        ),
        scanner_score=35 if scanner_wake else 0,
        scanner_triggers=("RANGE_BREAK",) if scanner_wake else (),
        scanner_wake=scanner_wake,
        shadow_wake=v0_wake,
        comparison=comparison,
        reasons=reasons if matched else (),
    )
    summary = ShadowAttentionSummary(
        scanner_evaluations=1,
        analytics_matched=1 if matched else 0,
        analytics_unmatched=0 if matched else 1,
        scanner_wakes=1 if scanner_wake else 0,
        shadow_wakes=1 if v0_wake else 0,
        both=1 if comparison is ShadowAttentionComparison.BOTH else 0,
        scanner_only=1 if comparison is ShadowAttentionComparison.SCANNER_ONLY else 0,
        shadow_only=1 if comparison is ShadowAttentionComparison.SHADOW_ONLY else 0,
        neither=1 if comparison is ShadowAttentionComparison.NEITHER else 0,
        unavailable=1 if comparison is ShadowAttentionComparison.UNAVAILABLE else 0,
        unavailable_scanner_wakes=1 if not matched and scanner_wake else 0,
        unavailable_scanner_sleeps=1 if not matched and not scanner_wake else 0,
        technical_event_wakes=(
            1
            if any(
                item.kind is ShadowAttentionReasonKind.TECHNICAL_EVENT
                for item in reasons
            )
            else 0
        ),
        zigzag_confirmation_wakes=(
            1
            if any(item.kind is ShadowAttentionReasonKind.ZIGZAG_CONFIRMATION for item in reasons)
            else 0
        ),
        pattern_transition_wakes=(
            1
            if any(item.kind is ShadowAttentionReasonKind.PATTERN_TRANSITION for item in reasons)
            else 0
        ),
    )
    return ShadowAttentionReport(
        source_backtest_run_id="run-1",
        analytics_run_id="analytics-1",
        period_role="DESIGN",
        summary=summary,
        records=(observation,),
    )


def test_v1_requires_two_distinct_technical_families_not_two_events() -> None:
    same_family = source_report(
        (
            reason(
                ShadowAttentionReasonKind.TECHNICAL_EVENT,
                "RSI_14_CROSS_ABOVE_50",
                "event-1",
                family="MOMENTUM",
                direction="BULLISH",
                timeframe="15m",
            ),
            reason(
                ShadowAttentionReasonKind.TECHNICAL_EVENT,
                "ROC_12_CROSS_ABOVE_ZERO",
                "event-2",
                family="MOMENTUM",
                direction="BULLISH",
                timeframe="15m",
            ),
        )
    )
    diverse = source_report(
        same_family.records[0].reasons
        + (
            reason(
                ShadowAttentionReasonKind.TECHNICAL_EVENT,
                "MACD_CROSS_ABOVE_SIGNAL",
                "event-3",
                family="TREND",
                direction="BULLISH",
                timeframe="15m",
            ),
        )
    )

    assert not build_semantic_attention_v1_report(same_family).records[0].shadow_wake
    record = build_semantic_attention_v1_report(diverse).records[0]
    assert record.shadow_wake
    assert record.clauses == (SemanticAttentionClause.DIVERSE_TECHNICAL_FAMILIES,)


def test_v1_wakes_on_technical_plus_zigzag_without_using_direction() -> None:
    source = source_report(
        (
            reason(
                ShadowAttentionReasonKind.TECHNICAL_EVENT,
                "RSI_14_CROSS_BELOW_50",
                "event-1",
                family="MOMENTUM",
                direction="BEARISH",
                timeframe="15m",
            ),
            reason(
                ShadowAttentionReasonKind.ZIGZAG_CONFIRMATION,
                "LOW_CONFIRMED",
                "pivot-1",
                timeframe="15m",
            ),
        )
    )

    record = build_semantic_attention_v1_report(source).records[0]
    assert record.shadow_wake
    assert record.clauses == (SemanticAttentionClause.TECHNICAL_PLUS_ZIGZAG,)


def test_v1_excludes_forming_pattern_but_accepts_mature_transition() -> None:
    forming = source_report(
        (
            reason(
                ShadowAttentionReasonKind.PATTERN_TRANSITION,
                "DOUBLE_BOTTOM:FORMING",
                "pattern-transition-1",
                family="REVERSAL",
                direction="BULLISH",
                timeframe="15m",
            ),
        )
    )
    mature = source_report(
        (
            reason(
                ShadowAttentionReasonKind.PATTERN_TRANSITION,
                "DOUBLE_BOTTOM:CONFIRMED",
                "pattern-transition-2",
                family="REVERSAL",
                direction="BULLISH",
                timeframe="15m",
            ),
        )
    )

    assert not build_semantic_attention_v1_report(forming).records[0].shadow_wake
    record = build_semantic_attention_v1_report(mature).records[0]
    assert record.shadow_wake
    assert record.clauses == (SemanticAttentionClause.MATURE_PATTERN_TRANSITION,)


def test_v1_unmatched_analytics_stays_fail_closed_and_conserves_scanner_wake() -> None:
    source = source_report((), scanner_wake=True, matched=False)

    report = build_semantic_attention_v1_report(source)
    record = report.records[0]
    assert record.comparison is ShadowAttentionComparison.UNAVAILABLE
    assert not record.shadow_wake
    assert report.summary.scanner_wakes == 1
    assert report.summary.unavailable_scanner_wakes == 1


def test_v1_policy_is_same_bar_direction_neutral_and_outcome_free() -> None:
    import inspect

    from app.evaluation.shadow_attention import semantic_v1

    source = inspect.getsource(semantic_v1)
    assert 'metadata.get("direction"' not in source
    assert "ForwardOutcome" not in source
    assert "return_pct" not in source
    assert "cooldown" not in source.lower()
