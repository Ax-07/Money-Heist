from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.services.backtest.historical_derivatives import (
    HISTORICAL_DERIVATIVES_ARCHIVE_VERSION,
    HistoricalFundingArchive,
    normalize_kraken_funding_csv,
)


START = datetime(2026, 1, 1, tzinfo=UTC)


def _canonical(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "symbol,instrument,observed_at,available_at,funding_rate",
                "BTC/USDC,PF_XBTUSD,2026-01-01T00:00:00Z,2026-01-01T00:05:00Z,0.0001",
                "BTC/USDC,PF_XBTUSD,2026-01-01T01:00:00Z,2026-01-01T01:05:00Z,-0.0002",
                "BTC/USDC,PF_XBTUSD,2026-01-01T02:00:00Z,2026-01-01T02:05:00Z,0.0003",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_archive_is_deterministic_and_cutoff_safe(tmp_path: Path):
    source = _canonical(tmp_path / "funding.csv")
    first = HistoricalFundingArchive.from_canonical_csv(source)
    second = HistoricalFundingArchive.from_canonical_csv(source)

    assert first.version == HISTORICAL_DERIVATIVES_ARCHIVE_VERSION
    assert first.dataset_fingerprint == second.dataset_fingerprint

    assert first.point_at(
        as_of=START + timedelta(minutes=4),
        max_age=timedelta(hours=2),
    ) is None

    point = first.point_at(
        as_of=START + timedelta(minutes=6),
        max_age=timedelta(hours=2),
    )
    assert point is not None
    assert point.observed_at == START
    assert str(point.funding_rate) == "0.0001"

    still_old = first.point_at(
        as_of=START + timedelta(hours=1, minutes=4),
        max_age=timedelta(hours=2),
    )
    assert still_old is not None
    assert still_old.observed_at == START

    next_point = first.point_at(
        as_of=START + timedelta(hours=1, minutes=5),
        max_age=timedelta(hours=2),
    )
    assert next_point is not None
    assert next_point.observed_at == START + timedelta(hours=1)


def test_stale_funding_is_explicitly_unavailable(tmp_path: Path):
    archive = HistoricalFundingArchive.from_canonical_csv(
        _canonical(tmp_path / "funding.csv")
    )

    assert archive.point_at(
        as_of=START + timedelta(hours=6),
        max_age=timedelta(hours=2),
    ) is None


def test_funding_only_snapshot_and_rio_context_are_degraded_but_usable(
    tmp_path: Path,
):
    archive = HistoricalFundingArchive.from_canonical_csv(
        _canonical(tmp_path / "funding.csv")
    )
    as_of = START + timedelta(minutes=10)

    snapshot = archive.positioning_snapshot_at(as_of=as_of)
    assert snapshot is not None
    assert str(snapshot.funding_rate) == "0.0001"
    assert snapshot.open_interest is None
    assert snapshot.long_short_ratio is None
    assert "open_interest" in snapshot.missing_fields
    assert "long_short_ratio" in snapshot.missing_fields

    rio = archive.rio_context_at(as_of=as_of)
    assert rio is not None
    assert rio.data_quality == "DEGRADED"
    assert rio.funding_rate == pytest.approx(0.0001)
    assert rio.open_interest is None
    assert rio.usable is True


def test_archive_rejects_availability_before_observation(tmp_path: Path):
    source = tmp_path / "bad.csv"
    source.write_text(
        "\n".join(
            [
                "symbol,instrument,observed_at,available_at,funding_rate",
                "BTC/USDC,PF_XBTUSD,2026-01-01T01:00:00Z,2026-01-01T00:59:00Z,0.0001",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="available_at"):
        HistoricalFundingArchive.from_canonical_csv(source)


def test_raw_kraken_converter_autodetects_common_columns_and_binds_lag(
    tmp_path: Path,
):
    raw = tmp_path / "raw.csv"
    raw.write_text(
        "\n".join(
            [
                "timestamp,funding_rate,ignored",
                "2026-01-01T00:00:00Z,0.0001,x",
                "2026-01-01T01:00:00Z,-0.0002,y",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "canonical.csv"

    archive = normalize_kraken_funding_csv(
        input_path=raw,
        output_path=output,
        symbol="BTC/USDC",
        instrument="PF_XBTUSD",
        availability_lag=timedelta(minutes=5),
    )

    assert len(archive.points) == 2
    assert archive.points[0].available_at == START + timedelta(minutes=5)
    assert archive.points[1].available_at == (
        START + timedelta(hours=1, minutes=5)
    )
