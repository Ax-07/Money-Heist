from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.agents.models import RioContext
from app.market.exchange.feed import (
    MarketSidecarRefreshResult,
    MarketSidecarRefreshStatus,
)
from app.market.exchange.kraken_futures import (
    DerivativesPositioningSnapshot,
    KrakenFuturesAnalyticsProvider,
)
from app.market.exchange.models import ExchangeAdapterError
from app.market.features.models import FeatureSnapshot
from app.market.scanner.models import CandidateOpportunity


class RioContextDiagnosticStatus(StrEnum):
    REFRESHED = "REFRESHED"
    CACHE_HIT = "CACHE_HIT"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class RioContextDiagnostic:
    """Read-only operator diagnostic; it never feeds the LLM or Risk Engine."""

    symbol: str
    status: RioContextDiagnosticStatus
    decision_time: datetime
    observed_at: datetime | None = None
    age_seconds: float | None = None
    source: str | None = None
    instrument: str | None = None
    data_quality: str | None = None
    missing_fields: tuple[str, ...] = ()
    last_refresh_status: MarketSidecarRefreshStatus | None = None
    message: str | None = None


class KrakenFuturesRioContextProvider:
    """Refreshable cache projecting public Kraken Futures facts to Rio.

    The same instance can be attached to ``PaperShadowMarketFeed`` as a non-critical
    sidecar refresher and to ``OrchestrationPipeline`` as a synchronous specialist
    context provider. Network I/O is therefore completed before orchestration begins.
    """

    refresher_id = "rio.kraken_futures"

    def __init__(
        self,
        analytics: KrakenFuturesAnalyticsProvider,
        *,
        max_context_age: timedelta = timedelta(minutes=20),
        min_refresh_interval: timedelta = timedelta(minutes=2),
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if max_context_age <= timedelta(0):
            raise ValueError("max_context_age must be > 0")
        if min_refresh_interval < timedelta(0):
            raise ValueError("min_refresh_interval must be >= 0")
        self.analytics = analytics
        self.max_context_age = max_context_age
        self.min_refresh_interval = min_refresh_interval
        self._now = now
        self._snapshots: dict[str, DerivativesPositioningSnapshot] = {}
        self._last_refresh_attempt_at: dict[str, datetime] = {}
        self._last_refresh_result: dict[str, MarketSidecarRefreshResult] = {}

    async def refresh(self, symbol: str) -> DerivativesPositioningSnapshot:
        snapshot = await self.analytics.get_positioning_snapshot(symbol)
        self.update(snapshot)
        return snapshot

    async def refresh_for_market(
        self,
        *,
        symbol: str,
        observed_at: datetime,
    ) -> MarketSidecarRefreshResult:
        """Refresh Rio context without making derivatives availability critical.

        Expected exchange/data errors are converted into ``UNAVAILABLE``. Unexpected
        programming errors are intentionally allowed to escape; the generic feed
        sidecar boundary records them as ``FAILED`` while keeping the spot path alive.
        """

        canonical = _normalize_symbol(symbol)
        decision_time = _as_utc(observed_at)
        now = _as_utc(self._now())

        def complete(
            result: MarketSidecarRefreshResult,
        ) -> MarketSidecarRefreshResult:
            self._last_refresh_result[canonical] = result
            return result

        previous_attempt = self._last_refresh_attempt_at.get(canonical)
        if (
            previous_attempt is not None
            and now >= previous_attempt
            and now - previous_attempt < self.min_refresh_interval
        ):
            cached = self._context_for(canonical, decision_time)
            if cached is not None:
                return complete(
                    MarketSidecarRefreshResult(
                        refresher_id=self.refresher_id,
                        status=MarketSidecarRefreshStatus.CACHED,
                        symbol=canonical,
                        observed_at=cached.observed_at,
                        message="fresh cached Rio context reused inside refresh interval",
                    )
                )
            return complete(
                MarketSidecarRefreshResult(
                    refresher_id=self.refresher_id,
                    status=MarketSidecarRefreshStatus.UNAVAILABLE,
                    symbol=canonical,
                    message="Rio refresh is cooling down and no usable cache exists",
                )
            )

        self._last_refresh_attempt_at[canonical] = now
        try:
            snapshot = await self.refresh(canonical)
        except (ExchangeAdapterError, ValueError) as exc:
            cached = self._context_for(canonical, decision_time)
            if cached is not None:
                return complete(
                    MarketSidecarRefreshResult(
                        refresher_id=self.refresher_id,
                        status=MarketSidecarRefreshStatus.CACHED,
                        symbol=canonical,
                        observed_at=cached.observed_at,
                        message=(
                            f"refresh unavailable ({type(exc).__name__}); "
                            "retained fresh cache"
                        ),
                    )
                )
            return complete(
                MarketSidecarRefreshResult(
                    refresher_id=self.refresher_id,
                    status=MarketSidecarRefreshStatus.UNAVAILABLE,
                    symbol=canonical,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )

        context = self._context_for(canonical, decision_time)
        if context is None:
            return complete(
                MarketSidecarRefreshResult(
                    refresher_id=self.refresher_id,
                    status=MarketSidecarRefreshStatus.UNAVAILABLE,
                    symbol=canonical,
                    observed_at=snapshot.observed_at,
                    message=(
                        "refreshed derivatives snapshot is not usable for this "
                        "decision time"
                    ),
                )
            )
        return complete(
            MarketSidecarRefreshResult(
                refresher_id=self.refresher_id,
                status=MarketSidecarRefreshStatus.REFRESHED,
                symbol=canonical,
                observed_at=context.observed_at,
            )
        )

    def update(self, snapshot: DerivativesPositioningSnapshot) -> None:
        """Atomically replace one symbol cache entry with a normalized real snapshot."""

        canonical = _normalize_symbol(snapshot.symbol)
        current = self._snapshots.get(canonical)
        if current is not None and snapshot.observed_at < current.observed_at:
            return
        self._snapshots[canonical] = snapshot

    def contexts_for(
        self,
        *,
        opportunity: CandidateOpportunity,
        market_context: FeatureSnapshot,
    ) -> dict[str, Any]:
        if opportunity.symbol != market_context.symbol:
            return {}
        context = self._context_for(
            _normalize_symbol(opportunity.symbol),
            _as_utc(market_context.observed_at),
        )
        return {"rio": context} if context is not None else {}

    def diagnostic_for(
        self,
        *,
        symbol: str,
        decision_time: datetime,
    ) -> RioContextDiagnostic:
        """Describe Rio availability without performing I/O or changing agent inputs."""

        canonical = _normalize_symbol(symbol)
        resolved_time = _as_utc(decision_time)
        snapshot = self._snapshots.get(canonical)
        last_result = self._last_refresh_result.get(canonical)
        last_status = None if last_result is None else last_result.status
        message = None if last_result is None else last_result.message

        if snapshot is None or snapshot.observed_at > resolved_time:
            return RioContextDiagnostic(
                symbol=canonical,
                status=RioContextDiagnosticStatus.UNAVAILABLE,
                decision_time=resolved_time,
                last_refresh_status=last_status,
                message=message,
            )

        age = resolved_time - snapshot.observed_at
        context = self._to_rio_context(snapshot)
        base = dict(
            symbol=canonical,
            decision_time=resolved_time,
            observed_at=snapshot.observed_at,
            age_seconds=max(0.0, age.total_seconds()),
            source=snapshot.source,
            instrument=snapshot.instrument,
            data_quality=context.data_quality,
            missing_fields=context.missing_fields,
            last_refresh_status=last_status,
            message=message,
        )
        if age > self.max_context_age:
            return RioContextDiagnostic(
                status=RioContextDiagnosticStatus.STALE,
                **base,
            )
        if not context.usable:
            return RioContextDiagnostic(
                status=RioContextDiagnosticStatus.UNAVAILABLE,
                **base,
            )
        if context.data_quality == "DEGRADED":
            return RioContextDiagnostic(
                status=RioContextDiagnosticStatus.DEGRADED,
                **base,
            )
        if last_status is MarketSidecarRefreshStatus.CACHED:
            status = RioContextDiagnosticStatus.CACHE_HIT
        else:
            status = RioContextDiagnosticStatus.REFRESHED
        return RioContextDiagnostic(status=status, **base)

    def _context_for(self, symbol: str, decision_time: datetime) -> RioContext | None:
        snapshot = self._snapshots.get(_normalize_symbol(symbol))
        if snapshot is None:
            return None
        if snapshot.observed_at > decision_time:
            return None
        if decision_time - snapshot.observed_at > self.max_context_age:
            return None
        context = self._to_rio_context(snapshot)
        return context if context.usable else None

    @staticmethod
    def _to_rio_context(snapshot: DerivativesPositioningSnapshot) -> RioContext:
        core = (
            snapshot.funding_rate,
            snapshot.open_interest,
            snapshot.long_short_ratio,
        )
        present = sum(value is not None for value in core)
        if present == len(core):
            data_quality = "RELIABLE"
        elif snapshot.available_metric_count > 0:
            data_quality = "DEGRADED"
        else:
            data_quality = "INSUFFICIENT"

        return RioContext(
            source=snapshot.source,
            instrument=snapshot.instrument,
            observed_at=snapshot.observed_at,
            is_stale=False,
            data_quality=data_quality,
            funding_rate=_float_or_none(snapshot.funding_rate),
            open_interest=_float_or_none(snapshot.open_interest),
            open_interest_change_pct=_float_or_none(snapshot.open_interest_change_pct),
            long_liquidations_notional=_float_or_none(
                snapshot.long_liquidations_notional
            ),
            short_liquidations_notional=_float_or_none(
                snapshot.short_liquidations_notional
            ),
            long_short_ratio=_float_or_none(snapshot.long_short_ratio),
            missing_fields=snapshot.missing_fields,
        )


def _float_or_none(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized.count("/") != 1:
        raise ValueError("Rio provider symbols must use canonical BASE/QUOTE form")
    base, quote = normalized.split("/", 1)
    if not base or not quote or any(character.isspace() for character in normalized):
        raise ValueError("invalid Rio provider BASE/QUOTE symbol")
    return f"{base}/{quote}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("market observed_at must be timezone-aware")
    return value.astimezone(UTC)
