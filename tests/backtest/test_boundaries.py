from __future__ import annotations

from pathlib import Path

import app.services.backtest as backtest


def test_backtest_package_has_no_live_execution_dependency() -> None:
    root = Path(backtest.__file__).parent
    content = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = (
        "app.trading.live",
        "KrakenSpotLiveBroker",
        "ControlledLiveExecutionService",
        "submit_live",
        "private_order",
    )

    for token in forbidden:
        assert token not in content
