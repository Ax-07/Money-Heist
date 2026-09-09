from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.market.features.models import FeatureQuality, FeatureSnapshot, MarketRegime
from app.market.scanner.models import CandidateOpportunity, ScannerTrigger
from app.services.orchestration.task_force_trigger import (
    TaskForceInvocationPolicy,
    TaskForceInvocationStatus,
    TaskForceTriggerSignal,
    evaluate_task_force_trigger,
    task_force_invocation_policy_fingerprint,
    task_force_trigger_signal_fingerprint,
)
from app.task_force.models import TaskForceInfluenceScope, TaskForceTrigger


NOW = datetime(2026, 9, 9, 15, 0, tzinfo=UTC)


def _opportunity(*, expires_in: int = 600) -> CandidateOpportunity:
    return CandidateOpportunity(
        scanner_version="scanner-v1",
        opportunity_id="11111111-1111-1111-1111-111111111111",
        snapshot_id="snapshot-1",
        system_id="balanced",
        symbol="BTC/EUR",
        timeframe="1h",
        priority_score=80,
        triggers=(ScannerTrigger.REGIME_CHANGE,),
        created_at=NOW,
        expires_at=NOW + timedelta(seconds=expires_in),
    )


def _market(*, observed_at: datetime = NOW) -> FeatureSnapshot:
    return FeatureSnapshot(
        feature_version="features-v1",
        snapshot_id="snapshot-1",
        source_snapshot_id="source-1",
        symbol="BTC/EUR",
        timeframe="1h",
        observed_at=observed_at,
        candle_count=200,
        close=50000.0,
        regime=MarketRegime.UNKNOWN,
        quality=FeatureQuality(warmup_complete=True, closed_candle_count=200),
    )


def _signal(**overrides) -> TaskForceTriggerSignal:
    values = {
        "signal_id": "signal-1",
        "trigger": TaskForceTrigger.UNUSUAL_MARKET_REGIME,
        "objective": "Investigate unusual regime evidence",
        "question": "What explains the regime anomaly?",
        "reason_codes": ("REGIME_UNUSUAL",),
        "evidence_refs": ("feature:regime",),
        "context_refs": ("context:derivatives",),
        "required_roles": ("trend_regime",),
        "required_capabilities": ("regime_analysis",),
        "red_team_required": False,
        "observed_at": NOW + timedelta(seconds=30),
    }
    values.update(overrides)
    return TaskForceTriggerSignal(**values)


def _policy(**overrides) -> TaskForceInvocationPolicy:
    values = {
        "policy_id": "tf-trigger-policy-v1",
        "enabled_triggers": (
            TaskForceTrigger.UNUSUAL_MARKET_REGIME,
            TaskForceTrigger.SPECIALIST_DISAGREEMENT,
        ),
        "max_request_lifetime_seconds": 300,
    }
    values.update(overrides)
    return TaskForceInvocationPolicy(**values)


def test_enabled_explicit_signal_proposes_request_without_execution_authority() -> None:
    decision = evaluate_task_force_trigger(
        policy=_policy(),
        signal=_signal(),
        opportunity=_opportunity(),
        market_context=_market(),
    )

    assert decision.status is TaskForceInvocationStatus.PROPOSED
    assert decision.request is not None
    assert decision.request.influence_scope is TaskForceInfluenceScope.ORCHESTRATION_ADVISORY
    assert decision.request.auto_execute is False
    assert decision.execute_task_force is False
    assert decision.operator_authorization_required is True
    assert decision.trade_proposal_authority is False
    assert decision.risk_authority is False
    assert decision.live_authority is False


def test_disabled_trigger_is_skipped_without_request() -> None:
    decision = evaluate_task_force_trigger(
        policy=_policy(enabled_triggers=(TaskForceTrigger.SPECIALIST_DISAGREEMENT,)),
        signal=_signal(),
        opportunity=_opportunity(),
        market_context=_market(),
    )

    assert decision.status is TaskForceInvocationStatus.SKIPPED
    assert decision.request is None
    assert decision.request_fingerprint_sha256 is None
    assert decision.decision_reasons == ("TRIGGER_DISABLED_BY_OPERATOR_POLICY",)


def test_request_lifetime_is_capped_by_operator_policy() -> None:
    decision = evaluate_task_force_trigger(
        policy=_policy(max_request_lifetime_seconds=120),
        signal=_signal(),
        opportunity=_opportunity(expires_in=600),
        market_context=_market(),
    )
    assert decision.request is not None
    assert decision.request.expires_at == NOW + timedelta(seconds=150)


def test_request_lifetime_never_outlives_opportunity() -> None:
    decision = evaluate_task_force_trigger(
        policy=_policy(max_request_lifetime_seconds=600),
        signal=_signal(),
        opportunity=_opportunity(expires_in=90),
        market_context=_market(),
    )
    assert decision.request is not None
    assert decision.request.expires_at == NOW + timedelta(seconds=90)


