#!/usr/bin/env python3
"""Download and prepare Binance Spot kline history for Money Heist.

Designed for long historical collections without API keys:
- downloads official Binance Public Data daily/monthly ZIP archives;
- verifies SHA-256 CHECKSUM files when available;
- resumes from an on-disk archive cache;
- normalizes Binance timestamps to milliseconds (archives use microseconds from 2025-01-01);
- writes rich normalized CSV files plus exact Money Heist backtest-ready CSV files;
- validates ordering, duplicates and gaps;
- optionally derives 15m/1h/4h/1d deterministically from canonical 1m data;
- optionally compares derived 15m against native Binance 15m.

Default example (12 months ending yesterday UTC):
    python download_binance_history.py --months 12

Six months:
    python download_binance_history.py --months 6

Custom period:
    python download_binance_history.py --start 2025-09-01 --end 2026-08-31

The script uses only Python's standard library.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from calendar import monthrange
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

BASE_URL = "https://data.binance.vision/data/spot"
USER_AGENT = "Money-Heist-Historical-Data/1.0"
RESAMPLER_VERSION = "mh_resampler_v1_closed_only_utc"

BINANCE_FIELDS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
)

OUTPUT_FIELDS = (
    "exchange_id",
    "market_type",
    "symbol",
    "timeframe",
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "is_closed",
    "updated_at",
    "source_id",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "provenance",
    "source_symbol",
    "provenance_note",
)

BACKTEST_FIELDS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)

INTERVAL_MS = {
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "2h": 2 * 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "6h": 6 * 60 * 60_000,
    "8h": 8 * 60 * 60_000,
    "12h": 12 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}

DERIVED_DEFAULTS = ("15m", "1h", "4h", "1d")


@dataclass(frozen=True)
class ArchiveSpec:
    interval: str
    kind: str  # monthly | daily
    year: int
    month: int
    day: int | None = None

    @property
    def filename(self) -> str:
        if self.kind == "monthly":
            return f"{{symbol}}-{self.interval}-{self.year:04d}-{self.month:02d}.zip"
        assert self.day is not None
        return f"{{symbol}}-{self.interval}-{self.year:04d}-{self.month:02d}-{self.day:02d}.zip"

    def remote_url(self, symbol: str) -> str:
        filename = self.filename.format(symbol=symbol)
        return f"{BASE_URL}/{self.kind}/klines/{symbol}/{self.interval}/{filename}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download official Binance Spot kline archives and prepare deterministic "
            "Money Heist datasets."
        )
    )
    parser.add_argument("--symbol", default="BTCUSDC", help="Binance symbol, default: BTCUSDC")
    parser.add_argument(
        "--display-symbol",
        default="BTC/USDC",
        help="Symbol written in normalized CSV, default: BTC/USDC",
    )
    period = parser.add_mutually_exclusive_group()
    period.add_argument(
        "--months", type=int, default=12, help="Trailing calendar months, default: 12"
    )
    period.add_argument("--start", help="Start UTC date YYYY-MM-DD (requires --end)")
    parser.add_argument("--end", help="End UTC date YYYY-MM-DD, inclusive. Default: yesterday UTC")
    parser.add_argument(
        "--intervals",
        nargs="+",
        default=["1m", "15m"],
        help="Native Binance intervals to download. Default: 1m 15m",
    )
    parser.add_argument(
        "--derive",
        nargs="*",
        default=list(DERIVED_DEFAULTS),
        help=(
            "Intervals to derive from native 1m. Default: 15m 1h 4h 1d. "
            "Use --derive with no values to disable."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="data/historical/binance_spot",
        help="Output root. Default: data/historical/binance_spot",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Only cache archives; do not consolidate/derive CSV files.",
    )
    parser.add_argument(
        "--no-checksum",
        action="store_true",
        help="Skip CHECKSUM verification (not recommended).",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Redownload archives even if already cached.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout seconds, default: 60",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=5,
        help="HTTP retries, default: 5",
    )
    return parser.parse_args()


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid date {value!r}; expected YYYY-MM-DD") from exc


def add_months(d: date, months: int) -> date:
    idx = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(idx, 12)
    month = month0 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def resolve_period(args: argparse.Namespace) -> tuple[date, date]:
    yesterday_utc = datetime.now(UTC).date() - timedelta(days=1)
    end = iso_date(args.end) if args.end else yesterday_utc
    if end >= datetime.now(UTC).date():
        raise SystemExit(
            "--end must be yesterday UTC or earlier so every requested candle is closed."
        )

    if args.start:
        if not args.end:
            raise SystemExit("--start requires an explicit --end.")
        start = iso_date(args.start)
    else:
        if args.months <= 0:
            raise SystemExit("--months must be > 0")
        # [start, end] is exactly N calendar months ending at end.
        start = add_months(end + timedelta(days=1), -args.months)

    if start > end:
        raise SystemExit("start date is after end date")
    return start, end


def daterange(start: date, end: date) -> Iterator[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def month_end(d: date) -> date:
    return date(d.year, d.month, monthrange(d.year, d.month)[1])


def plan_archives(interval: str, start: date, end: date) -> list[ArchiveSpec]:
    """Use monthly archives for whole months, daily archives for boundary fragments."""
    specs: list[ArchiveSpec] = []
    cursor = start
    while cursor <= end:
        ms = month_start(cursor)
        me = month_end(cursor)
        segment_start = max(start, ms)
        segment_end = min(end, me)
        if segment_start == ms and segment_end == me:
            specs.append(ArchiveSpec(interval, "monthly", cursor.year, cursor.month))
        else:
            for d in daterange(segment_start, segment_end):
                specs.append(ArchiveSpec(interval, "daily", d.year, d.month, d.day))
        cursor = me + timedelta(days=1)
    return specs


def http_get_bytes(url: str, timeout: int, retries: int, allow_404: bool = False) -> bytes | None:
    delay = 1.0
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and allow_404:
                return None
            if exc.code in (429, 418):
                retry_after = exc.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay
                print(f"  HTTP {exc.code}; backing off {wait:.1f}s", flush=True)
                time.sleep(wait)
                delay = min(delay * 2, 60)
                last_error = exc
                continue
            if 500 <= exc.code < 600:
                last_error = exc
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(delay)
            delay = min(delay * 2, 30)
    raise RuntimeError(f"Failed after {retries} attempts: {url}: {last_error}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_checksum(payload: bytes) -> str:
    text = payload.decode("utf-8", errors="replace").strip()
    if not text:
        raise ValueError("empty CHECKSUM file")
    digest = text.split()[0].lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"unexpected CHECKSUM content: {text!r}")
    return digest


def download_archive(
    spec: ArchiveSpec,
    symbol: str,
    cache_dir: Path,
    timeout: int,
    retries: int,
    verify_checksum: bool,
    force: bool,
) -> tuple[Path | None, dict]:
    url = spec.remote_url(symbol)
    filename = spec.filename.format(symbol=symbol)
    target_dir = cache_dir / spec.interval / spec.kind
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    checksum_url = url + ".CHECKSUM"

    expected_sha: str | None = None
    if verify_checksum:
        checksum_payload = http_get_bytes(checksum_url, timeout, retries, allow_404=True)
        if checksum_payload is not None:
            expected_sha = parse_checksum(checksum_payload)
        else:
            print(f"  warning: CHECKSUM missing: {checksum_url}")

    if target.exists() and not force:
        actual_sha = sha256_file(target) if expected_sha else None
        if expected_sha is None or actual_sha == expected_sha:
            return target, {
                "url": url,
                "path": str(target),
                "cached": True,
                "sha256": actual_sha or sha256_file(target),
                "checksum_verified": expected_sha is not None,
            }
        print(f"  cached checksum mismatch, redownloading: {filename}")
        target.unlink()

    print(f"  download {filename}", flush=True)
    payload = http_get_bytes(url, timeout, retries, allow_404=True)
    if payload is None:
        return None, {"url": url, "missing": True}

    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(payload)
    actual_sha = sha256_file(tmp)
    if expected_sha and actual_sha != expected_sha:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Checksum mismatch for {filename}: expected {expected_sha}, got {actual_sha}"
        )
    tmp.replace(target)
    return target, {
        "url": url,
        "path": str(target),
        "cached": False,
        "sha256": actual_sha,
        "checksum_verified": expected_sha is not None,
    }


def download_with_monthly_fallback(
    specs: Sequence[ArchiveSpec],
    symbol: str,
    cache_dir: Path,
    timeout: int,
    retries: int,
    verify_checksum: bool,
    force: bool,
) -> tuple[list[Path], list[dict]]:
    (
        "If a planned monthly archive is not published yet, transparently fall back "
        "to daily archives."
    )
    paths: list[Path] = []
    records: list[dict] = []
    for spec in specs:
        path, rec = download_archive(
            spec, symbol, cache_dir, timeout, retries, verify_checksum, force
        )
        records.append(rec)
        if path is not None:
            paths.append(path)
            continue

        if spec.kind != "monthly":
            raise RuntimeError(f"Required daily archive is missing: {spec.remote_url(symbol)}")

        print(
            f"  monthly archive unavailable for {spec.year:04d}-{spec.month:02d}; "
            "falling back to daily files",
            flush=True,
        )
        start = date(spec.year, spec.month, 1)
        end = month_end(start)
        for d in daterange(start, end):
            daily = ArchiveSpec(spec.interval, "daily", d.year, d.month, d.day)
            dpath, drec = download_archive(
                daily, symbol, cache_dir, timeout, retries, verify_checksum, force
            )
            records.append(drec)
            if dpath is None:
                raise RuntimeError(f"Required daily archive is missing: {daily.remote_url(symbol)}")
            paths.append(dpath)
    return paths, records


def normalize_epoch_ms(value: str) -> int:
    """Normalize seconds/ms/us/ns-ish integer epochs to milliseconds.

    Binance public SPOT archives from 2025-01-01 use microseconds.
    """
    raw = int(value)
    absolute = abs(raw)
    if absolute >= 10**17:  # ns
        return raw // 1_000_000
    if absolute >= 10**14:  # us
        return raw // 1_000
    if absolute >= 10**11:  # ms
        return raw
    return raw * 1_000  # seconds


def iter_zip_klines(path: Path) -> Iterator[dict[str, str]]:
    with zipfile.ZipFile(path, "r") as zf:
        members = [m for m in zf.namelist() if not m.endswith("/")]
        if len(members) != 1:
            raise RuntimeError(f"Expected exactly one CSV in {path}, found {members}")
        with zf.open(members[0], "r") as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            reader = csv.reader(text)
            for row in reader:
                if not row:
                    continue
                # Tolerate a header if Binance ever introduces one.
                if row[0].strip().lower() in ("open_time", "open time"):
                    continue
                if len(row) < 12:
                    raise RuntimeError(
                        f"Malformed row in {path}: expected >=12 columns, got {len(row)}"
                    )
                yield dict(zip(BINANCE_FIELDS, row[:12], strict=False))


def archive_sort_key(path: Path) -> tuple[int, ...]:
    # Sorting lexicographically is already chronological for YYYY-MM[-DD].
    # Include the kind path for deterministic ordering.
    return tuple(ord(ch) for ch in path.name)


def write_native_csv(
    archive_paths: Sequence[Path],
    output_path: Path,
    interval: str,
    symbol: str,
    display_symbol: str,
    start: date,
    end: date,
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    start_ms = int(datetime.combine(start, datetime.min.time(), tzinfo=UTC).timestamp() * 1000)
    end_exclusive_ms = int(
        datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC).timestamp()
        * 1000
    )
    interval_ms = INTERVAL_MS[interval]

    rows = 0
    duplicates = 0
    gaps: list[dict] = []
    first_open: int | None = None
    last_open: int | None = None
    last_full_row: dict[str, str] | None = None

    tmp = output_path.with_suffix(output_path.suffix + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()

        for archive in sorted(archive_paths, key=archive_sort_key):
            for src in iter_zip_klines(archive):
                ot = normalize_epoch_ms(src["open_time"])
                if ot < start_ms or ot >= end_exclusive_ms:
                    continue
                ct = normalize_epoch_ms(src["close_time"])

                if last_open is not None:
                    if ot == last_open:
                        current_core = {k: src[k] for k in BINANCE_FIELDS}
                        assert last_full_row is not None
                        previous_core = last_full_row
                        if current_core != previous_core:
                            raise RuntimeError(f"Conflicting duplicate candle at {ot} in {archive}")
                        duplicates += 1
                        continue
                    if ot < last_open:
                        raise RuntimeError(
                            f"Non-monotonic archive sequence: {ot} after {last_open}"
                        )
                    delta = ot - last_open
                    if delta != interval_ms:
                        gaps.append(
                            {
                                "after_open_time": last_open,
                                "next_open_time": ot,
                                "delta_ms": delta,
                                "missing_intervals": max(0, delta // interval_ms - 1),
                            }
                        )

                out = {
                    "exchange_id": "binance",
                    "market_type": "spot",
                    "symbol": display_symbol,
                    "timeframe": interval,
                    "open_time": ot,
                    "open": src["open"],
                    "high": src["high"],
                    "low": src["low"],
                    "close": src["close"],
                    "volume": src["volume"],
                    "close_time": ct,
                    "is_closed": 1,
                    "updated_at": "",
                    "source_id": "",
                    "quote_volume": src["quote_volume"],
                    "trade_count": src["trade_count"],
                    "taker_buy_base_volume": src["taker_buy_base_volume"],
                    "taker_buy_quote_volume": src["taker_buy_quote_volume"],
                    "provenance": "native",
                    "source_symbol": symbol,
                    "provenance_note": "binance_public_data",
                }
                writer.writerow(out)
                rows += 1
                first_open = ot if first_open is None else first_open
                last_open = ot
                last_full_row = {k: src[k] for k in BINANCE_FIELDS}

    tmp.replace(output_path)
    expected = (end_exclusive_ms - start_ms) // interval_ms
    summary = {
        "path": str(output_path),
        "interval": interval,
        "rows": rows,
        "expected_rows_if_continuous": expected,
        "duplicates_skipped": duplicates,
        "gap_count": len(gaps),
        "missing_intervals": sum(g["missing_intervals"] for g in gaps),
        "gap_examples": gaps[:20],
        "first_open_time": first_open,
        "last_open_time": last_open,
        "sha256": sha256_file(output_path),
    }
    return summary


def d(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise RuntimeError(f"Invalid decimal value: {value!r}") from exc


def decimal_text(value: Decimal) -> str:
    # Fixed-point, preserving exact sum without scientific notation.
    return format(value, "f")


def derive_from_1m(
    source_path: Path,
    output_path: Path,
    target_interval: str,
    display_symbol: str,
    symbol: str,
) -> dict:
    target_ms = INTERVAL_MS[target_interval]
    minute_ms = INTERVAL_MS["1m"]
    expected_count = target_ms // minute_ms
    if target_ms % minute_ms != 0:
        raise RuntimeError(f"Cannot derive {target_interval} from 1m using fixed UTC buckets")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".part")

    rows_written = 0
    incomplete_buckets = 0
    first_open: int | None = None
    last_open: int | None = None

    bucket_start: int | None = None
    bucket: list[dict[str, str]] = []

    def emit(writer: csv.DictWriter, bstart: int, items: list[dict[str, str]]) -> bool:
        nonlocal rows_written, incomplete_buckets, first_open, last_open
        if len(items) != expected_count:
            incomplete_buckets += 1
            return False
        expected_times = [bstart + i * minute_ms for i in range(expected_count)]
        actual_times = [int(x["open_time"]) for x in items]
        if actual_times != expected_times:
            incomplete_buckets += 1
            return False

        op = items[0]["open"]
        hi = max(d(x["high"]) for x in items)
        lo = min(d(x["low"]) for x in items)
        cl = items[-1]["close"]
        vol = sum((d(x["volume"]) for x in items), Decimal(0))
        qvol = sum((d(x["quote_volume"]) for x in items), Decimal(0))
        trades = sum(int(Decimal(x["trade_count"])) for x in items)
        taker_base = sum((d(x["taker_buy_base_volume"]) for x in items), Decimal(0))
        taker_quote = sum((d(x["taker_buy_quote_volume"]) for x in items), Decimal(0))

        writer.writerow(
            {
                "exchange_id": "binance",
                "market_type": "spot",
                "symbol": display_symbol,
                "timeframe": target_interval,
                "open_time": bstart,
                "open": op,
                "high": decimal_text(hi),
                "low": decimal_text(lo),
                "close": cl,
                "volume": decimal_text(vol),
                "close_time": bstart + target_ms - 1,
                "is_closed": 1,
                "updated_at": "",
                "source_id": "",
                "quote_volume": decimal_text(qvol),
                "trade_count": trades,
                "taker_buy_base_volume": decimal_text(taker_base),
                "taker_buy_quote_volume": decimal_text(taker_quote),
                "provenance": "resampled",
                "source_symbol": symbol,
                "provenance_note": RESAMPLER_VERSION,
            }
        )
        rows_written += 1
        first_open = bstart if first_open is None else first_open
        last_open = bstart
        return True

    with (
        source_path.open("r", encoding="utf-8", newline="") as src_f,
        tmp.open("w", encoding="utf-8", newline="") as out_f,
    ):
        reader = csv.DictReader(src_f)
        writer = csv.DictWriter(out_f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()

        for row in reader:
            ot = int(row["open_time"])
            bstart = (ot // target_ms) * target_ms
            if bucket_start is None:
                bucket_start = bstart
            if bstart != bucket_start:
                emit(writer, bucket_start, bucket)
                bucket_start = bstart
                bucket = []
            bucket.append(row)
        if bucket_start is not None and bucket:
            emit(writer, bucket_start, bucket)

    tmp.replace(output_path)
    return {
        "path": str(output_path),
        "interval": target_interval,
        "source": str(source_path),
        "rows": rows_written,
        "incomplete_buckets_dropped": incomplete_buckets,
        "first_open_time": first_open,
        "last_open_time": last_open,
        "resampler_version": RESAMPLER_VERSION,
        "sha256": sha256_file(output_path),
    }


def export_backtest_ready(source_path: Path, output_path: Path) -> dict:
    """Export a rich normalized/resampled CSV to Money Heist's current replay contract.

    Output columns are exactly:
        timestamp,open,high,low,close,volume

    ``timestamp`` is the candle OPEN time in Unix milliseconds. The current
    ``import_candles_csv`` loader reconstructs ``close_time`` from the timeframe's
    configured candle interval, so no close_time column is emitted here.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".part")

    rows = 0
    first_ts: int | None = None
    last_ts: int | None = None
    previous_ts: int | None = None
    duplicate_count = 0
    non_monotonic_count = 0

    with (
        source_path.open("r", encoding="utf-8", newline="") as src_f,
        tmp.open("w", encoding="utf-8", newline="") as out_f,
    ):
        reader = csv.DictReader(src_f)
        required = {"open_time", "open", "high", "low", "close", "volume"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise RuntimeError(f"Cannot export {source_path}: missing columns {sorted(missing)}")

        writer = csv.DictWriter(out_f, fieldnames=BACKTEST_FIELDS)
        writer.writeheader()
        for row in reader:
            ts = int(row["open_time"])
            if previous_ts is not None:
                if ts == previous_ts:
                    duplicate_count += 1
                elif ts < previous_ts:
                    non_monotonic_count += 1
            writer.writerow(
                {
                    "timestamp": ts,
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                }
            )
            rows += 1
            first_ts = ts if first_ts is None else first_ts
            last_ts = ts
            previous_ts = ts

    tmp.replace(output_path)
    return {
        "path": str(output_path),
        "source": str(source_path),
        "rows": rows,
        "columns": list(BACKTEST_FIELDS),
        "timestamp_unit": "unix_milliseconds",
        "timestamp_semantics": "candle_open_time_utc",
        "duplicates_seen": duplicate_count,
        "non_monotonic_seen": non_monotonic_count,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "sha256": sha256_file(output_path),
        "money_heist_contract": "timestamp,open,high,low,close,volume",
    }


def compare_derived_native(derived_path: Path, native_path: Path) -> dict:
    def load(path: Path) -> dict[int, dict[str, str]]:
        with path.open("r", encoding="utf-8", newline="") as f:
            return {int(r["open_time"]): r for r in csv.DictReader(f)}

    derived = load(derived_path)
    native = load(native_path)
    overlap = sorted(set(derived).intersection(native))
    mismatch_examples: list[dict] = []
    mismatch_count = 0
    compare_fields = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    )

    for ts in overlap:
        a = derived[ts]
        b = native[ts]
        diffs: dict[str, dict[str, str]] = {}
        for field in compare_fields:
            equal = (
                int(Decimal(a[field])) == int(Decimal(b[field]))
                if field == "trade_count"
                else d(a[field]) == d(b[field])
            )
            if not equal:
                diffs[field] = {"derived": a[field], "native": b[field]}
        if diffs:
            mismatch_count += 1
            if len(mismatch_examples) < 20:
                mismatch_examples.append({"open_time": ts, "diffs": diffs})

    return {
        "derived": str(derived_path),
        "native": str(native_path),
        "overlap_rows": len(overlap),
        "derived_only_rows": len(set(derived) - set(native)),
        "native_only_rows": len(set(native) - set(derived)),
        "mismatch_rows": mismatch_count,
        "exact_match_rows": len(overlap) - mismatch_count,
        "mismatch_examples": mismatch_examples,
    }


