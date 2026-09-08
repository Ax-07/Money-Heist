from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_backtest_dashboard_backend_has_no_live_trading_dependency() -> None:
    paths = (
        ROOT / "app/dashboard/backtest.py",
        ROOT / "app/api/routes/backtest_dashboard.py",
    )
    forbidden = (
        "app.trading.live",
        "KrakenSpotLiveBroker",
        "ControlledLiveExecutionService",
        "submit_live_order",
        "private_order",
    )
    for path in paths:
        content = path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in content, f"{path} contains forbidden LIVE marker {marker}"


def test_backtest_frontend_does_not_collect_secrets() -> None:
    html = (ROOT / "app/dashboard/static/backtest.html").read_text(encoding="utf-8")
    js = (ROOT / "app/dashboard/static/backtest.js").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in html
    assert 'type="password"' not in html
    assert "api_key" not in js.lower()
    assert "openai_api_key" not in js.lower()
