from __future__ import annotations

from pathlib import Path


def test_dashboard_exposes_duration_preset_buttons() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "app/dashboard/static/backtest.html").read_text(encoding="utf-8")

    assert html.count('id="split-1-month"') == 1
    assert html.count('id="split-3-months"') == 1
    assert html.count('id="split-1-year"') == 1
    assert ">1 mois<" in html
    assert ">3 mois<" in html
    assert ">1 an<" in html


def test_duration_presets_use_time_axis_and_keep_60_20_20_split() -> None:
    root = Path(__file__).resolve().parents[2]
    js = (root / "app/dashboard/static/backtest.js").read_text(encoding="utf-8")

    assert "function applyDurationSplit(durationDays, label)" in js
    assert "const warmupBars = 35" in js
    assert "durationDays * 24 * 60 * 60 * 1000" in js
    assert "Number(axis[end + 1]) <= targetEndMs" in js
    assert "Math.floor(testBars * 0.60)" in js
    assert "Math.floor(testBars * 0.80)" in js
    assert '["split-1-month", 30, "1 mois"]' in js
    assert '["split-3-months", 90, "3 mois"]' in js
    assert '["split-1-year", 365, "1 an"]' in js
    assert "mockAgentCoverage = false" in js
