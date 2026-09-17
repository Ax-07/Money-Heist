from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType, SimpleNamespace

from app.services.frontend_v2.analytics_overlays import (
    build_frontend_analytics_geometry_projection,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 1, 1, hour, tzinfo=UTC)


def test_geometry_projection_deduplicates_cumulative_snapshot_components() -> None:
    evidence = SimpleNamespace(
        canonical_payload=lambda: {
            "previous_values": MappingProxyType({"rsi": 49.0}),
            "current_values": MappingProxyType({"rsi": 51.0}),
            "parameters": MappingProxyType({"threshold": 50.0}),
        }
    )
    event = SimpleNamespace(
        event_id="event-1",
        event_type="RSI_CROSS_50_UP",
        family="MOMENTUM",
        direction="BULLISH",
        symbol="BTC/EUR",
        timeframe="1h",
        event_at=_dt(8),
        available_at=_dt(8),
        event_fingerprint="a" * 64,
        evidence=evidence,
    )
    pivot = SimpleNamespace(
        pivot_id="pivot-1",
        kind="HIGH",
        symbol="BTC/EUR",
        timeframe="1h",
        pivot_at=_dt(8),
        confirmed_at=_dt(14),
        price=Decimal("100"),
        atr_at_pivot=Decimal("2"),
        reversal_multiple=Decimal("2"),
        reversal_threshold=Decimal("4"),
        amplitude_pct=None,
        amplitude_atr=None,
        bars_from_previous=None,
        pivot_fingerprint="b" * 64,
    )
    snapshots = (
        SimpleNamespace(
            analytics_run_id="analytics-1",
            as_of=_dt(14),
            snapshot_id="s1",
            components={"technical_events": (event,), "zigzag_pivots": (pivot,)},
        ),
        SimpleNamespace(
            analytics_run_id="analytics-1",
            as_of=_dt(15),
            snapshot_id="s2",
            components={"technical_events": (event,), "zigzag_pivots": (pivot,)},
        ),
    )

    projection = build_frontend_analytics_geometry_projection(
        campaign_id="campaign-1",
        role="OOS",
        analytics_run_id="analytics-1",
        analytics_snapshots=snapshots,
    )

    assert len(projection.technical_events) == 1
    assert len(projection.zigzag_pivots) == 1
    assert projection.zigzag_pivots[0].pivot_at == _dt(8)
    assert projection.zigzag_pivots[0].confirmed_at == _dt(14)


def test_geometry_projection_rejects_foreign_analytics_run() -> None:
    snapshot = SimpleNamespace(
        analytics_run_id="other-run",
        as_of=_dt(8),
        snapshot_id="s1",
        components={},
    )
    try:
        build_frontend_analytics_geometry_projection(
            campaign_id="campaign-1",
            role="OOS",
            analytics_run_id="analytics-1",
            analytics_snapshots=(snapshot,),
        )
    except ValueError as exc:
        assert "another AnalyticsRun" in str(exc)
    else:
        raise AssertionError("foreign AnalyticsRun must be rejected")
