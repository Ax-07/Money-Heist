from pathlib import Path

import pytest

from app.services.backtest.derivatives_runtime import (
    DERIVATIVES_RUNTIME_VERSION,
    historical_derivatives_execution_assumptions,
    historical_derivatives_runner_kwargs,
)
from app.services.backtest.historical_derivatives_analytics import (
    HistoricalDerivativesAnalyticsArchive,
)
from app.services.backtest.mtf_runtime import mtf_execution_assumptions


def _archive(tmp_path: Path) -> HistoricalDerivativesAnalyticsArchive:
    path = tmp_path / "derivatives.csv"
    path.write_text(
        "\n".join(
            [
                (
                    "symbol,instrument,observed_at,available_at,funding_rate,"
                    "open_interest,open_interest_change_pct,long_short_ratio"
                ),
                (
                    "BTC/USDC,PF_XBTUSD,2026-01-01T00:00:00Z,"
                    "2026-01-01T01:00:00Z,,1000,1,1.1"
                ),
                (
                    "BTC/USDC,PF_XBTUSD,2026-01-01T01:00:00Z,"
                    "2026-01-01T02:00:00Z,0.0001,1010,1,1.2"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return HistoricalDerivativesAnalyticsArchive.from_canonical_csv(path)


def test_explicit_derivatives_runtime_binds_archive_identity(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    assumptions = mtf_execution_assumptions("1m")
    assumptions.update(
        historical_derivatives_execution_assumptions(
            archive,
            max_age_seconds=7200,
        )
    )

    assert assumptions["derivatives_runtime_version"] == (
        DERIVATIVES_RUNTIME_VERSION
    )
    assert assumptions["derivatives_archive_fingerprint"] == (
        archive.dataset_fingerprint
    )

    kwargs = historical_derivatives_runner_kwargs(assumptions, archive)
    assert kwargs["historical_derivatives_archive"] is archive
    assert int(kwargs["derivatives_max_age"].total_seconds()) == 7200
    assert kwargs["derivatives_context_binding_version"] == (
        "historical-derivatives-rio-v1"
    )


def test_archive_without_runtime_marker_fails_closed(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    with pytest.raises(ValueError, match="not enabled"):
        historical_derivatives_runner_kwargs(
            mtf_execution_assumptions("1m"),
            archive,
        )


def test_enabled_runtime_without_archive_fails_closed(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    assumptions = mtf_execution_assumptions("1m")
    assumptions.update(
        historical_derivatives_execution_assumptions(
            archive,
            max_age_seconds=7200,
        )
    )
    with pytest.raises(ValueError, match="requires the validated archive"):
        historical_derivatives_runner_kwargs(assumptions, None)


def test_tampered_archive_identity_fails_closed(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    assumptions = mtf_execution_assumptions("1m")
    assumptions.update(
        historical_derivatives_execution_assumptions(
            archive,
            max_age_seconds=7200,
        )
    )
    assumptions["derivatives_archive_fingerprint"] = "0" * 64

    with pytest.raises(ValueError, match="derivatives_archive_fingerprint"):
        historical_derivatives_runner_kwargs(assumptions, archive)


def test_no_marker_and_no_archive_remains_disabled() -> None:
    assert historical_derivatives_runner_kwargs({}, None) == {}
