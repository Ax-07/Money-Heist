"""Public exchange adapters for real Market Data only; no LIVE execution authority."""

from .feed import PaperShadowMarketFeed, PaperShadowMarketInput
from .kraken import (
    KRAKEN_INITIAL_SYMBOLS,
    KRAKEN_INTERVAL_MINUTES,
    KRAKEN_SOURCE,
    KrakenAdapterConfig,
    KrakenPublicMarketDataProvider,
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
    "ExchangeAdapterError",
    "ExchangeHttpError",
    "ExchangeNetworkError",
    "ExchangePayloadError",
    "ExchangeRateLimitError",
    "JsonTransport",
    "KRAKEN_INITIAL_SYMBOLS",
    "KRAKEN_INTERVAL_MINUTES",
    "KRAKEN_SOURCE",
    "KrakenAdapterConfig",
    "KrakenPublicMarketDataProvider",
    "PaperShadowMarketFeed",
    "PaperShadowMarketInput",
    "PublicHttpResponse",
    "ResilientPublicHttpClient",
    "RetryPolicy",
    "StdlibJsonTransport",
    "SymbolMetadata",
    "UnsafeMarketDataError",
]
