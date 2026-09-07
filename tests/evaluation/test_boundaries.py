from pathlib import Path


def test_evaluation_package_contains_no_live_broker_or_exchange_execution() -> None:
    root = Path(__file__).parents[2] / "app" / "evaluation"
    content = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "LiveBroker" not in content
    assert "submit_live" not in content
    assert "execute_arbitrary_exchange_request" not in content
    assert "from app.trading.risk" not in content
    assert "import app.trading.risk" not in content
    assert "from app.trading.paper.broker" not in content


def test_existing_paper_pipeline_does_not_depend_on_evaluation() -> None:
    pipeline = Path(__file__).parents[2] / "app" / "services" / "paper_pipeline" / "pipeline.py"
    if not pipeline.exists():
        return
    content = pipeline.read_text(encoding="utf-8")
    assert "app.evaluation" not in content
    assert "from app import evaluation" not in content


def test_evaluation_error_does_not_destroy_rebuildable_trading_source() -> None:
    from datetime import datetime, timezone
    from decimal import Decimal

    import pytest

    from app.evaluation import EvaluationService, ExecutionRecord, calculate_trading_metrics
    from app.evaluation.models import EvaluationSource

    class ExplodingLisbon:
        def build(self, **_kwargs):
            raise RuntimeError("evaluation reporter unavailable")

    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    source = EvaluationSource(
        executions=(
            ExecutionRecord(
                fill_id="f1",
                broker_order_id="o1",
                system_id="balanced_v1",
                symbol="BTCUSDT",
                side="BUY",
                order_type="MARKET",
                quantity=Decimal("1"),
                price=Decimal("100"),
                fee=Decimal("0"),
                filled_at=now,
                slippage_cost=Decimal("0"),
            ),
        ),
        marks={"BTCUSDT": Decimal("110")},
    )

    with pytest.raises(RuntimeError, match="evaluation reporter unavailable"):
        EvaluationService(lisbon=ExplodingLisbon()).evaluate(source)

    rebuilt = calculate_trading_metrics(source.executions, marks=source.marks)
    assert rebuilt.open_position_count == 1
    assert rebuilt.unrealized_pnl.value == Decimal("10")
