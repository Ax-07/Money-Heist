from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any, Callable, Mapping, Sequence

from app.market.models import Candle, MarketSnapshot
from app.market.quality import (
    FreshnessPolicy,
    MarketDataValidationError,
    count_gaps,
    validate_candle_series,
)
from app.market.snapshot import create_market_snapshot
from app.trading.risk.models import MarketConstraints

from .models import (
    CurrentPrice,
    ExchangePayloadError,
    ExchangeRateLimitError,
    PublicHttpResponse,
    SymbolMetadata,
    UnsafeMarketDataError,
)
from .transport import ResilientPublicHttpClient


KRAKEN_PUBLIC_BASE_URL = "https://api.kraken.com/0/public"
KRAKEN_SOURCE = "kraken_spot"
KRAKEN_INITIAL_SYMBOLS = ("BTC/EUR", "ETH/EUR", "SOL/EUR")

KRAKEN_INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
    "15d": 21600,
}


@dataclass(frozen=True, slots=True)
class KrakenAdapterConfig:
    freshness_policy: FreshnessPolicy
    snapshot_timeframes: tuple[str, ...]
    metadata_max_age: timedelta

    def __post_init__(self) -> None:
        if not self.snapshot_timeframes:
            raise ValueError("snapshot_timeframes must not be empty")
        unsupported = tuple(
            timeframe
            for timeframe in self.snapshot_timeframes
            if timeframe not in KRAKEN_INTERVAL_MINUTES
        )
        if unsupported:
            raise ValueError(f"unsupported Kraken timeframes: {unsupported!r}")
        if len(set(self.snapshot_timeframes)) != len(self.snapshot_timeframes):
            raise ValueError("snapshot_timeframes must not contain duplicates")
        if self.metadata_max_age <= timedelta(0):
            raise ValueError("metadata_max_age must be > 0")


