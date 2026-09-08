from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from .models import IntrabarPolicy

ZERO = Decimal("0")


class HistoricalExitReason(StrEnum):
    STOP_GAP = "STOP_GAP"
    TARGET_GAP = "TARGET_GAP"
    STOP_INTRABAR = "STOP_INTRABAR"
    TARGET_INTRABAR = "TARGET_INTRABAR"


@dataclass(frozen=True, slots=True)
class IntrabarResolution:
    reason: HistoricalExitReason
    reference_price: Decimal
    target_price: Decimal | None = None

    @property
    def is_gap(self) -> bool:
        return self.reason in {
            HistoricalExitReason.STOP_GAP,
            HistoricalExitReason.TARGET_GAP,
        }


def _decimal(value: Any, *, field_name: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not number.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return number


def _first_target(protection: Any) -> Decimal | None:
    entry = _decimal(protection.average_entry, field_name="average_entry")
    side = str(getattr(protection, "side", "")).upper()
    targets = tuple(_decimal(value, field_name="target") for value in protection.targets)
    if not targets:
        return None
    if any(target <= ZERO for target in targets):
        raise ValueError("targets must be > 0")

    if side == "LONG":
        favorable = [target for target in targets if target > entry]
        if len(favorable) != len(targets):
            raise ValueError("LONG targets must be above average_entry")
        return min(favorable)
    if side == "SHORT":
        favorable = [target for target in targets if target < entry]
        if len(favorable) != len(targets):
            raise ValueError("SHORT targets must be below average_entry")
        return max(favorable)
    raise ValueError("historical protection side must be LONG or SHORT")


def resolve_intrabar(
    protection: Any,
    row: dict[str, Any],
    *,
    policy: IntrabarPolicy = IntrabarPolicy.STOP_FIRST,
) -> IntrabarResolution | None:
    """Resolve one protected position against one fully known historical candle.

    The function is pure and deterministic. It never invents an OHLC path. A gap
    beyond a stop exits from the candle open; a favorable gap beyond a target is
    capped at the target price. When stop and target are both touched and lower
    timeframe ordering is unavailable, STOP_FIRST chooses the adverse outcome.
    """

    if policy is not IntrabarPolicy.STOP_FIRST:
        raise ValueError(f"unsupported intrabar policy: {policy}")

    open_price = _decimal(row["open"], field_name="open")
    high = _decimal(row["high"], field_name="high")
    low = _decimal(row["low"], field_name="low")
    close = _decimal(row["close"], field_name="close")
    if min(open_price, high, low, close) <= ZERO:
        raise ValueError("historical OHLC prices must be > 0")
    if high < max(open_price, close, low):
        raise ValueError("candle high is inconsistent with OHLC")
    if low > min(open_price, close, high):
        raise ValueError("candle low is inconsistent with OHLC")

    stop = _decimal(protection.stop_price, field_name="stop_price")
    if stop <= ZERO:
        raise ValueError("stop_price must be > 0")
    target = _first_target(protection)
    side = str(getattr(protection, "side", "")).upper()

    if side == "LONG":
        if open_price <= stop:
            return IntrabarResolution(HistoricalExitReason.STOP_GAP, open_price)
        if target is not None and open_price >= target:
            return IntrabarResolution(
                HistoricalExitReason.TARGET_GAP,
                target,
                target_price=target,
            )
        stop_touched = low <= stop
        target_touched = target is not None and high >= target
    elif side == "SHORT":
        if open_price >= stop:
            return IntrabarResolution(HistoricalExitReason.STOP_GAP, open_price)
        if target is not None and open_price <= target:
            return IntrabarResolution(
                HistoricalExitReason.TARGET_GAP,
                target,
                target_price=target,
            )
        stop_touched = high >= stop
        target_touched = target is not None and low <= target
    else:
        raise ValueError("historical protection side must be LONG or SHORT")

    if stop_touched:
        return IntrabarResolution(HistoricalExitReason.STOP_INTRABAR, stop)
    if target_touched and target is not None:
        return IntrabarResolution(
            HistoricalExitReason.TARGET_INTRABAR,
            target,
            target_price=target,
        )
    return None


__all__ = [
    "HistoricalExitReason",
    "IntrabarResolution",
    "resolve_intrabar",
]
