from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.market.features import FeatureEngine
from app.market.models import Candle
from app.market.multitimeframe import resample_closed_candles
from app.market.scanner.service import ScannerConfig
from app.services.frontend_v2.decision_intelligence import (
    FrontendDecisionIntelligenceBundle,
    PeriodRole,
)

FRONTEND_DECISION_CHART_SCHEMA_VERSION = "money-heist.frontend-decision-chart.v1"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FrontendDecisionChartCandle(FrozenModel):
    time: int
    open_time: datetime
    close_time: datetime
    open: str
    high: str
    low: str
    close: str
    volume: str
    is_closed: bool = True


class FrontendDecisionIndicatorPoint(FrozenModel):
    time: int
    observed_at: datetime
    snapshot_id: str
    candle_count: int = Field(ge=1)
    warmup_complete: bool
    ema_fast: float | None = None
    ema_slow: float | None = None
    ema_spread_pct: float | None = None
    rsi_14: float | None = None
    macd_line: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    atr_14: float | None = None
    atr_pct: float | None = None
    atr_expansion_ratio: float | None = None
    adx_14: float | None = None
    bollinger_mid: float | None = None
    bollinger_upper: float | None = None
    bollinger_lower: float | None = None
    bollinger_width_pct: float | None = None
    bollinger_position: float | None = None
    volume_sma_20: float | None = None
    volume_ratio: float | None = None
    realized_volatility_20_pct: float | None = None
    prior_range_high_20: float | None = None
    prior_range_low_20: float | None = None
    distance_to_range_high_pct: float | None = None
    distance_to_range_low_pct: float | None = None
    regime: str


class FrontendScannerThresholds(FrozenModel):
    candidate_score: int = Field(ge=0, le=100)
    range_break_buffer_pct: float
    volume_expansion_ratio: float
    volatility_expansion_ratio: float
    trend_adx_threshold: float
    trend_ema_spread_pct: float
    momentum_high_rsi: float
    momentum_low_rsi: float


class FrontendDecisionChartProjection(FrozenModel):
    schema_version: Literal["money-heist.frontend-decision-chart.v1"] = (
        FRONTEND_DECISION_CHART_SCHEMA_VERSION
    )
    campaign_id: str
    role: PeriodRole
    symbol: str
    source_timeframe: str
    decision_timeframe: str
    feature_version: str
    projection_source: Literal["RECONSTRUCTED_CANONICAL_FEATURE_ENGINE"] = (
        "RECONSTRUCTED_CANONICAL_FEATURE_ENGINE"
    )
    snapshot_identity_verified: bool = True
    direct_scanner_features: tuple[str, ...]
    scanner_thresholds: FrontendScannerThresholds
    candles: tuple[FrontendDecisionChartCandle, ...]
    indicators: tuple[FrontendDecisionIndicatorPoint, ...]

    def to_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


class DecisionChartUnavailableError(ValueError):
    pass


class DecisionChartArtifactStore(Protocol):
    def persisted_export(self, campaign_id: str, name: str) -> str | None: ...

    def persist_export(self, campaign_id: str, name: str, payload: str) -> None: ...


def decision_chart_export_name(role: PeriodRole) -> str:
    return f"frontend-decision-chart-{role.lower()}.json"


def _candle_projection(candle: Candle) -> FrontendDecisionChartCandle:
    return FrontendDecisionChartCandle(
        time=int(candle.close_time.timestamp()),
        open_time=candle.open_time,
        close_time=candle.close_time,
        open=str(candle.open),
        high=str(candle.high),
        low=str(candle.low),
        close=str(candle.close),
        volume=str(candle.volume),
        is_closed=candle.is_closed,
    )


