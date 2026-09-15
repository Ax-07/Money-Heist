#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

DEFAULT_CODE_VERSION = "5df9be1878bfbb76a40901d00535b1a1e9961e54"

TIMEFRAME_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

REQUIRED_SOURCE_COLUMNS = (
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
)

MONEY_HEIST_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


class SyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candle:
    open_time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    raw: dict[str, str]


def decimal_value(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, TypeError) as exc:
        raise SyncError(f"{field} invalide: {value!r}") from exc
    if not result.is_finite():
        raise SyncError(f"{field} doit être fini")
    return result


def as_decimal_text(value: Any) -> str:
    number = decimal_value(value, "decimal")
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def iso_utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_source_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise SyncError(f"Fichier introuvable: {path}")

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.lower().endswith("btc_1h.csv")
            ]
            if len(names) != 1:
                raise SyncError(
                    "Le ZIP doit contenir exactement un btc_1h.csv "
                    f"(trouvé: {len(names)})"
                )
            data = archive.read(names[0]).decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(data))
            fieldnames = list(reader.fieldnames or ())
            rows = [dict(row) for row in reader]
            return fieldnames, rows

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or ())
        rows = [dict(row) for row in reader]
        return fieldnames, rows


def parse_and_validate(
    fieldnames: list[str],
    rows: list[dict[str, str]],
    *,
    symbol: str,
    timeframe: str,
) -> list[Candle]:
    missing = [name for name in REQUIRED_SOURCE_COLUMNS if name not in fieldnames]
    if missing:
        raise SyncError(f"Colonnes source manquantes: {', '.join(missing)}")
    if not rows:
        raise SyncError("Le CSV H1 est vide")

    interval_ms = TIMEFRAME_MS[timeframe]
    candles: list[Candle] = []

    for line_no, row in enumerate(rows, start=2):
        if row.get("exchange_id", "").strip().lower() != "binance":
            raise SyncError(f"Ligne {line_no}: exchange_id != binance")
        if row.get("market_type", "").strip().lower() != "spot":
            raise SyncError(f"Ligne {line_no}: market_type != spot")
        if row.get("symbol", "").strip() != symbol:
            raise SyncError(f"Ligne {line_no}: symbol != {symbol}")
        if row.get("timeframe", "").strip() != timeframe:
            raise SyncError(f"Ligne {line_no}: timeframe != {timeframe}")
        if row.get("is_closed", "").strip() not in {"1", "true", "True"}:
            raise SyncError(f"Ligne {line_no}: bougie non close")

        try:
            open_time = int(row["open_time"])
        except (TypeError, ValueError) as exc:
            raise SyncError(f"Ligne {line_no}: open_time invalide") from exc

        candle = Candle(
            open_time=open_time,
            open=decimal_value(row["open"], "open"),
            high=decimal_value(row["high"], "high"),
            low=decimal_value(row["low"], "low"),
            close=decimal_value(row["close"], "close"),
            volume=decimal_value(row["volume"], "volume"),
            raw=row,
        )
        validate_ohlcv(candle, line_no)
        candles.append(candle)

    candles.sort(key=lambda item: item.open_time)
    timestamps = [item.open_time for item in candles]
    if len(timestamps) != len(set(timestamps)):
        raise SyncError("Doublons open_time détectés")

    gaps = []
    for previous, current in zip(candles, candles[1:], strict=False):
        delta = current.open_time - previous.open_time
        if delta != interval_ms:
            gaps.append((previous.open_time, current.open_time, delta))

    if gaps:
        first = gaps[0]
        raise SyncError(
            "Gap H1 détecté: "
            f"{iso_utc(first[0])} -> {iso_utc(first[1])} "
            f"(delta={first[2] // 1000}s)"
        )

    return candles


def validate_ohlcv(candle: Candle, line_no: int | str) -> None:
    if candle.open <= 0 or candle.high <= 0 or candle.low <= 0 or candle.close <= 0:
        raise SyncError(f"Ligne {line_no}: prix <= 0")
    if candle.volume < 0:
        raise SyncError(f"Ligne {line_no}: volume < 0")
    if candle.high < max(candle.open, candle.close):
        raise SyncError(f"Ligne {line_no}: high < open/close")
    if candle.low > min(candle.open, candle.close):
        raise SyncError(f"Ligne {line_no}: low > open/close")
    if candle.high < candle.low:
        raise SyncError(f"Ligne {line_no}: high < low")