def test_roles_capabilities_and_red_team_are_preserved_not_inferred() -> None:
    signal = _signal(
        required_roles=("red_team", "trend_regime"),
        required_capabilities=("contradiction", "regime_analysis"),
        red_team_required=True,
    )
    decision = evaluate_task_force_trigger(
        policy=_policy(),
        signal=signal,
        opportunity=_opportunity(),
        market_context=_market(),
    )
    assert decision.request is not None
    assert decision.request.required_roles == ("red_team", "trend_regime")
    assert decision.request.required_capabilities == ("contradiction", "regime_analysis")
    assert decision.request.red_team_required is True


def test_context_refs_include_opportunity_snapshot_and_explicit_evidence() -> None:
    decision = evaluate_task_force_trigger(
        policy=_policy(),
        signal=_signal(),
        opportunity=_opportunity(),
        market_context=_market(),
    )
    assert decision.request is not None
    assert decision.request.context_refs == (
        "context:derivatives",
        "feature:regime",
        "market_snapshot:snapshot-1",
        "opportunity:11111111-1111-1111-1111-111111111111",
    )


def test_signal_and_policy_fingerprints_are_order_stable() -> None:
    first = _signal(
        reason_codes=("B", "A"),
        evidence_refs=("e:2", "e:1"),
        required_roles=("trend_regime", "red_team"),
    )
    second = _signal(
        reason_codes=("A", "B"),
        evidence_refs=("e:1", "e:2"),
        required_roles=("red_team", "trend_regime"),
    )
    p1 = _policy(
        enabled_triggers=(
            TaskForceTrigger.SPECIALIST_DISAGREEMENT,
            TaskForceTrigger.UNUSUAL_MARKET_REGIME,
        )
    )
    p2 = _policy(
        enabled_triggers=(
            TaskForceTrigger.UNUSUAL_MARKET_REGIME,
            TaskForceTrigger.SPECIALIST_DISAGREEMENT,
        )
    )
    assert task_force_trigger_signal_fingerprint(first) == task_force_trigger_signal_fingerprint(
        second
    )
    assert task_force_invocation_policy_fingerprint(p1) == task_force_invocation_policy_fingerprint(
        p2
    )


def test_same_material_invocation_is_deterministic() -> None:
    kwargs = {
        "policy": _policy(),
        "signal": _signal(),
        "opportunity": _opportunity(),
        "market_context": _market(),
    }
    first = evaluate_task_force_trigger(**kwargs)
    second = evaluate_task_force_trigger(**kwargs)
    assert first.decision_id == second.decision_id
    assert first.request is not None and second.request is not None
    assert first.request.request_id == second.request.request_id
    assert first.request_fingerprint_sha256 == second.request_fingerprint_sha256


def test_snapshot_symbol_and_timeframe_must_match() -> None:
    market = _market().model_copy(update={"snapshot_id": "other"})
    with pytest.raises(ValueError, match="snapshot_id"):
        evaluate_task_force_trigger(
            policy=_policy(), signal=_signal(), opportunity=_opportunity(), market_context=market
        )

    market = _market().model_copy(update={"symbol": "ETH/EUR"})
    with pytest.raises(ValueError, match="symbol"):
        evaluate_task_force_trigger(
            policy=_policy(), signal=_signal(), opportunity=_opportunity(), market_context=market
        )

    market = _market().model_copy(update={"timeframe": "4h"})
    with pytest.raises(ValueError, match="timeframe"):
        evaluate_task_force_trigger(
            policy=_policy(), signal=_signal(), opportunity=_opportunity(), market_context=market
        )


def test_trigger_rejects_future_market_context_and_invalid_temporal_scope() -> None:
    with pytest.raises(ValueError, match="future"):
        evaluate_task_force_trigger(
            policy=_policy(),
            signal=_signal(observed_at=NOW + timedelta(seconds=10)),
            opportunity=_opportunity(),
            market_context=_market(observed_at=NOW + timedelta(seconds=20)),
        )

    with pytest.raises(ValueError, match="predates"):
        evaluate_task_force_trigger(
            policy=_policy(),
            signal=_signal(observed_at=NOW - timedelta(seconds=1)),
            opportunity=_opportunity(),
            market_context=_market(observed_at=NOW - timedelta(seconds=2)),
        )

    with pytest.raises(PermissionError, match="expired opportunity"):
        evaluate_task_force_trigger(
            policy=_policy(),
            signal=_signal(observed_at=NOW + timedelta(seconds=600)),
            opportunity=_opportunity(expires_in=600),
            market_context=_market(),
        )


def test_incomplete_feature_warmup_is_rejected() -> None:
    market = _market().model_copy(
        update={"quality": FeatureQuality(warmup_complete=False, closed_candle_count=20)}
    )
    with pytest.raises(ValueError, match="warmup"):
        evaluate_task_force_trigger(
            policy=_policy(), signal=_signal(), opportunity=_opportunity(), market_context=market
        )


def test_signal_requires_explicit_non_blank_audit_evidence() -> None:
    with pytest.raises(ValueError):
        _signal(reason_codes=())
    with pytest.raises(ValueError):
        _signal(evidence_refs=())
    with pytest.raises(ValueError, match="duplicates"):
        _signal(evidence_refs=("same", "same"))
    with pytest.raises(ValueError, match="blanks"):
        _signal(reason_codes=("OK", "  "))