class KrakenPublicMarketDataProvider:
    """Kraken Spot public adapter feeding Money Heist normalized market models.

    It deliberately has no authentication or order method. Its synchronous
    ``get_market_constraints`` method only serves metadata previously refreshed
    through public Market Data calls, allowing direct injection into the existing
    PAPER/SHADOW constraint port without network I/O inside the Risk Engine path.
    """

    def __init__(
        self,
        client: ResilientPublicHttpClient,
        *,
        config: KrakenAdapterConfig,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._client = client
        self.config = config
        self._now = now
        self._metadata: dict[str, SymbolMetadata] = {}

    async def get_snapshot(self, symbol: str) -> MarketSnapshot:
        symbol = self._normalize_symbol(symbol)
        metadata = await self._ensure_metadata(symbol)
        if metadata.status.lower() != "online":
            raise UnsafeMarketDataError(
                f"Kraken symbol {symbol} status is {metadata.status!r}, not 'online'"
            )

        current = await self.get_current_price(symbol)
        candle_sets: dict[str, Sequence[Candle]] = {}
        received_at = current.received_at
        expected_intervals: dict[str, timedelta] = {}

        for timeframe in self.config.snapshot_timeframes:
            candles, candles_received_at = await self._fetch_candles(symbol, timeframe)
            self._validate_current_ohlc(candles, received_at=candles_received_at)
            candle_sets[timeframe] = candles
            expected_intervals[timeframe] = self._timeframe_delta(timeframe)
            received_at = max(received_at, candles_received_at)

        now = self._utc_now()
        if received_at - now > self.config.freshness_policy.max_future_skew:
            raise UnsafeMarketDataError("Kraken receipt timestamp is too far in the future")
        try:
            snapshot = create_market_snapshot(
                symbol=symbol,
                source=KRAKEN_SOURCE,
                observed_at=current.observed_at,
                received_at=received_at,
                now=now,
                freshness_policy=self.config.freshness_policy,
                last_price=current.price,
                candle_sets=candle_sets,
                expected_intervals=expected_intervals,
            )
        except (MarketDataValidationError, ValueError) as exc:
            raise UnsafeMarketDataError(f"invalid Kraken market snapshot: {exc}") from exc

        if not snapshot.quality.is_valid:
            raise UnsafeMarketDataError(
                "Kraken market snapshot failed quality checks: "
                f"stale={snapshot.quality.is_stale}, "
                f"missing={snapshot.quality.missing_fields}, "
                f"gaps={snapshot.quality.gap_count}, "
                f"duplicates={snapshot.quality.has_duplicates}"
            )
        return snapshot

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> Sequence[Candle]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        candles, _ = await self._fetch_candles(self._normalize_symbol(symbol), timeframe)
        return candles[-min(limit, len(candles)) :]

    async def get_current_price(self, symbol: str) -> CurrentPrice:
        symbol = self._normalize_symbol(symbol)
        response = await self._call(
            "Trades",
            params={"pair": symbol, "assetVersion": 1, "count": 1},
        )
        pair_payload = self._single_pair_payload(response.payload, endpoint="Trades")
        if not isinstance(pair_payload, list) or not pair_payload:
            raise ExchangePayloadError("Kraken Trades result must contain at least one trade")
        trade = pair_payload[-1]
        if not isinstance(trade, list) or len(trade) < 3:
            raise ExchangePayloadError("Kraken trade entry is incomplete")

        price = self._positive_decimal(trade[0], field="trade.price")
        timestamp = self._timestamp_from_seconds(trade[2], field="trade.timestamp")
        if response.received_at < timestamp:
            raise UnsafeMarketDataError(
                "Kraken trade timestamp is later than local receipt time; clock order is unsafe"
            )
        return CurrentPrice(
            symbol=symbol,
            price=price,
            observed_at=timestamp,
            received_at=response.received_at,
            source=KRAKEN_SOURCE,
        )

    async def refresh_symbol_metadata(self, symbol: str) -> SymbolMetadata:
        symbol = self._normalize_symbol(symbol)
        response = await self._call(
            "AssetPairs",
            params={"pair": symbol, "assetVersion": 1},
        )
        pair_key, payload = self._single_pair_item(response.payload, endpoint="AssetPairs")
        if not isinstance(payload, Mapping):
            raise ExchangePayloadError("Kraken AssetPairs pair payload must be an object")

        required = (
            "base",
            "quote",
            "pair_decimals",
            "lot_decimals",
            "ordermin",
            "costmin",
            "tick_size",
            "status",
        )
        missing = tuple(name for name in required if payload.get(name) is None)
        if missing:
            raise ExchangePayloadError(
                f"Kraken AssetPairs missing required fields: {', '.join(missing)}"
            )

        price_precision = self._non_negative_int(payload["pair_decimals"], "pair_decimals")
        quantity_precision = self._non_negative_int(payload["lot_decimals"], "lot_decimals")
        metadata = SymbolMetadata(
            symbol=symbol,
            exchange_symbol=str(pair_key),
            source=KRAKEN_SOURCE,
            base_asset=self._required_text(payload["base"], "base"),
            quote_asset=self._required_text(payload["quote"], "quote"),
            status=self._required_text(payload["status"], "status"),
            tick_size=self._positive_decimal(payload["tick_size"], field="tick_size"),
            qty_step=Decimal(1).scaleb(-quantity_precision),
            min_qty=self._positive_decimal(payload["ordermin"], field="ordermin"),
            min_notional=self._positive_decimal(payload["costmin"], field="costmin"),
            price_precision=price_precision,
            quantity_precision=quantity_precision,
            received_at=response.received_at,
        )
        self._metadata[symbol] = metadata
        return metadata

    def get_cached_symbol_metadata(self, symbol: str) -> SymbolMetadata | None:
        symbol = self._normalize_symbol(symbol)
        metadata = self._metadata.get(symbol)
        if metadata is None:
            return None
        now = self._utc_now()
        if metadata.received_at - now > self.config.freshness_policy.max_future_skew:
            return None
        if now - metadata.received_at > self.config.metadata_max_age:
            return None
        return metadata

    def get_market_constraints(self, *, symbol: str) -> MarketConstraints | None:
        """Existing Batch 09/11 synchronous provider contract; missing/stale => fail closed."""

        metadata = self.get_cached_symbol_metadata(symbol)
        if metadata is None or metadata.status.lower() != "online":
            return None
        return metadata.to_market_constraints()

    async def _ensure_metadata(self, symbol: str) -> SymbolMetadata:
        cached = self.get_cached_symbol_metadata(symbol)
        if cached is not None:
            return cached
        return await self.refresh_symbol_metadata(symbol)

    async def _fetch_candles(
        self,
        symbol: str,
        timeframe: str,
    ) -> tuple[tuple[Candle, ...], datetime]:
        if timeframe not in KRAKEN_INTERVAL_MINUTES:
            raise ValueError(f"unsupported Kraken timeframe {timeframe!r}")
        interval_minutes = KRAKEN_INTERVAL_MINUTES[timeframe]
        response = await self._call(
            "OHLC",
            params={
                "pair": symbol,
                "assetVersion": 1,
                "interval": interval_minutes,
            },
        )
        pair_payload = self._single_pair_payload(response.payload, endpoint="OHLC")
        if not isinstance(pair_payload, list) or not pair_payload:
            raise ExchangePayloadError("Kraken OHLC result must contain at least one candle")

        interval = timedelta(minutes=interval_minutes)
        candles: list[Candle] = []
        for index, row in enumerate(pair_payload):
            if not isinstance(row, list) or len(row) < 7:
                raise ExchangePayloadError(f"Kraken OHLC row {index} is incomplete")
            open_time = self._timestamp_from_seconds(row[0], field=f"ohlc[{index}].time")
            try:
                candle = Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=open_time,
                    close_time=open_time + interval,
                    open=self._positive_decimal(row[1], field=f"ohlc[{index}].open"),
                    high=self._positive_decimal(row[2], field=f"ohlc[{index}].high"),
                    low=self._positive_decimal(row[3], field=f"ohlc[{index}].low"),
                    close=self._positive_decimal(row[4], field=f"ohlc[{index}].close"),
                    volume=self._non_negative_decimal(row[6], field=f"ohlc[{index}].volume"),
                    is_closed=index < len(pair_payload) - 1,
                )
            except ValueError as exc:
                raise ExchangePayloadError(f"invalid Kraken OHLC row {index}: {exc}") from exc
            candles.append(candle)

        try:
            validated = validate_candle_series(candles, expected_interval=interval)
            gaps = count_gaps(validated, expected_interval=interval)
        except MarketDataValidationError as exc:
            raise ExchangePayloadError(f"invalid Kraken OHLC series: {exc}") from exc
        if gaps:
            raise ExchangePayloadError(f"Kraken OHLC series contains {gaps} missing intervals")
        return validated, response.received_at


    def _validate_current_ohlc(
        self,
        candles: Sequence[Candle],
        *,
        received_at: datetime,
    ) -> None:
        if not candles:
            raise UnsafeMarketDataError("Kraken OHLC series is empty")
        current = candles[-1]
        if current.is_closed:
            raise UnsafeMarketDataError("Kraken OHLC series is missing its current open candle")
        skew = self.config.freshness_policy.max_future_skew
        if current.open_time - received_at > skew:
            raise UnsafeMarketDataError("Kraken current OHLC candle starts too far in the future")
        if received_at - current.close_time > skew:
            raise UnsafeMarketDataError("Kraken current OHLC candle is stale for its timeframe")

    async def _call(
        self,
        endpoint: str,
        *,
        params: Mapping[str, str | int],
    ) -> PublicHttpResponse:
        response = await self._client.get_json(
            f"{KRAKEN_PUBLIC_BASE_URL}/{endpoint}",
            params=params,
        )
        payload = response.payload
        if not isinstance(payload, Mapping):
            raise ExchangePayloadError("Kraken response must be a JSON object")
        errors = payload.get("error")
        if not isinstance(errors, list):
            raise ExchangePayloadError("Kraken response missing error list")
        if errors:
            normalized = tuple(str(error) for error in errors)
            joined = "; ".join(normalized)
            if any(
                "rate limit" in error.lower() or "throttled" in error.lower()
                for error in normalized
            ):
                raise ExchangeRateLimitError(429, f"Kraken API rate limited request: {joined}")
            raise ExchangePayloadError(f"Kraken API error: {joined}")
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise ExchangePayloadError("Kraken response missing result object")
        return response

    @staticmethod
    def _single_pair_item(payload: Any, *, endpoint: str) -> tuple[str, Any]:
        if not isinstance(payload, Mapping):
            raise ExchangePayloadError(f"Kraken {endpoint} response must be an object")
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise ExchangePayloadError(f"Kraken {endpoint} response missing result object")
        pair_items = [(key, value) for key, value in result.items() if key != "last"]
        if len(pair_items) != 1:
            raise ExchangePayloadError(
                f"Kraken {endpoint} expected exactly one pair result, got {len(pair_items)}"
            )
        return str(pair_items[0][0]), pair_items[0][1]

    @classmethod
    def _single_pair_payload(cls, payload: Any, *, endpoint: str) -> Any:
        return cls._single_pair_item(payload, endpoint=endpoint)[1]

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if normalized.count("/") != 1:
            raise ValueError("Kraken adapter symbols must use canonical BASE/QUOTE form")
        base, quote = normalized.split("/", 1)
        if not base or not quote or any(char.isspace() for char in normalized):
            raise ValueError("invalid Kraken BASE/QUOTE symbol")
        return f"{base}/{quote}"

    @staticmethod
    def _required_text(value: Any, field: str) -> str:
        text = str(value).strip()
        if not text:
            raise ExchangePayloadError(f"Kraken {field} must not be blank")
        return text

    @staticmethod
    def _positive_decimal(value: Any, *, field: str) -> Decimal:
        result = KrakenPublicMarketDataProvider._decimal(value, field=field)
        if result <= 0:
            raise ExchangePayloadError(f"Kraken {field} must be > 0")
        return result

    @staticmethod
    def _non_negative_decimal(value: Any, *, field: str) -> Decimal:
        result = KrakenPublicMarketDataProvider._decimal(value, field=field)
        if result < 0:
            raise ExchangePayloadError(f"Kraken {field} must be >= 0")
        return result

    @staticmethod
    def _decimal(value: Any, *, field: str) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ExchangePayloadError(f"Kraken {field} is not a decimal") from exc
        if not result.is_finite():
            raise ExchangePayloadError(f"Kraken {field} must be finite")
        return result

    @staticmethod
    def _non_negative_int(value: Any, field: str) -> int:
        if isinstance(value, bool):
            raise ExchangePayloadError(f"Kraken {field} must be an integer")
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ExchangePayloadError(f"Kraken {field} must be an integer") from exc
        if str(result) != str(value).strip() and not isinstance(value, int):
            # Reject 1.5 / "1.5" instead of silently truncating.
            try:
                if float(value) != result:
                    raise ExchangePayloadError(f"Kraken {field} must be an integer")
            except (TypeError, ValueError):
                raise ExchangePayloadError(f"Kraken {field} must be an integer") from None
        if result < 0:
            raise ExchangePayloadError(f"Kraken {field} must be >= 0")
        return result

    @staticmethod
    def _timestamp_from_seconds(value: Any, *, field: str) -> datetime:
        try:
            seconds = float(value)
        except (TypeError, ValueError) as exc:
            raise ExchangePayloadError(f"Kraken {field} is not a timestamp") from exc
        if not isfinite(seconds) or seconds <= 0:
            raise ExchangePayloadError(f"Kraken {field} must be a positive finite timestamp")
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise ExchangePayloadError(f"Kraken {field} is out of range") from exc

    @staticmethod
    def _timeframe_delta(timeframe: str) -> timedelta:
        try:
            minutes = KRAKEN_INTERVAL_MINUTES[timeframe]
        except KeyError as exc:
            raise ValueError(f"unsupported Kraken timeframe {timeframe!r}") from exc
        return timedelta(minutes=minutes)

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("now() must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)

