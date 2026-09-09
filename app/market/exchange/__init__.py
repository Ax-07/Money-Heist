"""Public exchange adapters for real Market Data only; no LIVE execution authority."""

from .feed import (
    MarketSidecarRefresher,
    MarketSidecarRefreshResult,
    MarketSidecarRefreshStatus,
    PaperShadowMarketFeed,
    PaperShadowMarketInput,
)
from .kraken import (
    KRAKEN_INITIAL_SYMBOLS,
    KRAKEN_INTERVAL_MINUTES,
    KRAKEN_SOURCE,
    KrakenAdapterConfig,
    KrakenPublicMarketDataProvider,
)
from .kraken_futures import (
    KRAKEN_FUTURES_ANALYTICS_BASE_URL,
    KRAKEN_FUTURES_ANALYTICS_INTERVALS,
    KRAKEN_FUTURES_INITIAL_SYMBOL_MAP,
    KRAKEN_FUTURES_SOURCE,
    DerivativesPositioningSnapshot,
    KrakenFuturesAnalyticsConfig,
    KrakenFuturesAnalyticsProvider,
)
from .models import (
    CurrentPrice,
    ExchangeAdapterError,
    ExchangeHttpError,
    ExchangeNetworkError,
    ExchangePayloadError,
    ExchangeRateLimitError,
    PublicHttpResponse,
    SymbolMetadata,
    UnsafeMarketDataError,
)
from .transport import JsonTransport, ResilientPublicHttpClient, RetryPolicy, StdlibJsonTransport

__all__ = [
    "CurrentPrice",
    "DerivativesPositioningSnapshot",
    "ExchangeAdapterError",
    "ExchangeHttpError",
    "ExchangeNetworkError",
    "ExchangePayloadError",
    "ExchangeRateLimitError",
    "JsonTransport",
    "KRAKEN_FUTURES_ANALYTICS_BASE_URL",
    "KRAKEN_FUTURES_ANALYTICS_INTERVALS",
    "KRAKEN_FUTURES_INITIAL_SYMBOL_MAP",
    "KRAKEN_FUTURES_SOURCE",
    "KRAKEN_INITIAL_SYMBOLS",
    "KRAKEN_INTERVAL_MINUTES",
    "KRAKEN_SOURCE",
    "KrakenAdapterConfig",
    "KrakenFuturesAnalyticsConfig",
    "KrakenFuturesAnalyticsProvider",
    "KrakenPublicMarketDataProvider",
    "MarketSidecarRefresher",
    "MarketSidecarRefreshResult",
    "MarketSidecarRefreshStatus",
    "PaperShadowMarketFeed",
    "PaperShadowMarketInput",
    "PublicHttpResponse",
    "ResilientPublicHttpClient",
    "RetryPolicy",
    "StdlibJsonTransport",
    "SymbolMetadata",
    "UnsafeMarketDataError",
]
