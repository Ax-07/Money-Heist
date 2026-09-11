from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.services.backtest.historical_derivatives_analytics import (
    HISTORICAL_DERIVATIVES_ANALYTICS_VERSION,
    HistoricalDerivativesAnalyticsArchive,
)


START = datetime(2025, 9, 11, tzinfo=UTC)


def _archive(path: Path) -> HistoricalDerivativesAnalyticsArchive:
    path.write_text(
        "\n".join(
            [
                (
                    "symbol,instrument,observed_at,available_at,funding_rate,"
                    "open_interest,open_interest_change_pct,long_short_ratio"
                ),
                (
                    "BTC/USDC,PF_XBTUSD,2025-09-11T00:00:00Z,"
                    "2025-09-11T01:00:00Z,,1000,,1.10"
                ),
                (
                    "BTC/USDC,PF_XBTUSD,2025-09-11T01:00:00Z,"
                    "2025-09-11T02:00:00Z,,1100,10,1.20"
                ),
                (
                    "BTC/USDC,PF_XBTUSD,2026-02-12T13:00:00Z,"
                    "2026-02-12T14:00:00Z,0.0002,1200,9.090909,1.30"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return HistoricalDerivativesAnalyticsArchive.from_canonical_csv(path)


def test_archive_is_deterministic_and_versioned(tmp_path: Path):
    first = _archive(tmp_path / "a.csv")
    second = _archive(tmp_path / "b.csv")

    assert first.version == HISTORICAL_DERIVATIVES_ANALYTICS_VERSION
    assert first.dataset_fingerprint == second.dataset_fingerprint


def test_metric_lookup_respects_available_at_and_never_uses_future(tmp_path: Path):
    archive = _archive(tmp_path / "a.csv")

    assert archive.metric_at(
        "open_interest",
        as_of=START + timedelta(minutes=59),
        max_age=timedelta(hours=2),
    ) is None

    selected = archive.metric_at(
        "open_interest",
        as_of=START + timedelta(hours=1),
        max_age=timedelta(hours=2),
    )
    assert selected is not None
    point, value = selected
    assert point.observed_at == START
    assert str(value) == "1000"


def test_prefunding_rio_context_is_degraded_but_uses_real_oi_and_ratio(
    tmp_path: Path,
):
    archive = _archive(tmp_path / "a.csv")
    rio = archive.rio_context_at(
        as_of=START + timedelta(hours=2),
        max_age=timedelta(hours=2),
    )

    assert rio is not None
    assert rio.data_quality == "DEGRADED"
    assert rio.funding_rate is None
    assert rio.open_interest == pytest.approx(1100.0)
    assert rio.open_interest_change_pct == pytest.approx(10.0)
    assert rio.long_short_ratio == pytest.approx(1.2)
    assert "funding_rate" in rio.missing_fields
    assert rio.usable is True


def test_postfunding_rio_context_becomes_reliable(tmp_path: Path):
    archive = _archive(tmp_path / "a.csv")
    as_of = datetime(2026, 2, 12, 14, tzinfo=UTC)

    rio = archive.rio_context_at(
        as_of=as_of,
        max_age=timedelta(hours=2),
    )
    snapshot = archive.positioning_snapshot_at(
        as_of=as_of,
        max_age=timedelta(hours=2),
    )

    assert rio is not None
    assert snapshot is not None
    assert rio.data_quality == "RELIABLE"
    assert rio.funding_rate == pytest.approx(0.0002)
    assert rio.open_interest == pytest.approx(1200.0)
    assert rio.long_short_ratio == pytest.approx(1.3)
    assert "funding_rate" not in snapshot.missing_fields
    assert "long_liquidations_notional" in snapshot.missing_fields
    assert "short_liquidations_notional" in snapshot.missing_fields


def test_stale_metric_is_not_carried_forward_indefinitely(tmp_path: Path):
    archive = _archive(tmp_path / "a.csv")

    assert archive.metric_at(
        "long_short_ratio",
        as_of=START + timedelta(hours=10),
        max_age=timedelta(hours=2),
    ) is None
