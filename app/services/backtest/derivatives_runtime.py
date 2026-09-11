from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta

from app.services.backtest.historical_derivatives_analytics import (
    HISTORICAL_DERIVATIVES_CONTEXT_BINDING_VERSION,
    HistoricalDerivativesAnalyticsArchive,
)
from app.services.backtest.mtf_runtime import MTF_RUNTIME_VERSION


DERIVATIVES_RUNTIME_VERSION = "historical-derivatives-runtime-v1"


def historical_derivatives_execution_assumptions(
    archive: HistoricalDerivativesAnalyticsArchive,
    *,
    max_age_seconds: int,
) -> dict[str, str]:
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int):
        raise TypeError("max_age_seconds must be an integer")
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be > 0")

    return {
        "derivatives_runtime_version": DERIVATIVES_RUNTIME_VERSION,
        "derivatives_context_binding_version": (
            HISTORICAL_DERIVATIVES_CONTEXT_BINDING_VERSION
        ),
        "derivatives_archive_version": archive.version,
        "derivatives_archive_fingerprint": archive.dataset_fingerprint,
        "derivatives_source": archive.source,
        "derivatives_instrument": archive.instrument,
        "derivatives_max_age_seconds": str(max_age_seconds),
    }


def historical_derivatives_runner_kwargs(
    assumptions: Mapping[str, str],
    archive: HistoricalDerivativesAnalyticsArchive | None,
) -> dict[str, object]:
    marker = assumptions.get("derivatives_runtime_version")
    if marker is None:
        if archive is not None:
            raise ValueError(
                "historical derivatives archive was injected but derivatives "
                "runtime is not enabled in execution_assumptions"
            )
        return {}

    if marker != DERIVATIVES_RUNTIME_VERSION:
        raise ValueError(
            "derivatives runtime assumptions are incoherent: "
            f"derivatives_runtime_version={marker!r}, "
            f"expected {DERIVATIVES_RUNTIME_VERSION!r}"
        )
    if assumptions.get("mtf_runtime_version") != MTF_RUNTIME_VERSION:
        raise ValueError(
            "historical derivatives runtime requires full MTF runtime"
        )
    if archive is None:
        raise ValueError(
            "enabled historical derivatives runtime requires the validated archive"
        )

    required = {
        "derivatives_context_binding_version": (
            HISTORICAL_DERIVATIVES_CONTEXT_BINDING_VERSION
        ),
        "derivatives_archive_version": archive.version,
        "derivatives_archive_fingerprint": archive.dataset_fingerprint,
        "derivatives_source": archive.source,
        "derivatives_instrument": archive.instrument,
    }
    for key, expected in required.items():
        actual = assumptions.get(key)
        if actual != expected:
            raise ValueError(
                "derivatives runtime assumptions are incoherent: "
                f"{key}={actual!r}, expected {expected!r}"
            )

    raw_max_age = assumptions.get("derivatives_max_age_seconds")
    try:
        max_age_seconds = int(str(raw_max_age))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "derivatives_max_age_seconds must be a positive integer"
        ) from exc
    if max_age_seconds <= 0 or str(max_age_seconds) != str(raw_max_age):
        raise ValueError(
            "derivatives_max_age_seconds must be a canonical positive integer"
        )

    return {
        "historical_derivatives_archive": archive,
        "derivatives_max_age": timedelta(seconds=max_age_seconds),
        "derivatives_context_binding_version": (
            HISTORICAL_DERIVATIVES_CONTEXT_BINDING_VERSION
        ),
    }


__all__ = [
    "DERIVATIVES_RUNTIME_VERSION",
    "historical_derivatives_execution_assumptions",
    "historical_derivatives_runner_kwargs",
]
