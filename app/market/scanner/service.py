from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from app.market.features import FeatureSnapshot, MarketRegime

from .models import CandidateOpportunity, ScanResult, ScannerTrigger


@dataclass(frozen=True, slots=True)
class ScannerConfig:
    scanner_version: str = "scanner-v1"
    min_priority_score: int = 35
    opportunity_ttl_seconds: int = 900

    range_break_buffer_pct: float = 0.05
    volume_expansion_ratio: float = 1.8
    volatility_expansion_ratio: float = 1.35
    trend_adx_threshold: float = 25.0
    trend_ema_spread_pct: float = 0.15
    momentum_high_rsi: float = 70.0
    momentum_low_rsi: float = 30.0

    weights: dict[ScannerTrigger, int] = field(
        default_factory=lambda: {
            ScannerTrigger.RANGE_BREAK: 35,
            ScannerTrigger.VOLUME_EXPANSION: 20,
            ScannerTrigger.VOLATILITY_EXPANSION: 20,
            ScannerTrigger.TREND_STRENGTH: 15,
            ScannerTrigger.MOMENTUM_EXTREME: 10,
            ScannerTrigger.REGIME_CHANGE: 15,
        }
    )

    def __post_init__(self) -> None:
        if not 0 <= self.min_priority_score <= 100:
            raise ValueError("min_priority_score must be between 0 and 100")
        if self.opportunity_ttl_seconds <= 0:
            raise ValueError("opportunity_ttl_seconds must be greater than zero")
        if any(weight < 0 for weight in self.weights.values()):
            raise ValueError("scanner weights cannot be negative")


class DeterministicScanner:
    """Score deterministic market events without producing a trade direction."""

    def __init__(self, config: ScannerConfig | None = None) -> None:
        self.config = config or ScannerConfig()

    def scan(
        self,
        current: FeatureSnapshot,
        *,
        system_id: str,
        previous: FeatureSnapshot | None = None,
    ) -> ScanResult:
        triggers = self._detect_triggers(current, previous)
        score = min(100, sum(self.config.weights.get(trigger, 0) for trigger in triggers))

        opportunity = None
        if score >= self.config.min_priority_score and triggers:
            opportunity = CandidateOpportunity(
                scanner_version=self.config.scanner_version,
                opportunity_id=self._opportunity_id(current, system_id, triggers),
                snapshot_id=current.snapshot_id,
                system_id=system_id,
                symbol=current.symbol,
                timeframe=current.timeframe,
                priority_score=score,
                triggers=triggers,
                created_at=current.observed_at,
                expires_at=current.observed_at
                + timedelta(seconds=self.config.opportunity_ttl_seconds),
            )
        return ScanResult(score=score, triggers=triggers, opportunity=opportunity)

    def _detect_triggers(
        self, current: FeatureSnapshot, previous: FeatureSnapshot | None
    ) -> tuple[ScannerTrigger, ...]:
        found: list[ScannerTrigger] = []

        if self._range_break(current):
            found.append(ScannerTrigger.RANGE_BREAK)
        if (
            current.volume_ratio is not None
            and current.volume_ratio >= self.config.volume_expansion_ratio
        ):
            found.append(ScannerTrigger.VOLUME_EXPANSION)
        if (
            current.atr_expansion_ratio is not None
            and current.atr_expansion_ratio >= self.config.volatility_expansion_ratio
        ):
            found.append(ScannerTrigger.VOLATILITY_EXPANSION)
        if (
            current.adx_14 is not None
            and current.ema_spread_pct is not None
            and current.adx_14 >= self.config.trend_adx_threshold
            and abs(current.ema_spread_pct) >= self.config.trend_ema_spread_pct
        ):
            found.append(ScannerTrigger.TREND_STRENGTH)
        if (
            current.rsi_14 is not None
            and (
                current.rsi_14 >= self.config.momentum_high_rsi
                or current.rsi_14 <= self.config.momentum_low_rsi
            )
        ):
            found.append(ScannerTrigger.MOMENTUM_EXTREME)
        if self._regime_change(current, previous):
            found.append(ScannerTrigger.REGIME_CHANGE)

        return tuple(found)

    def _range_break(self, current: FeatureSnapshot) -> bool:
        upper_distance = current.distance_to_range_high_pct
        lower_distance = current.distance_to_range_low_pct
        buffer_pct = self.config.range_break_buffer_pct
        if upper_distance is not None and upper_distance >= buffer_pct:
            return True
        if lower_distance is not None and lower_distance <= -buffer_pct:
            return True
        return False

    @staticmethod
    def _regime_change(
        current: FeatureSnapshot, previous: FeatureSnapshot | None
    ) -> bool:
        if previous is None:
            return False
        if current.symbol != previous.symbol or current.timeframe != previous.timeframe:
            return False
        if MarketRegime.UNKNOWN in (current.regime, previous.regime):
            return False
        return current.regime != previous.regime

    def _opportunity_id(
        self,
        current: FeatureSnapshot,
        system_id: str,
        triggers: tuple[ScannerTrigger, ...],
    ) -> str:
        trigger_key = ",".join(trigger.value for trigger in triggers)
        key = (
            f"money-heist:{self.config.scanner_version}:{system_id}:"
            f"{current.snapshot_id}:{trigger_key}"
        )
        return str(uuid5(NAMESPACE_URL, key))
