from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import (
    ExchangeAdapterError,
    ExchangePayloadError,
    PublicHttpResponse,
    UnsafeMarketDataError,
)
from .transport import ResilientPublicHttpClient

KRAKEN_FUTURES_ANALYTICS_BASE_URL = "https://futures.kraken.com/api/charts/v1/analytics"
KRAKEN_FUTURES_SOURCE = "kraken_futures_analytics"
KRAKEN_FUTURES_INITIAL_SYMBOL_MAP: tuple[tuple[str, str], ...] = (
    ("BTC/EUR", "PF_XBTUSD"),
    ("ETH/EUR", "PF_ETHUSD"),
    ("SOL/EUR", "PF_SOLUSD"),
)
KRAKEN_FUTURES_ANALYTICS_INTERVALS = frozenset(
    {60, 300, 900, 1800, 3600, 14400, 43200, 86400, 604800}
)


@dataclass(frozen=True, slots=True)
class KrakenFuturesAnalyticsConfig:
    """Read-only public analytics policy used to build grounded Rio inputs."""

    interval_seconds: int = 300
    lookback: timedelta = timedelta(hours=2)
    max_metric_age: timedelta = timedelta(minutes=20)
    max_future_skew: timedelta = timedelta(seconds=5)
    symbol_map: tuple[tuple[str, str], ...] = KRAKEN_FUTURES_INITIAL_SYMBOL_MAP

    def __post_init__(self) -> None:
        if self.interval_seconds not in KRAKEN_FUTURES_ANALYTICS_INTERVALS:
            raise ValueError("unsupported Kraken Futures analytics interval")
        if self.lookback <= timedelta(0):
            raise ValueError("lookback must be > 0")
        if self.max_metric_age <= timedelta(0):
            raise ValueError("max_metric_age must be > 0")
        if self.max_future_skew < timedelta(0):
            raise ValueError("max_future_skew must be >= 0")
        if self.lookback < self.max_metric_age:
            raise ValueError("lookback must be >= max_metric_age")
        if not self.symbol_map:
            raise ValueError("symbol_map must not be empty")

        normalized: set[str] = set()
        instruments: set[str] = set()
        for symbol, instrument in self.symbol_map:
            canonical = _normalize_symbol(symbol)
            native = instrument.strip().upper()
            if not native:
                raise ValueError("Kraken Futures instrument must not be blank")
            if canonical in normalized:
                raise ValueError("symbol_map contains duplicate canonical symbols")
            if native in instruments:
                raise ValueError("symbol_map contains duplicate futures instruments")
            normalized.add(canonical)
            instruments.add(native)

    def instrument_for(self, symbol: str) -> str:
        canonical = _normalize_symbol(symbol)
        for configured_symbol, instrument in self.symbol_map:
            if _normalize_symbol(configured_symbol) == canonical:
                return instrument.strip().upper()
        raise ValueError(f"no Kraken Futures analytics instrument configured for {canonical}")


