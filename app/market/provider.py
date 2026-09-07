from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from .models import Candle, MarketSnapshot


@runtime_checkable
class MarketDataProvider(Protocol):
    """Port exchange-agnostic pour la couche Market Data."""

    async def get_snapshot(self, symbol: str) -> MarketSnapshot:
        """Retourne le snapshot normalisé le plus récent pour un symbole."""
        ...

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> Sequence[Candle]:
        """Retourne au plus ``limit`` bougies normalisées."""
        ...


class InMemoryMarketDataProvider:
    """Provider déterministe pour développement, replay et tests sans exchange."""

    def __init__(
        self,
        *,
        snapshots: dict[str, MarketSnapshot] | None = None,
        candles: dict[tuple[str, str], Sequence[Candle]] | None = None,
    ) -> None:
        self._snapshots = dict(snapshots or {})
        self._candles = {
            key: tuple(value)
            for key, value in (candles or {}).items()
        }

    async def get_snapshot(self, symbol: str) -> MarketSnapshot:
        try:
            return self._snapshots[symbol]
        except KeyError as exc:
            raise KeyError(f"no market snapshot for symbol {symbol!r}") from exc

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> Sequence[Candle]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        series = self._candles.get((symbol, timeframe), ())
        return series[-limit:]

    def put_snapshot(self, snapshot: MarketSnapshot) -> None:
        self._snapshots[snapshot.symbol] = snapshot

    def put_candles(self, candles: Sequence[Candle]) -> None:
        if not candles:
            return
        symbol = candles[0].symbol
        timeframe = candles[0].timeframe
        if any(c.symbol != symbol or c.timeframe != timeframe for c in candles):
            raise ValueError("all candles must share symbol and timeframe")
        self._candles[(symbol, timeframe)] = tuple(candles)
