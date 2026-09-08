from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.services.backtest import closed_trades_to_csv, equity_curve_to_csv

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_equity_csv_is_chronologically_sorted() -> None:
    points = (
        SimpleNamespace(
            observed_at=NOW + timedelta(minutes=5),
            equity=Decimal("101"),
            data_kind="PAPER_EXECUTED",
        ),
        SimpleNamespace(
            observed_at=NOW,
            equity=Decimal("100"),
            data_kind="PAPER_EXECUTED",
        ),
    )
    payload = equity_curve_to_csv(points)
    lines = payload.splitlines()

    assert lines[0] == "observed_at,equity,data_kind"
    assert lines[1].startswith(NOW.isoformat())
    assert lines[2].startswith((NOW + timedelta(minutes=5)).isoformat())


def test_closed_trade_csv_is_stable() -> None:
    def trade(trade_id: str, minute: int):
        return SimpleNamespace(
            trade_id=trade_id,
            system_id="balanced_v1",
            symbol="BTC/EUR",
            side="LONG",
            quantity=Decimal("0.5"),
            entry_price=Decimal("100"),
            exit_price=Decimal("110"),
            opened_at=NOW,
            closed_at=NOW + timedelta(minutes=minute),
            net_pnl=Decimal("4.8"),
            fees=Decimal("0.2"),
            slippage_cost=Decimal("0.05"),
        )

    report = SimpleNamespace(
        trading=SimpleNamespace(closed_trades=(trade("b", 10), trade("a", 5)))
    )
    first = closed_trades_to_csv(report)
    second = closed_trades_to_csv(report)

    assert first == second
    assert first.splitlines()[1].startswith("a,")


def test_manifest_json_is_canonical_and_repeatable() -> None:
    from app.services.backtest import BacktestRunManifest, manifest_to_json

    manifest = BacktestRunManifest(
        schema_version="money-heist.backtest-manifest.v1",
        run_id="run-1",
        dataset_id="dataset-1",
        dataset_version="sha256:" + "a" * 64,
        period_start=NOW,
        period_end=NOW + timedelta(hours=1),
        ai_mode="CACHED",
        code_version="git:8db98a4",
        execution_model_version="historical-ohlc-v1",
        random_seed=42,
        business_sha256="b" * 64,
        evaluation_report_version="batch10.evaluation.v1",
    )

    first = manifest_to_json(manifest)
    second = manifest_to_json(manifest)
    assert first == second
    assert '"random_seed":42' in first
    assert '"code_version":"git:8db98a4"' in first
