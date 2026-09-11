from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.backtest.derivatives_runtime import (
    DERIVATIVES_RUNTIME_VERSION,
    historical_derivatives_execution_assumptions,
    historical_derivatives_runner_kwargs,
)
from app.services.backtest.historical_derivatives_analytics import (
    HistoricalDerivativesAnalyticsArchive,
)
from app.services.backtest.mtf_runtime import (
    mtf_execution_assumptions,
    mtf_runner_kwargs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Batch 16.21l explicit historical Rio runtime activation."
    )
    parser.add_argument("canonical_csv", type=Path)
    args = parser.parse_args()

    archive = HistoricalDerivativesAnalyticsArchive.from_canonical_csv(
        args.canonical_csv
    )
    assumptions = mtf_execution_assumptions("1m")
    assumptions.update(
        historical_derivatives_execution_assumptions(
            archive,
            max_age_seconds=7200,
        )
    )

    kwargs = mtf_runner_kwargs(assumptions)
    kwargs.update(
        historical_derivatives_runner_kwargs(
            assumptions,
            archive,
        )
    )

    if kwargs["historical_derivatives_archive"] is not archive:
        raise SystemExit("validated archive identity was not preserved")
    if int(kwargs["derivatives_max_age"].total_seconds()) != 7200:
        raise SystemExit("derivatives max age mismatch")
    if assumptions["derivatives_archive_fingerprint"] != archive.dataset_fingerprint:
        raise SystemExit("archive fingerprint mismatch")

    if historical_derivatives_runner_kwargs({}, None) != {}:
        raise SystemExit("derivatives runtime should be disabled without marker")

    tampered = dict(assumptions)
    tampered["derivatives_archive_fingerprint"] = "0" * 64
    try:
        historical_derivatives_runner_kwargs(tampered, archive)
    except ValueError:
        pass
    else:
        raise SystemExit("tampered fingerprint did not fail closed")

    print("Money Heist Batch 16.21l Historical Rio Runtime Activation")
    print(f"runtime_version: {DERIVATIVES_RUNTIME_VERSION}")
    print(f"archive_version: {archive.version}")
    print(f"archive_fingerprint: {archive.dataset_fingerprint}")
    print(f"instrument: {archive.instrument}")
    print(f"rows: {len(archive.points):,}")
    print("source_timeframe: 1m")
    print("decision_timeframe: 1h")
    print("derivatives_max_age_seconds: 7200")
    print("explicit archive supplied: ENABLED")
    print("archive omitted: DISABLED")
    print(
        "RESULT: OK - historical Rio runtime activation is explicit, "
        "fingerprint-bound and fail-closed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
