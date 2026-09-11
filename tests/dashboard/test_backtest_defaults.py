from __future__ import annotations

from pathlib import Path


def test_btc_usdc_h1_is_the_default_dataset_identity() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "app/dashboard/static/backtest.html").read_text(encoding="utf-8")

    assert 'id="symbol" value="BTC/USDC"' in html
    assert '<option selected>1h</option>' in html
    assert 'id="source" value="binance_spot_csv"' in html


def test_btc_usdc_binance_spot_order_constraints_are_prefilled() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "app/dashboard/static/backtest.html").read_text(encoding="utf-8")

    assert 'id="qty-step" type="number" step="any" value="0.00001"' in html
    assert 'id="min-qty" type="number" step="any" value="0.00001"' in html
    assert 'id="min-notional" type="number" step="any" value="5"' in html
    assert 'id="max-qty" type="number" step="any" value="9000"' in html
    assert 'id="market-leverage" type="number" step="0.1" value="1"' in html
    assert 'id="min-notional-unit">USDC<' in html


def test_filename_detection_and_market_preset_are_present() -> None:
    root = Path(__file__).resolve().parents[2]
    js = (root / "app/dashboard/static/backtest.js").read_text(encoding="utf-8")

    assert "const MARKET_PRESETS" in js
    assert '"BTC/USDC"' in js
    assert "BTCUSDC" in js
    assert "BTC_USDC" in js
    assert "H1" in js
    assert "1H" in js
    assert "60M" in js
    assert "applyDatasetDefaultsFromFile" in js
    assert "applyMarketPreset" in js


def test_single_quick_test_button_configures_all_three_periods() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "app/dashboard/static/backtest.html").read_text(encoding="utf-8")
    js = (root / "app/dashboard/static/backtest.js").read_text(encoding="utf-8")

    assert html.count('id="split-quick-test"') == 1
    assert ">Test rapide<" in html
    assert "function applyQuickTestSplit()" in js
    assert "const warmupBars = 35" in js
    assert "const targetTestBars = 100" in js
    assert "Math.min(targetTestBars, available - start)" in js
    assert "Math.floor(testBars * 0.60)" in js
    assert "Math.floor(testBars * 0.80)" in js
    assert "designEnd: start + designBars - 1" in js
    assert "validationEnd: start + validationBoundaryBars - 1" in js
    assert "end: start + testBars - 1" in js
    assert '$("split-quick-test").addEventListener("click"' in js


def test_dataset_defaults_do_not_add_secrets_or_live_execution() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "app/dashboard/static/backtest.html").read_text(encoding="utf-8")
    js = (root / "app/dashboard/static/backtest.js").read_text(encoding="utf-8")

    assert "api_key" not in js.lower()
    assert 'type="password"' not in html.lower()
    assert "live broker" not in js.lower()
    assert "live broker" not in html.lower()


def test_ai_mode_presets_are_safe_and_prefilled() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "app/dashboard/static/backtest.html").read_text(encoding="utf-8")
    js = (root / "app/dashboard/static/backtest.js").read_text(encoding="utf-8")

    # Safety invariant: opening the dashboard must not arm paid LIVE_EVAL.
    assert '<option selected>MOCK</option>' in html

    # Mode changes deterministically switch the whole AI pricing preset.
    assert "const AI_MODE_PRESETS" in js
    assert "function applyAIModePreset(mode)" in js
    assert 'applyAIModePreset(mode);' in js

    # MOCK remains free/deterministic from the dashboard accounting perspective.
    assert 'budget: "1"' in js
    assert 'modelId: "mock-backtest-v1"' in js
    assert 'inputPrice: "0"' in js
    assert 'outputPrice: "0"' in js

    # CACHED / LIVE_EVAL use the Luna preset shown to the operator.
    assert js.count('modelId: "gpt-5.6-luna"') == 2
    assert js.count('budget: "0.25"') == 2
    assert js.count('inputPrice: "0.20"') == 2
    assert js.count('outputPrice: "1.20"') == 2
    assert js.count('cachedPrice: "0.02"') == 2


def test_historical_rio_controls_are_explicit_and_off_by_default() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "app/dashboard/static/backtest.html").read_text(
        encoding="utf-8"
    )
    js = (root / "app/dashboard/static/backtest.js").read_text(
        encoding="utf-8"
    )

    assert 'id="derivatives-enabled" type="checkbox"' in html
    assert 'id="derivatives-file" type="file"' in html
    assert 'id="derivatives-max-age"' in html
    assert 'value="7200"' in html
    assert 'id="derivatives-enabled" type="checkbox" checked' not in html

    assert 'let derivativesCsvText = "";' in js
    assert "function derivativesPayload()" in js
    assert "derivatives: derivativesPayload()" in js
    assert '["1m", "5m", "15m"]' in js
    assert '$("derivatives-enabled").checked' in js
