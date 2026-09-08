from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.backtest import (
    HistoricalExitReason,
    HistoricalTradeProtection,
    IntrabarPolicy,
    resolve_intrabar,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def protection(*, side="LONG", stop="95", targets=("110", "115")):
    return HistoricalTradeProtection(
        symbol="BTC/EUR",
        side=side,
        quantity=Decimal("1"),
        average_entry=Decimal("100"),
        stop_price=Decimal(stop),
        targets=tuple(Decimal(item) for item in targets),
        opened_at=NOW,
        opportunity_id="opp-1",
        proposal_id="proposal-1",
    )


def candle(*, open="100", high="105", low="98", close="102"):
    return {
        "open": Decimal(open),
        "high": Decimal(high),
        "low": Decimal(low),
        "close": Decimal(close),
    }


def test_stop_wins_when_stop_and_target_are_both_touched() -> None:
    resolution = resolve_intrabar(
        protection(),
        candle(high="112", low="94"),
        policy=IntrabarPolicy.STOP_FIRST,
    )

    assert resolution is not None
    assert resolution.reason is HistoricalExitReason.STOP_INTRABAR
    assert resolution.reference_price == Decimal("95")


def test_long_stop_gap_uses_open_as_adverse_reference() -> None:
    resolution = resolve_intrabar(protection(), candle(open="92", high="96", low="90", close="94"))

    assert resolution is not None
    assert resolution.reason is HistoricalExitReason.STOP_GAP
    assert resolution.reference_price == Decimal("92")
    assert resolution.is_gap is True


def test_long_target_gap_is_capped_at_first_target_without_price_improvement() -> None:
    resolution = resolve_intrabar(
        protection(),
        candle(open="120", high="122", low="119", close="121"),
    )

    assert resolution is not None
    assert resolution.reason is HistoricalExitReason.TARGET_GAP
    assert resolution.reference_price == Decimal("110")
    assert resolution.target_price == Decimal("110")


def test_first_target_is_used_when_multiple_targets_are_crossed() -> None:
    resolution = resolve_intrabar(
        protection(targets=("115", "110", "125")),
        candle(high="130", low="99"),
    )

    assert resolution is not None
    assert resolution.reason is HistoricalExitReason.TARGET_INTRABAR
    assert resolution.reference_price == Decimal("110")


def test_short_stop_target_and_gap_rules_are_symmetric() -> None:
    short = protection(side="SHORT", stop="105", targets=("90", "85"))

    stop_first = resolve_intrabar(short, candle(high="106", low="89"))
    target_gap = resolve_intrabar(
        short,
        candle(open="80", high="82", low="78", close="81"),
    )

    assert stop_first is not None
    assert stop_first.reason is HistoricalExitReason.STOP_INTRABAR
    assert stop_first.reference_price == Decimal("105")
    assert target_gap is not None
    assert target_gap.reason is HistoricalExitReason.TARGET_GAP
    assert target_gap.reference_price == Decimal("90")


def test_no_touch_produces_no_exit() -> None:
    assert resolve_intrabar(protection(), candle()) is None


def test_targets_must_be_on_the_favorable_side() -> None:
    bad = SimpleNamespace(
        side="LONG",
        average_entry=Decimal("100"),
        stop_price=Decimal("95"),
        targets=(Decimal("99"),),
    )

    with pytest.raises(ValueError, match="LONG targets"):
        resolve_intrabar(bad, candle())
