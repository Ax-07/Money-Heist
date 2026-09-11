import pytest

from app.services.backtest.mtf_runtime import (
    MTF_RUNTIME_VERSION,
    mtf_execution_assumptions,
    mtf_runner_kwargs,
    supports_full_mtf_source,
)


def test_full_mtf_runtime_support_is_explicit():
    assert supports_full_mtf_source("1m")
    assert supports_full_mtf_source("5m")
    assert supports_full_mtf_source("15m")
    assert not supports_full_mtf_source("30m")
    assert not supports_full_mtf_source("1h")
    assert not supports_full_mtf_source("4h")


def test_supported_source_binds_complete_runtime_contract():
    assumptions = mtf_execution_assumptions("1m")

    assert assumptions == {
        "mtf_runtime_version": "historical-mtf-runtime-v1",
        "historical_source_timeframe": "1m",
        "decision_timeframe": "1h",
        "mtf_timeframes": "15m,1h,4h,1d",
        "mtf_policy_version": "mtf-utc-closed-v1",
        "mtf_feature_context_version": "mtf-feature-context-v1",
        "decision_context_version": "decision-context-v1",
        "agent_context_binding_version": "decision-context-agent-binding-v1",
        "risk_context_binding_version": "portfolio-market-constraints-v1",
        "market_structure_version": "market-structure-v1",
        "lifecycle_timeframe": "1m",
    }

    kwargs = mtf_runner_kwargs(assumptions)
    assert kwargs["decision_timeframe"] == "1h"
    assert kwargs["mtf_timeframes"] == ("15m", "1h", "4h", "1d")
    assert kwargs["risk_context_binding_version"] == (
        "portfolio-market-constraints-v1"
    )


def test_native_1h_source_remains_legacy():
    assert mtf_execution_assumptions("1h") == {}
    assert mtf_runner_kwargs({}) == {}


def test_tampered_versioned_runtime_contract_fails_closed():
    assumptions = mtf_execution_assumptions("1m")
    assumptions["market_structure_version"] = "tampered"

    with pytest.raises(ValueError, match="market_structure_version"):
        mtf_runner_kwargs(assumptions)


def test_runtime_marker_is_required_before_enabling_mtf():
    assumptions = mtf_execution_assumptions("1m")
    assumptions.pop("mtf_runtime_version")
    assert mtf_runner_kwargs(assumptions) == {}
    assert MTF_RUNTIME_VERSION == "historical-mtf-runtime-v1"