def ms_iso(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()


def main() -> int:
    args = parse_args()
    symbol = args.symbol.upper().replace("/", "")
    start, end = resolve_period(args)

    for interval in args.intervals:
        if interval not in INTERVAL_MS:
            raise SystemExit(
                f"Unsupported interval {interval!r}; supported: {', '.join(INTERVAL_MS)}"
            )
    for interval in args.derive:
        if interval not in INTERVAL_MS:
            raise SystemExit(f"Unsupported derived interval {interval!r}")
    if args.derive and "1m" not in args.intervals:
        raise SystemExit("Derivation requires native 1m in --intervals")

    root = Path(args.output_dir).expanduser().resolve()
    cache_dir = root / "raw_archives"
    normalized_dir = root / "normalized"
    derived_dir = root / "derived_from_1m"
    backtest_dir = root / "backtest_ready"
    manifests_dir = root / "manifests"
    for p in (cache_dir, normalized_dir, derived_dir, backtest_dir, manifests_dir):
        p.mkdir(parents=True, exist_ok=True)

    stamp = f"{start.isoformat()}_{end.isoformat()}"
    manifest: dict = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "exchange_id": "binance",
        "market_type": "spot",
        "source_symbol": symbol,
        "display_symbol": args.display_symbol,
        "start_date_utc": start.isoformat(),
        "end_date_utc": end.isoformat(),
        "native_intervals": args.intervals,
        "derived_intervals": args.derive,
        "resampler_version": RESAMPLER_VERSION,
        "timestamp_normalization": "source seconds/ms/us/ns -> integer milliseconds",
        "archives": {},
        "native": {},
        "derived": {},
        "backtest_ready": {},
        "comparisons": {},
    }

    print("Money Heist historical data preparation")
    print(f"  symbol: {symbol} ({args.display_symbol})")
    print(f"  period: {start} -> {end} UTC (inclusive)")
    print(f"  native intervals: {', '.join(args.intervals)}")
    print(f"  output: {root}")

    archive_paths_by_interval: dict[str, list[Path]] = {}
    for interval in args.intervals:
        print(f"\n[{interval}] planning/downloading official Binance archives")
        specs = plan_archives(interval, start, end)
        paths, records = download_with_monthly_fallback(
            specs=specs,
            symbol=symbol,
            cache_dir=cache_dir,
            timeout=args.timeout,
            retries=args.retries,
            verify_checksum=not args.no_checksum,
            force=args.force_download,
        )
        archive_paths_by_interval[interval] = paths
        manifest["archives"][interval] = records
        print(f"  archives ready: {len(paths)}")

    if args.download_only:
        manifest_path = manifests_dir / f"{symbol}_{stamp}_download_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"\nDownload-only complete. Manifest: {manifest_path}")
        return 0

    native_paths: dict[str, Path] = {}
    for interval in args.intervals:
        print(f"\n[{interval}] consolidating + validating")
        out = normalized_dir / f"{symbol}_{interval}_{stamp}.csv"
        summary = write_native_csv(
            archive_paths=archive_paths_by_interval[interval],
            output_path=out,
            interval=interval,
            symbol=symbol,
            display_symbol=args.display_symbol,
            start=start,
            end=end,
        )
        summary["first_open_iso_utc"] = ms_iso(summary["first_open_time"])
        summary["last_open_iso_utc"] = ms_iso(summary["last_open_time"])
        manifest["native"][interval] = summary
        native_paths[interval] = out
        print(
            f"  rows={summary['rows']:,} gaps={summary['gap_count']} "
            f"missing={summary['missing_intervals']} sha256={summary['sha256'][:16]}..."
        )

    derived_paths: dict[str, Path] = {}
    if args.derive:
        source_1m = native_paths["1m"]
        for interval in args.derive:
            if interval == "1m":
                continue
            print(f"\n[derive {interval}] from canonical 1m, closed UTC buckets only")
            out = derived_dir / f"{symbol}_{interval}_{stamp}_from_1m.csv"
            summary = derive_from_1m(
                source_path=source_1m,
                output_path=out,
                target_interval=interval,
                display_symbol=args.display_symbol,
                symbol=symbol,
            )
            summary["first_open_iso_utc"] = ms_iso(summary["first_open_time"])
            summary["last_open_iso_utc"] = ms_iso(summary["last_open_time"])
            manifest["derived"][interval] = summary
            derived_paths[interval] = out
            print(
                f"  rows={summary['rows']:,} incomplete_buckets_dropped="
                f"{summary['incomplete_buckets_dropped']} sha256={summary['sha256'][:16]}..."
            )

    if "15m" in derived_paths and "15m" in native_paths:
        print("\n[compare] derived 15m from 1m vs native Binance 15m")
        cmp_summary = compare_derived_native(derived_paths["15m"], native_paths["15m"])
        manifest["comparisons"]["15m_from_1m_vs_native"] = cmp_summary
        print(
            f"  overlap={cmp_summary['overlap_rows']:,} "
            f"exact={cmp_summary['exact_match_rows']:,} "
            f"mismatch={cmp_summary['mismatch_rows']:,}"
        )
        if cmp_summary["mismatch_rows"]:
            print(
                "  WARNING: 15m resampling mismatches detected; "
                "inspect manifest before using derived data."
            )

    print("\n[backtest-ready] exporting current Money Heist CSV contract")
    slug_symbol = args.display_symbol.lower().replace("/", "_").replace("-", "_")

    # 1m is native. Higher timeframes prefer deterministic resampling from the
    # canonical 1m stream when available. Native 15m is also exported separately
    # as a control file when both variants exist.
    selected_sources: dict[str, Path] = {}
    if "1m" in native_paths:
        selected_sources["1m"] = native_paths["1m"]

    for interval in ("15m", "1h", "4h", "1d"):
        if interval in derived_paths:
            selected_sources[interval] = derived_paths[interval]
        elif interval in native_paths:
            selected_sources[interval] = native_paths[interval]

    for interval, source_path in selected_sources.items():
        out = backtest_dir / f"binance_{slug_symbol}_{interval}_{stamp}.csv"
        summary = export_backtest_ready(source_path, out)
        summary["interval"] = interval
        summary["first_timestamp_iso_utc"] = ms_iso(summary["first_timestamp"])
        summary["last_timestamp_iso_utc"] = ms_iso(summary["last_timestamp"])
        summary["canonical_for_backtest"] = True
        manifest["backtest_ready"][interval] = summary
        print(f"  {interval}: rows={summary['rows']:,} -> {summary['path']}")

    if "15m" in native_paths and "15m" in derived_paths:
        native_control = backtest_dir / f"binance_{slug_symbol}_15m_native_control_{stamp}.csv"
        control_summary = export_backtest_ready(native_paths["15m"], native_control)
        control_summary["interval"] = "15m"
        control_summary["canonical_for_backtest"] = False
        control_summary["purpose"] = "native Binance 15m control for resampler comparison"
        control_summary["first_timestamp_iso_utc"] = ms_iso(control_summary["first_timestamp"])
        control_summary["last_timestamp_iso_utc"] = ms_iso(control_summary["last_timestamp"])
        manifest["backtest_ready"]["15m_native_control"] = control_summary
        print(f"  15m native control -> {control_summary['path']}")

    manifest_path = manifests_dir / f"{symbol}_{stamp}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("\n=== COMPLETE ===")
    print(f"Manifest: {manifest_path}")
    for interval, summary in manifest["native"].items():
        status = "OK" if summary["gap_count"] == 0 else "WARNING_GAPS"
        print(f"native {interval}: {status} -> {summary['path']}")
    for interval, summary in manifest["derived"].items():
        print(f"derived {interval}: -> {summary['path']}")
    for interval, summary in manifest["backtest_ready"].items():
        print(f"backtest {interval}: -> {summary['path']}")

    warnings = []
    for interval, summary in manifest["native"].items():
        if summary["gap_count"]:
            warnings.append(f"native {interval}: {summary['gap_count']} gaps")
    comparison = manifest["comparisons"].get("15m_from_1m_vs_native")
    if comparison and comparison["mismatch_rows"]:
        warnings.append(f"15m derived/native: {comparison['mismatch_rows']} mismatch rows")

    if warnings:
        print("\nDATA QUALITY WARNINGS:")
        for warning in warnings:
            print(f"  - {warning}")
        print(
            "Keep the files, but do not promote them as canonical until the warnings are reviewed."
        )
    else:
        print("\nData-quality checks passed for the requested period.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(
            "\nInterrupted. Cached archives are preserved; rerun the same command to resume.",
            file=sys.stderr,
        )
        raise SystemExit(130) from None
