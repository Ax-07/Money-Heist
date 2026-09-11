from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Protocol

from app.market.multitimeframe import HistoricalMultiTimeframeCursor

from .models import FeatureSnapshot


class FeatureEngineLike(Protocol):
    config: Any

    def compute(
        self,
        candles: Any,
        *,
        symbol: str,
        timeframe: str,
        source_snapshot_id: str | None = None,
        observed_at: datetime | None = None,
    ) -> Any: ...


def _as_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _snapshot_payload(snapshot: FeatureSnapshot) -> dict[str, Any]:
    return snapshot.model_dump(mode="json")


@dataclass(frozen=True, slots=True)
class MultiTimeframeFeatureContext:
    """Frozen deterministic FeatureSnapshot set available at one decision time."""

    symbol: str
    observed_at: datetime
    decision_timeframe: str
    feature_version: str
    context_version: str
    source_cursor_fingerprint: str
    requested_timeframes: tuple[str, ...]
    snapshots: Mapping[str, FeatureSnapshot]
    missing_timeframes: tuple[str, ...]
    warmup_incomplete_timeframes: tuple[str, ...]
    context_fingerprint: str

    def __post_init__(self) -> None:
        symbol = self.symbol.strip()
        decision = self.decision_timeframe.strip().lower()
        feature_version = self.feature_version.strip()
        context_version = self.context_version.strip()
        source_fingerprint = self.source_cursor_fingerprint.strip().lower()
        requested = tuple(item.strip().lower() for item in self.requested_timeframes)

        if not symbol:
            raise ValueError("symbol must not be empty")
        if not decision:
            raise ValueError("decision_timeframe must not be empty")
        if not feature_version:
            raise ValueError("feature_version must not be empty")
        if not context_version:
            raise ValueError("context_version must not be empty")
        if len(source_fingerprint) != 64 or any(
            char not in "0123456789abcdef" for char in source_fingerprint
        ):
            raise ValueError(
                "source_cursor_fingerprint must be a 64-character hex digest"
            )
        if not requested or len(set(requested)) != len(requested):
            raise ValueError("requested_timeframes must be non-empty and unique")
        if decision not in requested:
            raise ValueError(
                "decision_timeframe must be included in requested_timeframes"
            )

        observed_at = _as_utc(self.observed_at, field="observed_at")
        frozen = MappingProxyType(dict(sorted(self.snapshots.items())))
        snapshot_keys = set(frozen)
        requested_set = set(requested)
        if not snapshot_keys.issubset(requested_set):
            raise ValueError("snapshot timeframes must be requested")
        if any(
            snapshot.symbol != symbol or snapshot.timeframe != timeframe
            for timeframe, snapshot in frozen.items()
        ):
            raise ValueError(
                "all FeatureSnapshots must match context symbol/timeframe"
            )
        if any(snapshot.observed_at != observed_at for snapshot in frozen.values()):
            raise ValueError(
                "all FeatureSnapshots must share context observed_at"
            )
        if any(
            snapshot.feature_version != feature_version
            for snapshot in frozen.values()
        ):
            raise ValueError(
                "all FeatureSnapshots must share context feature_version"
            )

        missing = tuple(item.strip().lower() for item in self.missing_timeframes)
        incomplete = tuple(
            item.strip().lower() for item in self.warmup_incomplete_timeframes
        )
        if set(missing) != requested_set - snapshot_keys:
            raise ValueError(
                "missing_timeframes must exactly match absent snapshots"
            )
        expected_incomplete = {
            timeframe
            for timeframe, snapshot in frozen.items()
            if not snapshot.quality.warmup_complete
        }
        if set(incomplete) != expected_incomplete:
            raise ValueError(
                "warmup_incomplete_timeframes must match snapshot quality"
            )

        digest = self.context_fingerprint.strip().lower()
        if len(digest) != 64 or any(
            char not in "0123456789abcdef" for char in digest
        ):
            raise ValueError(
                "context_fingerprint must be a 64-character hex digest"
            )

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "decision_timeframe", decision)
        object.__setattr__(self, "feature_version", feature_version)
        object.__setattr__(self, "context_version", context_version)
        object.__setattr__(
            self, "source_cursor_fingerprint", source_fingerprint
        )
        object.__setattr__(self, "requested_timeframes", requested)
        object.__setattr__(self, "snapshots", frozen)
        object.__setattr__(self, "missing_timeframes", tuple(sorted(missing)))
        object.__setattr__(
            self,
            "warmup_incomplete_timeframes",
            tuple(sorted(incomplete)),
        )
        object.__setattr__(self, "context_fingerprint", digest)

    @property
    def decision_snapshot(self) -> FeatureSnapshot:
        try:
            return self.snapshots[self.decision_timeframe]
        except KeyError as exc:
            raise ValueError(
                "decision timeframe has no FeatureSnapshot"
            ) from exc

    @property
    def all_timeframes_available(self) -> bool:
        return not self.missing_timeframes

    @property
    def all_warmups_complete(self) -> bool:
        return (
            self.all_timeframes_available
            and not self.warmup_incomplete_timeframes
        )