class DerivativesPositioningSnapshot(BaseModel):
    """Exchange-normalized public derivatives facts; it contains no trade recommendation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    source: str = Field(min_length=1, max_length=100)
    symbol: str = Field(min_length=1, max_length=50)
    instrument: str = Field(min_length=1, max_length=100)
    observed_at: datetime
    received_at: datetime
    funding_rate: Decimal | None = Field(default=None, allow_inf_nan=False)
    open_interest: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    open_interest_change_pct: Decimal | None = Field(default=None, allow_inf_nan=False)
    long_short_ratio: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    long_liquidations_notional: Decimal | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )
    short_liquidations_notional: Decimal | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )
    missing_fields: tuple[str, ...] = ()

    @field_validator("observed_at", "received_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("derivatives timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_clock_order(self) -> DerivativesPositioningSnapshot:
        if self.received_at < self.observed_at:
            raise ValueError("received_at must be >= observed_at")
        return self

    @property
    def available_metric_count(self) -> int:
        metrics = (
            self.funding_rate,
            self.open_interest,
            self.open_interest_change_pct,
            self.long_short_ratio,
            self.long_liquidations_notional,
            self.short_liquidations_notional,
        )
        return sum(value is not None for value in metrics)


@dataclass(frozen=True, slots=True)
class _MetricPoint:
    value: Decimal
    observed_at: datetime
    received_at: datetime


class KrakenFuturesAnalyticsProvider:
    """Unauthenticated Kraken Futures analytics adapter for Rio market context.

    The adapter has no account, order, margin or private API capability. It fetches
    only the public analytics required for positioning context. Kraken's public
    liquidation-volume chart is intentionally not projected into long/short
    liquidation fields because that endpoint exposes aggregate volume, not a
    trustworthy side split for the RioContext v1 contract.
    """

    def __init__(
        self,
        client: ResilientPublicHttpClient,
        *,
        config: KrakenFuturesAnalyticsConfig | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self.config = config or KrakenFuturesAnalyticsConfig()
        self._now = now

    async def get_positioning_snapshot(self, symbol: str) -> DerivativesPositioningSnapshot:
        canonical = _normalize_symbol(symbol)
        instrument = self.config.instrument_for(canonical)
        now = self._utc_now()
        since = int((now - self.config.lookback).timestamp())
        to = int(now.timestamp())

        analytics_types = ("open-interest", "long-short-ratio", "funding")
        raw_results = await asyncio.gather(
            *(
                self._fetch_analytics(
                    instrument,
                    analytics_type,
                    since=since,
                    to=to,
                )
                for analytics_type in analytics_types
            ),
            return_exceptions=True,
        )

        payloads: dict[str, PublicHttpResponse] = {}
        missing: set[str] = {
            "long_liquidations_notional",
            "short_liquidations_notional",
        }
        metric_names = {
            "open-interest": ("open_interest", "open_interest_change_pct"),
            "long-short-ratio": ("long_short_ratio",),
            "funding": ("funding_rate",),
        }

        for analytics_type, result in zip(analytics_types, raw_results, strict=True):
            if isinstance(result, UnsafeMarketDataError):
                raise result
            if isinstance(result, BaseException):
                if not isinstance(result, ExchangeAdapterError):
                    raise result
                missing.update(metric_names[analytics_type])
                continue
            payloads[analytics_type] = result

        points: dict[str, _MetricPoint] = {}
        open_interest_history: tuple[_MetricPoint, ...] = ()

        if response := payloads.get("open-interest"):
            try:
                open_interest_history = self._series_points(
                    response,
                    analytics_type="open-interest",
                    data_key="openInterest",
                    non_negative=True,
                    now=now,
                )
            except UnsafeMarketDataError:
                raise
            except ExchangeAdapterError:
                missing.update(("open_interest", "open_interest_change_pct"))
            else:
                fresh_oi = self._fresh_points(open_interest_history, now=now)
                if fresh_oi:
                    points["open_interest"] = fresh_oi[-1]
                else:
                    missing.add("open_interest")
                change = self._open_interest_change(open_interest_history, now=now)
                if change is not None:
                    points["open_interest_change_pct"] = change
                else:
                    missing.add("open_interest_change_pct")

        if response := payloads.get("long-short-ratio"):
            try:
                ratio_points = self._series_points(
                    response,
                    analytics_type="long-short-ratio",
                    data_key="ratio",
                    non_negative=True,
                    now=now,
                )
            except UnsafeMarketDataError:
                raise
            except ExchangeAdapterError:
                missing.add("long_short_ratio")
            else:
                fresh_ratio = self._fresh_points(ratio_points, now=now)
                if fresh_ratio:
                    points["long_short_ratio"] = fresh_ratio[-1]
                else:
                    missing.add("long_short_ratio")

        if response := payloads.get("funding"):
            try:
                funding_points = self._funding_points(response, now=now)
            except UnsafeMarketDataError:
                raise
            except ExchangeAdapterError:
                missing.add("funding_rate")
            else:
                fresh_funding = self._fresh_points(funding_points, now=now)
                if fresh_funding:
                    points["funding_rate"] = fresh_funding[-1]
                else:
                    missing.add("funding_rate")

        for metric in ("funding_rate", "open_interest", "long_short_ratio"):
            if metric not in points:
                missing.add(metric)

        if not points:
            raise UnsafeMarketDataError(
                f"Kraken Futures analytics produced no usable positioning metrics for {canonical}"
            )

        observed_at = max(point.observed_at for point in points.values())
        received_at = max(point.received_at for point in points.values())
        if observed_at > received_at:
            raise UnsafeMarketDataError("Kraken Futures analytics clock order is unsafe")

        return DerivativesPositioningSnapshot(
            source=KRAKEN_FUTURES_SOURCE,
            symbol=canonical,
            instrument=instrument,
            observed_at=observed_at,
            received_at=received_at,
            funding_rate=self._value(points, "funding_rate"),
            open_interest=self._value(points, "open_interest"),
            open_interest_change_pct=self._value(points, "open_interest_change_pct"),
            long_short_ratio=self._value(points, "long_short_ratio"),
            missing_fields=tuple(sorted(missing)),
        )

    async def _fetch_analytics(
        self,
        instrument: str,
        analytics_type: str,
        *,
        since: int,
        to: int,
    ) -> PublicHttpResponse:
        return await self._client.get_json(
            f"{KRAKEN_FUTURES_ANALYTICS_BASE_URL}/{instrument}/{analytics_type}",
            params={
                "since": since,
                "to": to,
                "interval": self.config.interval_seconds,
            },
        )

    def _series_points(
        self,
        response: PublicHttpResponse,
        *,
        analytics_type: str,
        data_key: str,
        non_negative: bool,
        now: datetime,
    ) -> tuple[_MetricPoint, ...]:
        result = self._result_payload(response, analytics_type=analytics_type)
        timestamps = self._timestamps(result, analytics_type=analytics_type)
        data = result.get("data")
        series = data.get(data_key) if isinstance(data, Mapping) else data
        if not _is_sequence(series):
            raise ExchangePayloadError(
                f"Kraken Futures {analytics_type} data must contain {data_key} series"
            )
        close_series = self._scalar_or_ohlc_close_series(
            series,
            expected_count=len(timestamps),
            field=f"{analytics_type}.{data_key}",
        )

        points = []
        for index, (timestamp, raw_value) in enumerate(
            zip(timestamps, close_series, strict=True)
        ):
            value = self._decimal(
                raw_value,
                field=f"{analytics_type}.{data_key}[{index}]",
                non_negative=non_negative,
            )
            observed_at = self._timestamp(timestamp, field=f"{analytics_type}.timestamp[{index}]")
            self._validate_timestamp(
                observed_at,
                received_at=response.received_at,
                now=now,
                field=analytics_type,
            )
            points.append(
                _MetricPoint(
                    value=value,
                    observed_at=observed_at,
                    received_at=response.received_at,
                )
            )
        if not points:
            raise ExchangePayloadError(f"Kraken Futures {analytics_type} series is empty")
        return tuple(points)

    def _funding_points(
        self,
        response: PublicHttpResponse,
        *,
        now: datetime,
    ) -> tuple[_MetricPoint, ...]:
        result = self._result_payload(response, analytics_type="funding")
        timestamps = self._timestamps(result, analytics_type="funding")
        data = result.get("data")
        if not isinstance(data, Mapping):
            raise ExchangePayloadError("Kraken Futures funding data must be an object")
        raw_rate = data.get("rate")
        if not _is_sequence(raw_rate):
            raise ExchangePayloadError("Kraken Futures funding data missing rate series")

        close_series = self._funding_close_series(raw_rate, expected_count=len(timestamps))
        points = []
        for index, (timestamp, raw_value) in enumerate(
            zip(timestamps, close_series, strict=True)
        ):
            value = self._decimal(
                raw_value,
                field=f"funding.rate[{index}]",
                non_negative=False,
            )
            observed_at = self._timestamp(timestamp, field=f"funding.timestamp[{index}]")
            self._validate_timestamp(
                observed_at,
                received_at=response.received_at,
                now=now,
                field="funding",
            )
            points.append(
                _MetricPoint(
                    value=value,
                    observed_at=observed_at,
                    received_at=response.received_at,
                )
            )
        if not points:
            raise ExchangePayloadError("Kraken Futures funding series is empty")
        return tuple(points)

    @staticmethod
    def _scalar_or_ohlc_close_series(
        raw_series: Sequence[Any],
        *,
        expected_count: int,
        field: str,
    ) -> tuple[Any, ...]:
        if len(raw_series) == expected_count and all(
            not _is_sequence(item) for item in raw_series
        ):
            return tuple(raw_series)
        if (
            len(raw_series) == 4
            and all(_is_sequence(item) for item in raw_series)
            and all(len(item) == expected_count for item in raw_series)
        ):
            return tuple(raw_series[3])
        if len(raw_series) == expected_count and all(
            _is_sequence(item) and len(item) >= 4 for item in raw_series
        ):
            return tuple(item[3] for item in raw_series)
        raise ExchangePayloadError(f"Kraken Futures {field} series shape is unsupported")

    @staticmethod
    def _funding_close_series(
        raw_rate: Sequence[Any],
        *,
        expected_count: int,
    ) -> tuple[Any, ...]:
        # Kraken documents funding as OHLC analytics. Accept both common JSON
        # encodings: four parallel OHLC arrays or one OHLC row per timestamp.
        if (
            len(raw_rate) == 4
            and all(_is_sequence(item) for item in raw_rate)
            and all(len(item) == expected_count for item in raw_rate)
        ):
            return tuple(raw_rate[3])
        if len(raw_rate) == expected_count and all(
            _is_sequence(item) and len(item) >= 4 for item in raw_rate
        ):
            return tuple(item[3] for item in raw_rate)
        if len(raw_rate) == expected_count and all(not _is_sequence(item) for item in raw_rate):
            return tuple(raw_rate)
        raise ExchangePayloadError("Kraken Futures funding rate shape is unsupported")

    def _open_interest_change(
        self,
        points: tuple[_MetricPoint, ...],
        *,
        now: datetime,
    ) -> _MetricPoint | None:
        fresh = self._fresh_points(points, now=now)
        if len(fresh) < 2:
            return None
        previous, current = fresh[-2], fresh[-1]
        if previous.value == 0:
            return None
        change = (current.value - previous.value) / previous.value * Decimal("100")
        return _MetricPoint(
            value=change,
            observed_at=current.observed_at,
            received_at=current.received_at,
        )

    def _fresh_points(
        self,
        points: tuple[_MetricPoint, ...],
        *,
        now: datetime,
    ) -> tuple[_MetricPoint, ...]:
        cutoff = now - self.config.max_metric_age
        return tuple(point for point in points if point.observed_at >= cutoff)

    @staticmethod
    def _result_payload(
        response: PublicHttpResponse,
        *,
        analytics_type: str,
    ) -> Mapping[str, Any]:
        payload = response.payload
        if not isinstance(payload, Mapping):
            raise ExchangePayloadError(
                f"Kraken Futures {analytics_type} response must be a JSON object"
            )
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise ExchangePayloadError(
                f"Kraken Futures {analytics_type} response missing result object"
            )
        errors = result.get("errors")
        if errors is None and isinstance(result.get("data"), Mapping):
            errors = result["data"].get("errors")
        if _is_sequence(errors) and errors:
            raise ExchangePayloadError(
                f"Kraken Futures {analytics_type} analytics returned errors"
            )
        return result

    @staticmethod
    def _timestamps(
        result: Mapping[str, Any],
        *,
        analytics_type: str,
    ) -> Sequence[Any]:
        timestamps = result.get("timestamp")
        if not _is_sequence(timestamps):
            raise ExchangePayloadError(
                f"Kraken Futures {analytics_type} response missing timestamp series"
            )
        return timestamps

    def _validate_timestamp(
        self,
        observed_at: datetime,
        *,
        received_at: datetime,
        now: datetime,
        field: str,
    ) -> None:
        received = _as_utc(received_at)
        if observed_at - received > self.config.max_future_skew:
            raise UnsafeMarketDataError(
                f"Kraken Futures {field} timestamp is later than local receipt time"
            )
        if observed_at - now > self.config.max_future_skew:
            raise UnsafeMarketDataError(
                f"Kraken Futures {field} timestamp is too far in the future"
            )

    @staticmethod
    def _timestamp(value: Any, *, field: str) -> datetime:
        if isinstance(value, bool):
            raise ExchangePayloadError(f"Kraken Futures {field} is not a timestamp")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ExchangePayloadError(f"Kraken Futures {field} is not a timestamp") from exc
        if not isfinite(numeric) or numeric <= 0:
            raise ExchangePayloadError(
                f"Kraken Futures {field} must be a positive finite timestamp"
            )
        seconds = numeric / 1000 if numeric >= 1_000_000_000_000 else numeric
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise ExchangePayloadError(f"Kraken Futures {field} is out of range") from exc

    @staticmethod
    def _decimal(value: Any, *, field: str, non_negative: bool) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ExchangePayloadError(f"Kraken Futures {field} is not a decimal") from exc
        if not result.is_finite():
            raise ExchangePayloadError(f"Kraken Futures {field} must be finite")
        if non_negative and result < 0:
            raise ExchangePayloadError(f"Kraken Futures {field} must be >= 0")
        return result

    @staticmethod
    def _value(points: Mapping[str, _MetricPoint], key: str) -> Decimal | None:
        point = points.get(key)
        return None if point is None else point.value

    def _utc_now(self) -> datetime:
        return _as_utc(self._now())


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized.count("/") != 1:
        raise ValueError("Kraken Futures symbols must use canonical BASE/QUOTE form")
    base, quote = normalized.split("/", 1)
    if not base or not quote or any(character.isspace() for character in normalized):
        raise ValueError("invalid Kraken Futures BASE/QUOTE symbol")
    return f"{base}/{quote}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
