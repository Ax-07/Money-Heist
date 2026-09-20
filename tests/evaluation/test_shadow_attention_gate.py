from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.evaluation.shadow_attention import (
    ShadowAttentionComparison,
    build_shadow_attention_report,
    shadow_attention_export_name,
)


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


def scanner_record(
    *,
    scan_id: str,
    at: datetime,
    classification: str,
    score: int,
    matched: bool = True,
    triggers: tuple[str, ...] = (),
):
    return ns(
        scanner_evaluation_id=scan_id,
        observed_at=at,
        classification=classification,
        score=score,
        triggers=triggers,
        analytics=ns(
            status="MATCHED" if matched else "UNMATCHED",
            analytics_run_id="analytics-run",
            analytics_snapshot_id=f"snapshot-{scan_id}" if matched else None,
            analytics_as_of=at if matched else None,
        ),
    )


def projection(*records):
    return ns(
        analytics_available=True,
        source_backtest_run_id="run-1",
        analytics_run_id="analytics-run",
        role="DESIGN",
        records=tuple(records),
    )


def geometry(*, events=(), pivots=(), patterns=(), role="DESIGN", structure=()):
    return ns(
        analytics_run_id="analytics-run",
        role=role,
        technical_events=tuple(events),
        zigzag_pivots=tuple(pivots),
        patterns=tuple(patterns),
        structure=tuple(structure),
    )


def test_shadow_attention_v0_coalesces_same_bar_reasons_and_compares_scanner() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1, t2, t3, t4 = (t0 + timedelta(hours=i) for i in range(4))

    event1 = ns(
        available_at=t1,
        event_type="MACD_CROSS_ABOVE_SIGNAL",
        event_id="event-1",
        family="MOMENTUM",
        direction="BULLISH",
        timeframe="1h",
    )
    event2 = ns(
        available_at=t2,
        event_type="RSI_14_CROSS_ABOVE_50",
        event_id="event-2",
        family="MOMENTUM",
        direction="BULLISH",
        timeframe="1h",
    )
    pivot = ns(
        confirmed_at=t1,
        kind="LOW",
        pivot_id="pivot-1",
        timeframe="1h",
    )
    transition = ns(
        available_at=t1,
        status="CONFIRMED",
        fingerprint="f" * 64,
    )
    pattern = ns(
        pattern_type="DOUBLE_BOTTOM",
        family="REVERSAL",
        direction="BULLISH",
        timeframe="1h",
        pattern_id="pattern-1",
        transitions=(transition,),
    )

    scanner = projection(
        scanner_record(
            scan_id="scan-1",
            at=t1,
            classification="CANDIDATE_OPPORTUNITY",
            score=35,
            triggers=("RANGE_BREAK",),
        ),
        scanner_record(
            scan_id="scan-2",
            at=t2,
            classification="NO_TRIGGER",
            score=0,
        ),
        scanner_record(
            scan_id="scan-3",
            at=t3,
            classification="CANDIDATE_OPPORTUNITY",
            score=40,
            triggers=("VOLUME_EXPANSION", "VOLATILITY_EXPANSION"),
        ),
        scanner_record(
            scan_id="scan-4",
            at=t4,
            classification="NO_TRIGGER",
            score=0,
        ),
    )
    analytics_geometry = geometry(
        events=(event1, event2),
        pivots=(pivot,),
        patterns=(pattern,),
        # Structure is deliberately present but must remain context-only.
        structure=(ns(as_of=t4, state="MIXED"),),
    )

    report = build_shadow_attention_report(
        period_role="DESIGN",
        scanner_projection=scanner,
        geometry=analytics_geometry,
    )

    assert tuple(item.comparison for item in report.records) == (
        ShadowAttentionComparison.BOTH,
        ShadowAttentionComparison.SHADOW_ONLY,
        ShadowAttentionComparison.SCANNER_ONLY,
        ShadowAttentionComparison.NEITHER,
    )
    assert len(report.records[0].reasons) == 3
    assert report.summary.scanner_evaluations == 4
    assert report.summary.scanner_wakes == 2
    assert report.summary.shadow_wakes == 2
    assert report.summary.both == 1
    assert report.summary.shadow_only == 1
    assert report.summary.scanner_only == 1
    assert report.summary.neither == 1
    assert report.summary.technical_event_wakes == 2
    assert report.summary.zigzag_confirmation_wakes == 1
    assert report.summary.pattern_transition_wakes == 1


def test_shadow_attention_v0_requires_exact_scanner_analytics_time_parity() -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    record = scanner_record(
        scan_id="scan",
        at=at,
        classification="NO_TRIGGER",
        score=0,
    )
    record.analytics.analytics_as_of = at + timedelta(minutes=1)

    with pytest.raises(ValueError, match="exact Scanner ↔ Analytics as_of parity"):
        build_shadow_attention_report(
            period_role="DESIGN",
            scanner_projection=projection(record),
            geometry=geometry(),
        )


def test_shadow_attention_v0_is_fail_closed_when_analytics_is_unmatched() -> None:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    record = scanner_record(
        scan_id="scan",
        at=at,
        classification="CANDIDATE_OPPORTUNITY",
        score=35,
        matched=False,
        triggers=("RANGE_BREAK",),
    )
    report = build_shadow_attention_report(
        period_role="DESIGN",
        scanner_projection=projection(record),
        geometry=geometry(),
    )

    assert report.records[0].comparison is ShadowAttentionComparison.UNAVAILABLE
    assert report.records[0].scanner_wake is True
    assert report.records[0].shadow_wake is False
    assert report.summary.analytics_unmatched == 1
    assert report.summary.unavailable == 1
    assert report.summary.unavailable_scanner_wakes == 1
    assert report.summary.unavailable_scanner_sleeps == 0


def test_shadow_attention_export_name_is_role_scoped() -> None:
    assert shadow_attention_export_name("DESIGN") == "shadow-attention-v0-design.json"
    assert shadow_attention_export_name("VALIDATION") == "shadow-attention-v0-validation.json"
    assert shadow_attention_export_name("OOS") == "shadow-attention-v0-oos.json"
    with pytest.raises(ValueError):
        shadow_attention_export_name("LIVE")