def _indicator_projection(snapshot: Any) -> FrontendDecisionIndicatorPoint:
    return FrontendDecisionIndicatorPoint(
        time=int(snapshot.observed_at.timestamp()),
        observed_at=snapshot.observed_at,
        snapshot_id=str(snapshot.snapshot_id),
        candle_count=int(snapshot.candle_count),
        warmup_complete=bool(snapshot.quality.warmup_complete),
        ema_fast=snapshot.ema_fast,
        ema_slow=snapshot.ema_slow,
        ema_spread_pct=snapshot.ema_spread_pct,
        rsi_14=snapshot.rsi_14,
        macd_line=snapshot.macd_line,
        macd_signal=snapshot.macd_signal,
        macd_histogram=snapshot.macd_histogram,
        atr_14=snapshot.atr_14,
        atr_pct=snapshot.atr_pct,
        atr_expansion_ratio=snapshot.atr_expansion_ratio,
        adx_14=snapshot.adx_14,
        bollinger_mid=snapshot.bollinger_mid,
        bollinger_upper=snapshot.bollinger_upper,
        bollinger_lower=snapshot.bollinger_lower,
        bollinger_width_pct=snapshot.bollinger_width_pct,
        bollinger_position=snapshot.bollinger_position,
        volume_sma_20=snapshot.volume_sma_20,
        volume_ratio=snapshot.volume_ratio,
        realized_volatility_20_pct=snapshot.realized_volatility_20_pct,
        prior_range_high_20=snapshot.prior_range_high_20,
        prior_range_low_20=snapshot.prior_range_low_20,
        distance_to_range_high_pct=snapshot.distance_to_range_high_pct,
        distance_to_range_low_pct=snapshot.distance_to_range_low_pct,
        regime=str(getattr(snapshot.regime, "value", snapshot.regime)),
    )


def _decision_candles(
    *,
    source_candles: Sequence[Candle],
    source_timeframe: str,
    decision_timeframe: str,
    period_end: datetime,
) -> tuple[Candle, ...]:
    ordered = tuple(
        sorted(
            (
                candle
                for candle in source_candles
                if candle.is_closed and candle.close_time <= period_end
            ),
            key=lambda candle: candle.close_time,
        )
    )
    if not ordered:
        raise DecisionChartUnavailableError("DECISION_CHART_SOURCE_CANDLES_UNAVAILABLE")
    if any(candle.timeframe != source_timeframe for candle in ordered):
        raise DecisionChartUnavailableError("DECISION_CHART_SOURCE_TIMEFRAME_MISMATCH")
    if decision_timeframe == source_timeframe:
        return ordered
    return resample_closed_candles(
        ordered,
        target_timeframe=decision_timeframe,
        as_of=period_end,
    )


