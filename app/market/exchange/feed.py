from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.market.models import MarketSnapshot
from app.market.provider import MarketDataProvider

from .models import UnsafeMarketDataError


@dataclass(frozen=True, slots=True)
class PaperShadowMarketInput:
    """Boundary object ready for the existing scanner/PAPER/SHADOW path."""

    market_snapshot: MarketSnapshot
    market_context: Any
    scan_result: Any

    @property
    def opportunity(self) -> Any | None:
        return getattr(self.scan_result, "opportunity", None)


class PaperShadowMarketFeed:
    """Real Market Data -> existing Feature Engine -> existing deterministic Scanner.

    This class never invokes orchestration, Risk Engine or a broker. The caller keeps
    explicit authority over whether a produced opportunity is sent into the existing
    PAPER/SHADOW pipeline.
    """

    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        feature_engine: Any,
        scanner: Any,
        root_system_id: str,
    ) -> None:
        if not root_system_id.strip():
            raise ValueError("root_system_id must not be blank")
        self.provider = provider
        self.feature_engine = feature_engine
        self.scanner = scanner
        self.root_system_id = root_system_id

    async def build(
        self,
        *,
        symbol: str,
        timeframe: str,
        previous_market_context: Any | None = None,
    ) -> PaperShadowMarketInput:
        snapshot = await self.provider.get_snapshot(symbol)
        if not snapshot.quality.is_valid:
            raise UnsafeMarketDataError("invalid MarketSnapshot cannot feed PAPER/SHADOW")

        candles = snapshot.candles.get(timeframe)
        if not candles:
            raise UnsafeMarketDataError(
                f"MarketSnapshot has no candles for requested timeframe {timeframe!r}"
            )

        market_context = self.feature_engine.compute(
            candles,
            symbol=snapshot.symbol,
            timeframe=timeframe,
            source_snapshot_id=str(snapshot.snapshot_id),
            observed_at=snapshot.observed_at,
        )
        scan_result = self.scanner.scan(
            market_context,
            system_id=self.root_system_id,
            previous=previous_market_context,
        )
        return PaperShadowMarketInput(
            market_snapshot=snapshot,
            market_context=market_context,
            scan_result=scan_result,
        )
