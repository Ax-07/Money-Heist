from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .models import Candle, SnapshotQuality


class MarketDataValidationError(ValueError):
    """Erreur de qualité empêchant la normalisation sûre des données."""


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    """Politique explicite de fraîcheur, sans fixer les timeframes du projet."""

    max_age: timedelta
    max_future_skew: timedelta = timedelta(seconds=5)

    def __post_init__(self) -> None:
        if self.max_age <= timedelta(0):
            raise ValueError("max_age must be > 0")
        if self.max_future_skew < timedelta(0):
            raise ValueError("max_future_skew must be >= 0")


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MarketDataValidationError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def is_stale(
    observed_at: datetime,
    *,
    now: datetime,
    policy: FreshnessPolicy,
) -> bool:
    observed_at = ensure_utc(observed_at)
    now = ensure_utc(now)

    if observed_at - now > policy.max_future_skew:
        raise MarketDataValidationError("observed_at is too far in the future")

    return now - observed_at > policy.max_age


def validate_candle_series(
    candles: Iterable[Candle],
    *,
    expected_interval: timedelta | None = None,
) -> tuple[Candle, ...]:
    """Valide l'ordre, l'unicité et la cohérence d'une série de bougies."""

    series = tuple(candles)
    if expected_interval is not None and expected_interval <= timedelta(0):
        raise ValueError("expected_interval must be > 0")

    previous: Candle | None = None
    seen_open_times: set[datetime] = set()
    symbol: str | None = None
    timeframe: str | None = None

    for candle in series:
        if symbol is None:
            symbol = candle.symbol
            timeframe = candle.timeframe
        elif candle.symbol != symbol or candle.timeframe != timeframe:
            raise MarketDataValidationError(
                "a candle series must contain one symbol and one timeframe"
            )

        if candle.open_time in seen_open_times:
            raise MarketDataValidationError("duplicate candle open_time detected")
        seen_open_times.add(candle.open_time)

        if previous is not None:
            if candle.open_time <= previous.open_time:
                raise MarketDataValidationError(
                    "candles must be strictly chronological"
                )
            if expected_interval is not None:
                delta = candle.open_time - previous.open_time
                if delta < expected_interval:
                    raise MarketDataValidationError(
                        "candle interval is shorter than expected"
                    )
                if delta % expected_interval != timedelta(0):
                    raise MarketDataValidationError(
                        "candle interval is not aligned with expected interval"
                    )
        previous = candle

    return series


def count_gaps(
    candles: Iterable[Candle],
    *,
    expected_interval: timedelta,
) -> int:
    """Compte les intervalles manquants entre bougies normalisées."""

    if expected_interval <= timedelta(0):
        raise ValueError("expected_interval must be > 0")

    series = validate_candle_series(candles, expected_interval=expected_interval)
    gaps = 0
    for previous, current in zip(series, series[1:]):
        delta = current.open_time - previous.open_time
        if delta > expected_interval:
            missing = int(delta // expected_interval) - 1
            gaps += max(0, missing)
    return gaps


def build_quality(
    *,
    stale: bool,
    missing_fields: Iterable[str] = (),
    gap_count: int = 0,
    has_duplicates: bool = False,
) -> SnapshotQuality:
    normalized_missing = tuple(sorted({field for field in missing_fields if field}))
    valid = not (stale or normalized_missing or gap_count > 0 or has_duplicates)
    return SnapshotQuality(
        is_stale=stale,
        missing_fields=normalized_missing,
        gap_count=gap_count,
        has_duplicates=has_duplicates,
        is_valid=valid,
    )