def build_frontend_decision_chart_projection(
    *,
    campaign_id: str,
    role: PeriodRole,
    bundle: FrontendDecisionIntelligenceBundle,
    source_candles: Sequence[Candle],
) -> FrontendDecisionChartProjection:
    if bundle.campaign_id != campaign_id or bundle.role != role:
        raise DecisionChartUnavailableError("DECISION_CHART_BUNDLE_IDENTITY_MISMATCH")
    if not bundle.analytics.analytics_available or bundle.analytics.run is None:
        raise DecisionChartUnavailableError("DECISION_CHART_ANALYTICS_UNAVAILABLE")
    if not bundle.scanner.analytics_available:
        raise DecisionChartUnavailableError("DECISION_CHART_SCANNER_PROJECTION_UNAVAILABLE")

    run = bundle.analytics.run
    source_timeframe = run.source_timeframe.strip().lower()
    decision_timeframe = run.decision_timeframe.strip().lower()
    symbol = run.symbol
    if not source_timeframe or not decision_timeframe:
        raise DecisionChartUnavailableError("DECISION_CHART_TIMEFRAME_UNAVAILABLE")
    if any(candle.symbol != symbol for candle in source_candles):
        raise DecisionChartUnavailableError("DECISION_CHART_SYMBOL_MISMATCH")

    decision_candles = _decision_candles(
        source_candles=source_candles,
        source_timeframe=source_timeframe,
        decision_timeframe=decision_timeframe,
        period_end=run.period_end,
    )
    role_candles = tuple(
        candle
        for candle in decision_candles
        if run.period_start <= candle.close_time <= run.period_end
    )

    records_by_time = {record.observed_at: record for record in bundle.scanner.records}
    if len(records_by_time) != len(bundle.scanner.records):
        raise DecisionChartUnavailableError("DECISION_CHART_DUPLICATE_SCANNER_TIMESTAMP")
    if any(
        record.symbol != symbol or record.decision_timeframe != decision_timeframe
        for record in bundle.scanner.records
    ):
        raise DecisionChartUnavailableError("DECISION_CHART_SCANNER_IDENTITY_MISMATCH")

    feature_engine = FeatureEngine()
    visible: list[Candle] = []
    indicators: list[FrontendDecisionIndicatorPoint] = []
    consumed: set[datetime] = set()
    for candle in decision_candles:
        visible.append(candle)
        record = records_by_time.get(candle.close_time)
        if record is None:
            continue
        snapshot = feature_engine.compute(
            tuple(visible),
            symbol=symbol,
            timeframe=decision_timeframe,
            observed_at=candle.close_time,
        )
        if str(snapshot.snapshot_id) != record.scanner_evaluation_id:
            raise DecisionChartUnavailableError(
                "DECISION_CHART_FEATURE_SNAPSHOT_ID_MISMATCH"
            )
        if run.period_start <= candle.close_time <= run.period_end:
            indicators.append(_indicator_projection(snapshot))
        consumed.add(candle.close_time)

    missing = tuple(sorted(set(records_by_time) - consumed))
    if missing:
        raise DecisionChartUnavailableError(
            "DECISION_CHART_SCANNER_TIMESTAMP_NOT_IN_DECISION_SERIES"
        )

    scanner = ScannerConfig()
    return FrontendDecisionChartProjection(
        campaign_id=campaign_id,
        role=role,
        symbol=symbol,
        source_timeframe=source_timeframe,
        decision_timeframe=decision_timeframe,
        feature_version=feature_engine.config.feature_version,
        direct_scanner_features=(
            "prior_range_high_20",
            "prior_range_low_20",
            "distance_to_range_high_pct",
            "distance_to_range_low_pct",
            "volume_ratio",
            "atr_expansion_ratio",
            "adx_14",
            "ema_spread_pct",
            "rsi_14",
            "regime",
        ),
        scanner_thresholds=FrontendScannerThresholds(
            candidate_score=scanner.min_priority_score,
            range_break_buffer_pct=scanner.range_break_buffer_pct,
            volume_expansion_ratio=scanner.volume_expansion_ratio,
            volatility_expansion_ratio=scanner.volatility_expansion_ratio,
            trend_adx_threshold=scanner.trend_adx_threshold,
            trend_ema_spread_pct=scanner.trend_ema_spread_pct,
            momentum_high_rsi=scanner.momentum_high_rsi,
            momentum_low_rsi=scanner.momentum_low_rsi,
        ),
        candles=tuple(_candle_projection(candle) for candle in role_candles),
        indicators=tuple(indicators),
    )


class FrontendDecisionChartProjectionService:
    def __init__(self, store: DecisionChartArtifactStore) -> None:
        self._store = store

    def load(
        self,
        campaign_id: str,
        role: PeriodRole,
    ) -> FrontendDecisionChartProjection | None:
        payload = self._store.persisted_export(
            campaign_id,
            decision_chart_export_name(role),
        )
        if payload is None:
            return None
        projection = FrontendDecisionChartProjection.model_validate_json(payload)
        if projection.campaign_id != campaign_id or projection.role != role:
            raise ValueError("persisted Decision Chart projection identity mismatch")
        return projection

    def persist(self, projection: FrontendDecisionChartProjection) -> None:
        self._store.persist_export(
            projection.campaign_id,
            decision_chart_export_name(projection.role),
            projection.to_json(),
        )


__all__ = [
    "DecisionChartUnavailableError",
    "FrontendDecisionChartProjection",
    "FrontendDecisionChartProjectionService",
    "build_frontend_decision_chart_projection",
    "decision_chart_export_name",
]
