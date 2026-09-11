from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "run_advanced_specialist_smokes.py"


def load_module():
    spec = importlib.util.spec_from_file_location("advanced_agent_smokes", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quick_split_matches_dashboard_smoke_window() -> None:
    module = load_module()
    assert module.quick_split_indices(1000) == (35, 94, 114, 134)


def test_quick_split_uses_short_dataset_after_warmup() -> None:
    module = load_module()
    start, design_end, validation_end, end = module.quick_split_indices(85)
    assert start == 35
    assert end == 84
    assert design_end == 64
    assert validation_end == 74


def test_kraken_smoke_maps_btc_usdc_to_read_only_btc_futures_proxy() -> None:
    module = load_module()
    config = module.kraken_config_for_symbol("BTC/USDC")
    assert config.instrument_for("BTC/USDC") == "PF_XBTUSD"


def test_denver_smoke_keeps_strict_attribution_and_uses_one_grounded_observation() -> (
    None
):
    module = load_module()
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "observations_from_historical_replay(" in source
    assert "cannot be attributed to exactly one setup entry" in source
    assert "attempt_ambiguous += 1" in source
    assert "HistoricalSetupStatsCatalog((observation,))" in source
    assert "catalog_from_historical_runs" not in source
    assert "candidates[0]" not in source


def test_denver_v3_progressively_expands_real_replay_windows() -> None:
    module = load_module()
    assert module.denver_attempt_sizes(1000) == (100, 200, 400, 800, 965)
    assert module.denver_attempt_sizes(435) == (100, 200, 400)
    assert module.denver_attempt_sizes(85) == (50,)


def test_denver_v3_keeps_fail_closed_attribution_and_rio_can_run_independently() -> (
    None
):
    module = load_module()
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "observations_from_historical_replay(" in source
    assert "cannot be attributed to exactly one setup entry" in source
    assert "attempt_ambiguous += 1" in source
    assert "continue" in source
    assert "--skip-denver" in source
    assert "candidates[0]" not in source