def close_enough(first: Decimal, second: Decimal) -> bool:
    tolerance = max(Decimal("0.00000001"), abs(first) * Decimal("0.000000000001"))
    return abs(first - second) <= tolerance


def compare_overlap(existing: Candle, fetched: list[Any]) -> None:
    fetched_candle = Candle(
        open_time=int(fetched[0]),
        open=decimal_value(fetched[1], "ccxt open"),
        high=decimal_value(fetched[2], "ccxt high"),
        low=decimal_value(fetched[3], "ccxt low"),
        close=decimal_value(fetched[4], "ccxt close"),
        volume=decimal_value(fetched[5], "ccxt volume"),
        raw={},
    )
    validate_ohlcv(fetched_candle, "CCXT-overlap")

    checks = (
        ("open", existing.open, fetched_candle.open),
        ("high", existing.high, fetched_candle.high),
        ("low", existing.low, fetched_candle.low),
        ("close", existing.close, fetched_candle.close),
        ("volume", existing.volume, fetched_candle.volume),
    )
    mismatches = [
        f"{name}: source={left} ccxt={right}"
        for name, left, right in checks
        if not close_enough(left, right)
    ]
    if mismatches:
        raise SyncError(
            "La bougie de recouvrement diffère entre le CSV et Binance/CCXT. "
            "Aucun écrasement automatique.\n  " + "\n  ".join(mismatches)
        )


def precision_to_step(value: Any) -> str | None:
    if value is None:
        return None
    number = decimal_value(value, "amount precision")
    if number <= 0:
        return None
    if number < 1:
        return as_decimal_text(number)
    if number == number.to_integral_value():
        decimals = int(number)
        return "1" if decimals == 0 else "0." + ("0" * (decimals - 1)) + "1"
    return as_decimal_text(number)


def fetch_ccxt_updates(
    *,
    symbol: str,
    timeframe: str,
    last_existing: Candle,
) -> tuple[list[list[Any]], dict[str, Any]]:
    try:
        import ccxt  # type: ignore
    except ImportError as exc:
        raise SyncError(
            "CCXT n'est pas installé. Utilise: "
            'uv run --with "ccxt==4.5.78" python .\\sync_binance_btc_usdc_h1.py ...'
        ) from exc

    exchange = ccxt.binance({"enableRateLimit": True})
    try:
        exchange.load_markets()
        if symbol not in exchange.markets:
            raise SyncError(
                f"{symbol} n'existe pas dans les marchés Binance chargés par CCXT"
            )

        market = exchange.market(symbol)
        if not market.get("spot"):
            raise SyncError(f"{symbol} n'est pas identifié comme marché spot")
        if market.get("active") is False:
            raise SyncError(f"{symbol} est marqué inactif par CCXT/Binance")

        try:
            exchange_now_ms = int(exchange.fetch_time())
        except Exception:
            exchange_now_ms = int(exchange.milliseconds())

        interval_ms = TIMEFRAME_MS[timeframe]
        current_bucket_start = (exchange_now_ms // interval_ms) * interval_ms
        target_last_closed = current_bucket_start - interval_ms

        overlap_bars = 24
        since = max(0, last_existing.open_time - (overlap_bars - 1) * interval_ms)
        fetched_by_ts: dict[int, list[Any]] = {}

        while since <= target_last_closed:
            batch = exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, since=since, limit=1000
            )
            if not batch:
                break

            for item in batch:
                ts = int(item[0])
                if ts < current_bucket_start:
                    fetched_by_ts[ts] = item

            last_batch_ts = int(batch[-1][0])
            next_since = last_batch_ts + interval_ms
            if next_since <= since:
                raise SyncError("Pagination CCXT n'avance plus")
            since = next_since

            if last_batch_ts >= target_last_closed:
                break

        fetched = [fetched_by_ts[key] for key in sorted(fetched_by_ts)]
        limits = market.get("limits") or {}
        amount_limits = limits.get("amount") or {}
        cost_limits = limits.get("cost") or {}
        precision = market.get("precision") or {}

        metadata = {
            "ccxt_version": getattr(ccxt, "__version__", "unknown"),
            "exchange": exchange.id,
            "exchange_now_utc": iso_utc(exchange_now_ms),
            "market_active": market.get("active"),
            "qty_step": precision_to_step(precision.get("amount")),
            "min_qty": (
                as_decimal_text(amount_limits.get("min"))
                if amount_limits.get("min") is not None
                else None
            ),
            "max_qty": (
                as_decimal_text(amount_limits.get("max"))
                if amount_limits.get("max") is not None
                else None
            ),
            "min_notional": (
                as_decimal_text(cost_limits.get("min"))
                if cost_limits.get("min") is not None
                else None
            ),
            "maker_fee_reference": market.get("maker"),
            "taker_fee_reference": market.get("taker"),
            "target_last_closed_utc": iso_utc(target_last_closed),
        }
        return fetched, metadata
    finally:
        exchange.close()


