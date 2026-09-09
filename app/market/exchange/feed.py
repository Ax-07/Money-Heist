from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from app.market.models import MarketSnapshot
from app.market.provider import MarketDataProvider

from .models import UnsafeMarketDataError


class MarketSidecarRefreshStatus(StrEnum):
    REFRESHED = "REFRESHED"
    CACHED = "CACHED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class MarketSidecarRefreshResult:
    """Non-critical context refresh diagnostic attached to one PAPER/SHADOW input."""

    refresher_id: str
    status: MarketSidecarRefreshStatus
    symbol: str
    observed_at: datetime | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not self.refresher_id.strip():
            raise ValueError("refresher_id must not be blank")
        if not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        if self.observed_at is not None:
            if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
                raise ValueError("sidecar observed_at must be timezone-aware")
            object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))


class MarketSidecarRefresher(Protocol):
    refresher_id: str

    async def refresh_for_market(
        self,
        *,
        symbol: str,
        observed_at: datetime,
    ) -> MarketSidecarRefreshResult: ...


@dataclass(frozen=True, slots=True)
class PaperShadowMarketInput:
    """Boundary object ready for the existing scanner/PAPER/SHADOW path."""

    market_snapshot: MarketSnapshot
    market_context: Any
    scan_result: Any
    sidecar_refreshes: tuple[MarketSidecarRefreshResult, ...] = ()

    @property
    def opportunity(self) -> Any | None:
        return getattr(self.scan_result, "opportunity", None)

    def sidecar_result(self, refresher_id: str) -> MarketSidecarRefreshResult | None:
        normalized = refresher_id.strip()
        if not normalized:
            raise ValueError("refresher_id must not be blank")
        for result in self.sidecar_refreshes:
            if result.refresher_id == normalized:
                return result
        return None


class PaperShadowMarketFeed:
    """Real Market Data -> existing Feature Engine -> deterministic Scanner.

    Optional sidecars refresh non-critical specialist context only after the Scanner
    produced an opportunity. Sidecar failures never downgrade otherwise-valid spot
    Market Data and never invoke orchestration, Risk Engine or a broker.
    """

    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        feature_engine: Any,
        scanner: Any,
        root_system_id: str,
        sidecar_refreshers: Sequence[MarketSidecarRefresher] = (),
    ) -> None:
        if not root_system_id.strip():
            raise ValueError("root_system_id must not be blank")
        self.provider = provider
        self.feature_engine = feature_engine
        self.scanner = scanner
        self.root_system_id = root_system_id
        self.sidecar_refreshers = tuple(sidecar_refreshers)
        refresher_ids = [refresher.refresher_id for refresher in self.sidecar_refreshers]
        if any(not item.strip() for item in refresher_ids):
            raise ValueError("sidecar refresher_id must not be blank")
        if len(refresher_ids) != len(set(refresher_ids)):
            raise ValueError("sidecar refresher_id values must be unique")

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

        refreshes: tuple[MarketSidecarRefreshResult, ...] = ()
        if getattr(scan_result, "opportunity", None) is not None and self.sidecar_refreshers:
            decision_time = getattr(market_context, "observed_at", snapshot.observed_at)
            refreshes = await self._refresh_sidecars(
                symbol=snapshot.symbol,
                observed_at=decision_time,
            )

        return PaperShadowMarketInput(
            market_snapshot=snapshot,
            market_context=market_context,
            scan_result=scan_result,
            sidecar_refreshes=refreshes,
        )

    async def _refresh_sidecars(
        self,
        *,
        symbol: str,
        observed_at: datetime,
    ) -> tuple[MarketSidecarRefreshResult, ...]:
        outcomes = await asyncio.gather(
            *(
                refresher.refresh_for_market(
                    symbol=symbol,
                    observed_at=observed_at,
                )
                for refresher in self.sidecar_refreshers
            ),
            return_exceptions=True,
        )
        results: list[MarketSidecarRefreshResult] = []
        for refresher, outcome in zip(self.sidecar_refreshers, outcomes, strict=True):
            if isinstance(outcome, asyncio.CancelledError):
                raise outcome
            if isinstance(outcome, BaseException):
                results.append(
                    MarketSidecarRefreshResult(
                        refresher_id=refresher.refresher_id,
                        status=MarketSidecarRefreshStatus.FAILED,
                        symbol=symbol,
                        message=f"{type(outcome).__name__}: {outcome}",
                    )
                )
                continue
            if not isinstance(outcome, MarketSidecarRefreshResult):
                results.append(
                    MarketSidecarRefreshResult(
                        refresher_id=refresher.refresher_id,
                        status=MarketSidecarRefreshStatus.FAILED,
                        symbol=symbol,
                        message="sidecar refresher returned an invalid result",
                    )
                )
                continue
            results.append(outcome)
        return tuple(results)