def build_multi_timeframe_feature_context(
    *,
    feature_engine: FeatureEngineLike,
    mtf_cursor: HistoricalMultiTimeframeCursor,
    observed_at: datetime,
    decision_timeframe: str,
    decision_feature: FeatureSnapshot | None = None,
    context_version: str = "mtf-feature-context-v1",
) -> MultiTimeframeFeatureContext:
    """Build the MTF feature context available at one replay decision.

    Empty higher-timeframe series are represented explicitly as missing.
    Existing but insufficiently warmed series still produce FeatureSnapshots
    carrying ``warmup_complete=False``.
    """

    observed_at = _as_utc(observed_at, field="observed_at")
    decision_timeframe = decision_timeframe.strip().lower()
    context_version = context_version.strip()
    if not context_version:
        raise ValueError("context_version must not be empty")

    state = mtf_cursor.state()
    if state.as_of != observed_at:
        raise ValueError(
            "MTF cursor as_of must equal feature-context observed_at"
        )
    if decision_timeframe not in mtf_cursor.target_timeframes:
        raise ValueError(
            "decision_timeframe must be configured on MTF cursor"
        )

    feature_version = str(
        getattr(feature_engine.config, "feature_version", "")
    ).strip()
    if not feature_version:
        raise ValueError("feature_engine.config.feature_version is required")

    snapshots: dict[str, FeatureSnapshot] = {}
    missing: list[str] = []
    incomplete: list[str] = []

    for timeframe in mtf_cursor.target_timeframes:
        series = mtf_cursor.series(timeframe)
        if not series:
            missing.append(timeframe)
            continue

        if timeframe == decision_timeframe and decision_feature is not None:
            snapshot = decision_feature
            if not isinstance(snapshot, FeatureSnapshot):
                raise TypeError(
                    "decision_feature must be a FeatureSnapshot"
                )
            if snapshot.candle_count != len(series):
                raise ValueError(
                    "decision FeatureSnapshot candle_count does not match cursor"
                )
        else:
            computed = feature_engine.compute(
                series,
                symbol=state.symbol,
                timeframe=timeframe,
                observed_at=observed_at,
            )
            if not isinstance(computed, FeatureSnapshot):
                raise TypeError(
                    "feature_engine must return FeatureSnapshot in MTF context"
                )
            snapshot = computed

        if snapshot.symbol != state.symbol:
            raise ValueError("FeatureSnapshot symbol does not match MTF cursor")
        if snapshot.timeframe != timeframe:
            raise ValueError(
                "FeatureSnapshot timeframe does not match MTF cursor"
            )
        if snapshot.observed_at != observed_at:
            raise ValueError(
                "FeatureSnapshot observed_at does not match MTF context"
            )
        if snapshot.feature_version != feature_version:
            raise ValueError(
                "FeatureSnapshot feature_version does not match FeatureEngine"
            )

        snapshots[timeframe] = snapshot
        if not snapshot.quality.warmup_complete:
            incomplete.append(timeframe)

    if decision_timeframe not in snapshots:
        raise ValueError(
            "decision timeframe must be available in MTF feature context"
        )

    payload = {
        "schema": "money-heist.mtf-feature-context.v1",
        "context_version": context_version,
        "feature_version": feature_version,
        "symbol": state.symbol,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "decision_timeframe": decision_timeframe,
        "source_cursor_fingerprint": state.cursor_fingerprint,
        "requested_timeframes": mtf_cursor.target_timeframes,
        "snapshots": {
            timeframe: _snapshot_payload(snapshot)
            for timeframe, snapshot in sorted(snapshots.items())
        },
        "missing_timeframes": tuple(sorted(missing)),
        "warmup_incomplete_timeframes": tuple(sorted(incomplete)),
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()

    return MultiTimeframeFeatureContext(
        symbol=state.symbol,
        observed_at=observed_at,
        decision_timeframe=decision_timeframe,
        feature_version=feature_version,
        context_version=context_version,
        source_cursor_fingerprint=state.cursor_fingerprint,
        requested_timeframes=mtf_cursor.target_timeframes,
        snapshots=snapshots,
        missing_timeframes=tuple(sorted(missing)),
        warmup_incomplete_timeframes=tuple(sorted(incomplete)),
        context_fingerprint=digest,
    )
