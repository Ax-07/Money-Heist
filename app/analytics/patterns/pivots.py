from __future__ import annotations

from collections.abc import Sequence

from app.analytics.structure import StructureSource
from app.analytics.zigzag.models import CausalZigZagPivot

from .models import PatternPivot


def pattern_pivots_from_causal_zigzag(
    pivots: Sequence[CausalZigZagPivot],
) -> tuple[PatternPivot, ...]:
    return tuple(
        PatternPivot(
            pivot_id=pivot.pivot_id,
            kind=pivot.kind.value,
            price=pivot.price,
            pivot_at=pivot.pivot_at,
            confirmed_at=pivot.confirmed_at,
            symbol=pivot.symbol,
            timeframe=pivot.timeframe,
            source=StructureSource.CAUSAL_ZIGZAG,
            source_fingerprint=pivot.pivot_fingerprint,
            source_cursor_fingerprint=pivot.source_cursor_fingerprint,
            atr_at_pivot=pivot.atr_at_pivot,
            candle_index=pivot.candle_index,
            confirmed_index=pivot.confirmed_index,
        )
        for pivot in pivots
    )
