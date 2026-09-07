from __future__ import annotations

from app.services.paper_pipeline import PaperPipelineStatus
from app.services.shadow import DEFAULT_SHADOW_SYSTEMS, ShadowFleetRunner
from app.trading.risk import RiskEngine, RiskReasonCode

from ._helpers import make_runtime, market_context, root_opportunity, run


def test_unconfigured_shadow_profile_contains_no_invented_risk_values():
    identity = DEFAULT_SHADOW_SYSTEMS[0]
    runtime = make_runtime(identity, risk_profile=None)
    profile = runtime.risk_profile_provider.get_risk_profile(system_id=identity.system_id)
    assert profile is not None
    assert profile.risk_profile_id.endswith(":unresolved")
    assert profile.max_risk_per_trade_pct is None
    assert profile.max_daily_loss_pct is None
    assert profile.max_drawdown_pct is None
    assert profile.max_portfolio_risk_pct is None
    assert profile.max_positions is None
    assert profile.max_leverage is None
    assert profile.max_correlated_exposure_pct is None
    assert profile.min_expected_rr is None
    assert not profile.is_complete


def test_unresolved_profile_fails_closed_through_existing_risk_engine():
    runtimes = (
        make_runtime(DEFAULT_SHADOW_SYSTEMS[0], risk_profile=None),
        make_runtime(DEFAULT_SHADOW_SYSTEMS[1]),
        make_runtime(DEFAULT_SHADOW_SYSTEMS[2]),
    )
    result = run(
        ShadowFleetRunner(runtimes).run(
            root_opportunity=root_opportunity(), market_context=market_context()
        )
    )
    first = result.systems[0].paper_result
    assert first.status is PaperPipelineStatus.RISK_REJECTED
    assert first.risk_record.decision.reason_codes == (RiskReasonCode.PROFILE_INCOMPLETE,)
    assert result.systems[1].paper_result.status is PaperPipelineStatus.EXECUTED
    assert result.systems[2].paper_result.status is PaperPipelineStatus.EXECUTED


def test_risk_engine_implementation_is_reused_not_replaced():
    runtime = make_runtime(DEFAULT_SHADOW_SYSTEMS[0])
    assert type(runtime.paper_pipeline.risk_engine) is RiskEngine


def test_risk_profiles_are_independently_injected_objects():
    runtimes = tuple(make_runtime(identity) for identity in DEFAULT_SHADOW_SYSTEMS)
    profiles = [
        runtime.risk_profile_provider.get_risk_profile(system_id=runtime.identity.system_id)
        for runtime in runtimes
    ]
    assert len({id(profile) for profile in profiles}) == 3
    assert [profile.risk_profile_id for profile in profiles] == [
        f"test:{identity.system_id}" for identity in DEFAULT_SHADOW_SYSTEMS
    ]