def candle_from_ccxt(item: list[Any]) -> Candle:
    candle = Candle(
        open_time=int(item[0]),
        open=decimal_value(item[1], "ccxt open"),
        high=decimal_value(item[2], "ccxt high"),
        low=decimal_value(item[3], "ccxt low"),
        close=decimal_value(item[4], "ccxt close"),
        volume=decimal_value(item[5], "ccxt volume"),
        raw={},
    )
    validate_ohlcv(candle, "CCXT")
    return candle


def candle_mismatches(existing: Candle, fetched: Candle) -> list[str]:
    checks = (
        ("open", existing.open, fetched.open),
        ("high", existing.high, fetched.high),
        ("low", existing.low, fetched.low),
        ("close", existing.close, fetched.close),
        ("volume", existing.volume, fetched.volume),
    )
    return [
        f"{name}: source={left} ccxt={right}"
        for name, left, right in checks
        if not close_enough(left, right)
    ]


def repair_trailing_overlap(
    fieldnames: list[str],
    rows: list[dict[str, str]],
    candles: list[Candle],
    fetched: list[list[Any]],
    *,
    timeframe: str,
) -> tuple[list[dict[str, str]], int]:
    """Repair only a contiguous mismatching suffix in the 24-bar overlap.

    This is intentionally fail-closed:
    - every compared historical timestamp must exist in CCXT;
    - mismatches are accepted only if they form a suffix ending on the last
      existing source candle;
    - older isolated mismatches abort the sync.
    """
    interval_ms = TIMEFRAME_MS[timeframe]
    fetched_map = {int(item[0]): candle_from_ccxt(item) for item in fetched}
    overlap = candles[-min(24, len(candles)) :]

    missing = [item for item in overlap if item.open_time not in fetched_map]
    if missing:
        raise SyncError(
            "CCXT ne fournit pas tout le recouvrement de contrôle. "
            f"Premier timestamp absent: {iso_utc(missing[0].open_time)}"
        )

    mismatch_indices: list[int] = []
    mismatch_details: dict[int, list[str]] = {}
    for index, existing in enumerate(overlap):
        diffs = candle_mismatches(existing, fetched_map[existing.open_time])
        if diffs:
            mismatch_indices.append(index)
            mismatch_details[index] = diffs

    if not mismatch_indices:
        print("Recouvrement 24h: toutes les bougies concordent.")
        return rows, 0

    first = mismatch_indices[0]
    expected_suffix = list(range(first, len(overlap)))
    if mismatch_indices != expected_suffix:
        bad = overlap[first]
        details = "\n  ".join(mismatch_details[first])
        raise SyncError(
            "Divergence historique non terminale détectée; correction automatique refusée.\n"
            f"Timestamp: {iso_utc(bad.open_time)}\n  {details}"
        )

    repaired_count = len(mismatch_indices)
    first_bad = overlap[first]
    print(
        "Recouvrement 24h: divergence terminale compatible avec une ou plusieurs "
        "bougies capturées avant clôture."
    )
    print(f"Première bougie à réparer : {iso_utc(first_bad.open_time)}")
    print(f"Bougies terminales réparées: {repaired_count}")

    rows_by_ts = {int(row["open_time"]): dict(row) for row in rows}
    repaired_at = int(datetime.now(UTC).timestamp() * 1000)

    for existing in overlap[first:]:
        fetched_candle = fetched_map[existing.open_time]
        row = rows_by_ts[existing.open_time]
        row["open"] = as_decimal_text(fetched_candle.open)
        row["high"] = as_decimal_text(fetched_candle.high)
        row["low"] = as_decimal_text(fetched_candle.low)
        row["close"] = as_decimal_text(fetched_candle.close)
        row["volume"] = as_decimal_text(fetched_candle.volume)
        if "close_time" in row:
            row["close_time"] = str(existing.open_time + interval_ms - 1)
        if "is_closed" in row:
            row["is_closed"] = "1"
        if "updated_at" in row:
            row["updated_at"] = str(repaired_at)
        if "source_id" in row:
            row["source_id"] = "ccxt:binance:fetch_ohlcv"
        if "provenance" in row:
            row["provenance"] = "native"
        if "source_symbol" in row:
            row["source_symbol"] = "BTCUSDC"
        if "provenance_note" in row:
            row["provenance_note"] = (
                "terminal candle revalidated/repaired from final Binance OHLCV via CCXT"
            )
        rows_by_ts[existing.open_time] = row

    repaired_rows = [rows_by_ts[int(row["open_time"])] for row in rows]
    repaired_rows.sort(key=lambda row: int(row["open_time"]))
    return repaired_rows, repaired_count


