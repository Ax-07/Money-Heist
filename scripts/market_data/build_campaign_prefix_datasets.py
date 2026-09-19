#!/usr/bin/env python3
"""Build smaller Money Heist campaign datasets as exact prefixes of a canonical 1m CSV.

The important invariant is that every generated file keeps the exact same origin as
its source dataset.  We only remove the *future tail*.  This preserves recursive
indicator state (EMA/MACD/ADX), MTF cursor history, and causal replay behaviour for
all timestamps retained in the generated prefix.

No separate warm-up is invented by this tool.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

SCHEMA_VERSION = "money-heist.campaign-prefix-datasets.v1"
CANONICAL_HEADER = ("timestamp", "open", "high", "low", "close", "volume")
DEFAULT_SOURCE = Path(
    "data/historical/binance_spot/backtest_ready/"
    "binance_btc_usdc_1m_2025-09-11_2026-09-10.csv"
)
DEFAULT_OUTPUT_DIR = Path("data/historical/binance_spot/campaign_datasets")
DEFAULT_DURATIONS = (1, 3, 6, 9, 12)
INTERVAL_MS = 60_000


class DatasetBuildError(RuntimeError):
    """Controlled validation/build failure."""


@dataclass(frozen=True)
class SourceRow:
    timestamp_ms: int
    raw_line: bytes


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + (value.month - 1) + months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def date_from_timestamp_ms(timestamp_ms: int) -> date:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).date()


def timestamp_ms_at_midnight(value: date) -> int:
    return int(datetime(value.year, value.month, value.day, tzinfo=UTC).timestamp() * 1000)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build exact calendar-month prefixes from the canonical Money Heist 1m dataset."
        )
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--months",
        type=int,
        nargs="+",
        default=list(DEFAULT_DURATIONS),
        help="Calendar-month prefix durations. Default: 1 3 6 9 12",
    )
    parser.add_argument(
        "--copy-full",
        action="store_true",
        help=(
            "Also copy the full-duration source into campaign_datasets. By default the "
            "manifest references the canonical source instead of duplicating it."
        ),
    )
    return parser.parse_args()


def read_source(path: Path) -> tuple[bytes, list[SourceRow]]:
    if not path.is_file():
        raise DatasetBuildError(f"source dataset not found: {path}")

    with path.open("rb") as handle:
        header = handle.readline()
        if not header:
            raise DatasetBuildError("source CSV is empty")

        try:
            decoded_header = next(csv.reader([header.decode("utf-8-sig").strip()]))
        except UnicodeDecodeError as exc:
            raise DatasetBuildError("source CSV header is not UTF-8") from exc

        normalized_header = tuple(item.strip().lower() for item in decoded_header)
        if normalized_header != CANONICAL_HEADER:
            raise DatasetBuildError(
                f"unexpected CSV header {normalized_header!r}; expected {CANONICAL_HEADER!r}"
            )

        rows: list[SourceRow] = []
        previous_timestamp: int | None = None
        for line_number, raw_line in enumerate(handle, start=2):
            if not raw_line.strip():
                continue
            timestamp_token = raw_line.split(b",", 1)[0]
            try:
                timestamp_ms = int(timestamp_token)
            except ValueError as exc:
                raise DatasetBuildError(
                    f"invalid timestamp at line {line_number}: {timestamp_token!r}"
                ) from exc

            if previous_timestamp is not None:
                delta = timestamp_ms - previous_timestamp
                if delta != INTERVAL_MS:
                    raise DatasetBuildError(
                        "source is not a continuous 1m series: "
                        f"line {line_number}, delta={delta} ms"
                    )
            previous_timestamp = timestamp_ms
            rows.append(SourceRow(timestamp_ms=timestamp_ms, raw_line=raw_line))

    if not rows:
        raise DatasetBuildError("source CSV has no data rows")
    return header, rows


def main() -> int:
    args = parse_args()
    months = tuple(sorted(set(args.months)))
    if not months or any(value <= 0 for value in months):
        raise DatasetBuildError("--months values must be positive integers")

    source = args.source.resolve()
    output_dir = args.output_dir.resolve()
    header, rows = read_source(source)

    source_start = date_from_timestamp_ms(rows[0].timestamp_ms)
    source_last = date_from_timestamp_ms(rows[-1].timestamp_ms)
    source_end_exclusive_ms = rows[-1].timestamp_ms + INTERVAL_MS
    source_end_exclusive = datetime.fromtimestamp(
        source_end_exclusive_ms / 1000, tz=UTC
    ).date()

    output_dir.mkdir(parents=True, exist_ok=True)
    source_sha = sha256_file(source)

    entries: list[dict[str, object]] = []
    for duration_months in months:
        end_exclusive = add_months(source_start, duration_months)
        cutoff_ms = timestamp_ms_at_midnight(end_exclusive)
        expected_rows = (cutoff_ms - rows[0].timestamp_ms) // INTERVAL_MS

        if cutoff_ms > source_end_exclusive_ms:
            raise DatasetBuildError(
                f"{duration_months}m prefix exceeds source coverage: "
                f"needs data through {end_exclusive.isoformat()} exclusive, "
                f"source ends {source_end_exclusive.isoformat()} exclusive"
            )
        if expected_rows <= 0:
            raise DatasetBuildError(f"invalid row count for {duration_months}m prefix")

        row_count = int(expected_rows)
        selected = rows[:row_count]
        if len(selected) != row_count:
            raise DatasetBuildError(
                f"unexpected source row shortage for {duration_months}m prefix"
            )
        if selected[-1].timestamp_ms + INTERVAL_MS != cutoff_ms:
            raise DatasetBuildError(
                f"{duration_months}m cutoff is not exactly aligned to source candles"
            )

        end_inclusive = date_from_timestamp_ms(selected[-1].timestamp_ms)
        is_full_source = row_count == len(rows)
        filename = (
            f"binance_btc_usdc_1m_campaign_{duration_months}m_"
            f"{source_start.isoformat()}_{end_inclusive.isoformat()}.csv"
        )
        output_path = output_dir / filename

        if is_full_source and not args.copy_full:
            entry_path = str(source)
            output_sha = source_sha
            size_bytes = source.stat().st_size
            storage = "canonical_source_reference"
        else:
            with output_path.open("wb") as handle:
                handle.write(header)
                for row in selected:
                    handle.write(row.raw_line)
            output_sha = sha256_file(output_path)
            size_bytes = output_path.stat().st_size
            entry_path = str(output_path)
            storage = "generated_prefix"

            # Strong byte-level invariant: generated payload must be an exact source prefix.
            generated = output_path.read_bytes()
            with source.open("rb") as source_handle:
                source_prefix = source_handle.read(len(generated))
            if generated != source_prefix:
                raise DatasetBuildError(
                    f"generated {duration_months}m dataset is not an exact byte prefix"
                )

        entries.append(
            {
                "duration_months": duration_months,
                "dataset_start_utc": source_start.isoformat(),
                "dataset_end_utc_inclusive": end_inclusive.isoformat(),
                "dataset_end_utc_exclusive": end_exclusive.isoformat(),
                "rows": row_count,
                "size_bytes": size_bytes,
                "sha256": output_sha,
                "path": entry_path,
                "storage": storage,
                "exact_source_prefix": True,
            }
        )

    manifest = {
        "schema": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "policy": "calendar_prefix_from_canonical_source_start",
        "rationale": (
            "Only the future tail is removed. Dataset origin is unchanged so recursive "
            "indicator state and causal MTF history are preserved for retained timestamps."
        ),
        "source": {
            "path": str(source),
            "sha256": source_sha,
            "rows": len(rows),
            "start_utc": source_start.isoformat(),
            "last_candle_date_utc": source_last.isoformat(),
            "end_utc_exclusive": source_end_exclusive.isoformat(),
            "timeframe": "1m",
            "interval_ms": INTERVAL_MS,
        },
        "datasets": entries,
    }

    manifest_path = output_dir / "campaign_datasets_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"Source: {source}")
    print(f"Source SHA-256: {source_sha}")
    print(f"Manifest: {manifest_path}")
    print()
    for entry in entries:
        mb = int(entry["size_bytes"]) / 1024 / 1024
        print(
            f"{entry['duration_months']:>2}m  {entry['rows']:>6} rows  "
            f"{mb:>7.2f} MiB  {entry['dataset_start_utc']} -> "
            f"{entry['dataset_end_utc_inclusive']}  {entry['storage']}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DatasetBuildError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