def append_updates(
    fieldnames: list[str],
    rows: list[dict[str, str]],
    candles: list[Candle],
    fetched: list[list[Any]],
    *,
    symbol: str,
    timeframe: str,
) -> tuple[list[dict[str, str]], int]:
    interval_ms = TIMEFRAME_MS[timeframe]
    existing_ts = {candle.open_time for candle in candles}
    new_rows: list[dict[str, str]] = []
    updated_at = int(datetime.now(UTC).timestamp() * 1000)

    for item in fetched:
        ts = int(item[0])
        if ts in existing_ts:
            continue

        candle = Candle(
            open_time=ts,
            open=decimal_value(item[1], "ccxt open"),
            high=decimal_value(item[2], "ccxt high"),
            low=decimal_value(item[3], "ccxt low"),
            close=decimal_value(item[4], "ccxt close"),
            volume=decimal_value(item[5], "ccxt volume"),
            raw={},
        )
        validate_ohlcv(candle, "CCXT")

        row = {name: "" for name in fieldnames}
        values = {
            "exchange_id": "binance",
            "market_type": "spot",
            "symbol": symbol,
            "timeframe": timeframe,
            "open_time": str(ts),
            "open": as_decimal_text(candle.open),
            "high": as_decimal_text(candle.high),
            "low": as_decimal_text(candle.low),
            "close": as_decimal_text(candle.close),
            "volume": as_decimal_text(candle.volume),
            "close_time": str(ts + interval_ms - 1),
            "is_closed": "1",
            "updated_at": str(updated_at),
            "source_id": "ccxt:binance:fetch_ohlcv",
            "provenance": "native",
            "source_symbol": "BTCUSDC",
            "provenance_note": "append via CCXT fetch_ohlcv",
        }
        for key, value in values.items():
            if key in row:
                row[key] = value
        new_rows.append(row)

    combined = rows + new_rows
    combined.sort(key=lambda row: int(row["open_time"]))
    return combined, len(new_rows)


def write_source_csv(
    path: Path, fieldnames: list[str], rows: list[dict[str, str]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_money_heist_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MONEY_HEIST_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "timestamp": row["open_time"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                }
            )


def build_plan(
    *,
    minimal_path: Path,
    rows: list[dict[str, str]],
    metadata: dict[str, Any],
    code_version: str,
) -> dict[str, Any]:
    n = len(rows)
    if n < 180:
        raise SyncError("Dataset trop court pour générer le plan 60/20/20")

    design_count = int(n * 0.60)
    validation_count = int(n * 0.20)
    oos_count = n - design_count - validation_count
    interval_ms = TIMEFRAME_MS["1h"]

    def close_iso(index: int) -> str:
        return iso_utc(int(rows[index]["open_time"]) + interval_ms)

    market_constraints = {
        "qty_step": metadata.get("qty_step"),
        "min_qty": metadata.get("min_qty"),
        "min_notional": metadata.get("min_notional"),
        "max_qty": metadata.get("max_qty"),
        "max_leverage": "1",
        "note": (
            "Références publiques CCXT/Binance. Vérifier avant une campagne officielle "
            "si une contrainte est absente."
        ),
    }

    return {
        "campaign": "Campagne 00 — Binance BTC/USDC H1 historique réel",
        "purpose": (
            "Premier replay réel sur le dataset utilisateur consolidé et mis à jour. "
            "Trading fictif; aucun ordre LIVE."
        ),
        "dataset": {
            "csv_path": str(minimal_path.resolve()),
            "symbol": "BTC/USDC",
            "quote_asset": "USDC",
            "timeframe": "1h",
            "source": "binance_spot_user_archive_plus_ccxt",
            "candle_interval_seconds": 3600,
            "closed_candles": n,
            "first_open_utc": iso_utc(int(rows[0]["open_time"])),
            "last_open_utc": iso_utc(int(rows[-1]["open_time"])),
            "sha256": sha256_file(minimal_path),
        },
        "splits": {
            "design_start": close_iso(0),
            "design_end": close_iso(design_count - 1),
            "validation_start": close_iso(design_count),
            "validation_end": close_iso(design_count + validation_count - 1),
            "oos_start": close_iso(design_count + validation_count),
            "oos_end": close_iso(n - 1),
            "design_bars": design_count,
            "validation_bars": validation_count,
            "oos_bars": oos_count,
        },
        "execution": {
            "initial_balance": "100",
            "initial_balance_currency": "USDC",
            "maker_fee_bps": "10",
            "taker_fee_bps": "10",
            "market_slippage_bps": "5",
            "code_version": code_version,
            "execution_model_version": "historical-ohlc-v1",
            "random_seed": 0,
            "fee_note": (
                "10 bps maker/taker = hypothèse conservatrice de campagne, "
                "pas un tarif personnel Binance garanti."
            ),
        },
        "market_constraints": market_constraints,
        "risk_dev": {
            "risk_profile_id": "dashboard_balanced_dev",
            "risk_version": "dashboard-balanced-dev-v1",
            "max_risk_per_trade_pct": "0.01",
            "max_daily_loss_pct": "0.03",
            "max_drawdown_pct": "0.10",
            "max_portfolio_risk_pct": "0.03",
            "max_positions": 3,
            "max_leverage": "1",
            "max_correlated_exposure_pct": "0.02",
            "min_expected_rr": "1.5",
            "note": "Profil DEV de backtest; ce n'est pas le Balanced LIVE approuvé.",
        },
        "ai": {
            "mode": "MOCK",
            "hard_budget_eur": "1",
            "model_id": "mock-backtest-v1",
            "input_per_million_eur": "0",
            "output_per_million_eur": "0",
        },
        "walk_forward": {
            "enabled": False,
            "note": (
                "On valide d'abord la campagne simple DESIGN/VALIDATION/OOS. "
                "Walk-forward ensuite, sans modifier l'OOS."
            ),
        },
        "ccxt": metadata,
        "acceptance_before_results": [
            "Dataset validé sans gap, doublon ou incohérence OHLCV.",
            "DESIGN, VALIDATION et OOS terminent sans échec technique.",
            "Le scanner génère des opportunités sur la campagne.",
            "Les exports JSON/CSV Batch 16 sont générés.",
            "Un second run identique reproduit le fingerprint business.",
            "Le PnL positif n'est pas à lui seul un critère de réussite de l'infrastructure.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Met à jour btc_1h.csv Binance BTC/USDC avec CCXT et produit le CSV Money Heist."
    )
    parser.add_argument(
        "--input",
        default="btc_candles.zip",
        help="btc_candles.zip ou btc_1h.csv (défaut: btc_candles.zip)",
    )
    parser.add_argument(
        "--output-dir",
        default=r"data\backtest",
        help=r"Dossier de sortie (défaut: data\backtest)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Valide/construit les sorties sans appeler CCXT/Binance.",
    )
    parser.add_argument(
        "--code-version",
        default=DEFAULT_CODE_VERSION,
        help="Commit Git immuable utilisé par la campagne.",
    )
    args = parser.parse_args()

    source_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fieldnames, rows = open_source_csv(source_path)
    candles = parse_and_validate(fieldnames, rows, symbol="BTC/USDC", timeframe="1h")
    original_count = len(candles)

    print("=== SOURCE H1 EXISTANTE ===")
    print(f"Fichier        : {source_path}")
    print(f"Bougies        : {original_count}")
    print(f"Première       : {iso_utc(candles[0].open_time)}")
    print(f"Dernière       : {iso_utc(candles[-1].open_time)}")
    print("Doublons       : 0")
    print("Gaps H1        : 0")
    print("OHLCV          : valide")
    print()

    metadata: dict[str, Any] = {
        "mode": "offline",
        "ccxt_version": None,
        "qty_step": None,
        "min_qty": None,
        "max_qty": None,
        "min_notional": None,
    }
    fetched: list[list[Any]] = []

    if not args.offline:
        print("=== SYNCHRONISATION CCXT / BINANCE ===")
        fetched, metadata = fetch_ccxt_updates(
            symbol="BTC/USDC",
            timeframe="1h",
            last_existing=candles[-1],
        )
        print(f"CCXT version   : {metadata.get('ccxt_version')}")
        print(f"Heure exchange : {metadata.get('exchange_now_utc')}")
        print(f"Dernière close : {metadata.get('target_last_closed_utc')}")
        print(f"Lignes reçues  : {len(fetched)}")
        print()

    repaired_rows = rows
    repaired_count = 0
    if fetched:
        repaired_rows, repaired_count = repair_trailing_overlap(
            fieldnames,
            rows,
            candles,
            fetched,
            timeframe="1h",
        )

    # Re-parse after any safe terminal repair before appending new candles.
    repaired_candles = parse_and_validate(
        fieldnames,
        repaired_rows,
        symbol="BTC/USDC",
        timeframe="1h",
    )

    combined_rows, added_count = append_updates(
        fieldnames,
        repaired_rows,
        repaired_candles,
        fetched,
        symbol="BTC/USDC",
        timeframe="1h",
    )

    # Revalide le résultat final complet.
    final_candles = parse_and_validate(
        fieldnames,
        combined_rows,
        symbol="BTC/USDC",
        timeframe="1h",
    )

    consolidated_path = output_dir / "binance_btc_usdc_1h_consolidated.csv"
    minimal_path = output_dir / "binance_btc_usdc_1h_money_heist.csv"
    plan_path = output_dir / "campaign_00_binance_btc_usdc_h1.json"

    write_source_csv(consolidated_path, fieldnames, combined_rows)
    write_money_heist_csv(minimal_path, combined_rows)

    plan = build_plan(
        minimal_path=minimal_path,
        rows=combined_rows,
        metadata=metadata,
        code_version=args.code_version,
    )
    plan_path.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("=== RÉSULTAT ===")
    print(f"Bougies avant   : {original_count}")
    print(f"Bougies réparées: {repaired_count}")
    print(f"Bougies ajoutées: {added_count}")
    print(f"Bougies après   : {len(final_candles)}")
    print(f"Dernière H1    : {iso_utc(final_candles[-1].open_time)}")
    print("Doublons       : 0")
    print("Gaps H1        : 0")
    print("OHLCV          : valide")
    print()
    print(f"CSV consolidé  : {consolidated_path.resolve()}")
    print(f"CSV Dashboard  : {minimal_path.resolve()}")
    print(f"Plan campagne  : {plan_path.resolve()}")
    print(f"SHA256 dataset : {plan['dataset']['sha256']}")
    print()
    print("=== SPLITS 60 / 20 / 20 ===")
    splits = plan["splits"]
    print(f"DESIGN         : {splits['design_start']} -> {splits['design_end']}")
    print(
        f"VALIDATION     : {splits['validation_start']} -> {splits['validation_end']}"
    )
    print(f"OOS            : {splits['oos_start']} -> {splits['oos_end']}")
    print()
    print("=== CONTRAINTES CCXT/BINANCE ===")
    print(f"qty_step       : {metadata.get('qty_step')}")
    print(f"min_qty        : {metadata.get('min_qty')}")
    print(f"min_notional   : {metadata.get('min_notional')}")
    print(f"max_qty        : {metadata.get('max_qty')}")
    print()
    print("AI             : MOCK")
    print("Capital fictif : 100 USDC")
    print("Walk-forward   : OFF pour ce premier passage")
    print()
    print("Aucun fichier source n'a été écrasé.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SyncError as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        raise SystemExit(2)
