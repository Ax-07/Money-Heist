from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.portfolio import (
    MasterRiskGateDecision,
    MasterRiskGateDecisionStatus,
    MasterRiskGatePolicy,
    MasterRiskGatePolicySource,
    MasterRiskGatePolicyStatus,
    MasterRiskGateReasonCode,
    build_master_risk_gate_candidate,
    build_master_risk_gate_policy,
)
from app.portfolio.risk_gate import _build_master_risk_gate_decision
from app.trading.risk.models import RiskDecision, RiskDecisionStatus, RiskReasonCode

NOW = datetime(2026, 9, 9, 23, 0, tzinfo=UTC)
ALLOCATION_FINGERPRINT = "a" * 64
GATE_FINGERPRINT = "b" * 64
SNAPSHOT_FINGERPRINT = "c" * 64
LEDGER_FINGERPRINT = "d" * 64


def approved_decision(
    *,
    status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
    quantity: str = "2",
    risk: str = "3",
    notional: str = "50",
) -> RiskDecision:
    reason_codes = (
        (RiskReasonCode.APPROVED,)
        if status is RiskDecisionStatus.APPROVED
        else (RiskReasonCode.RESIZED_PORTFOLIO_RISK,)
    )
    return RiskDecision(
        proposal_id="proposal-1",
        status=status,
        reason_codes=reason_codes,
        approved_quantity=Decimal(quantity),
        approved_risk_amount=Decimal(risk),
        approved_notional=Decimal(notional),
        created_at=NOW,
        details={"source": "local-risk"},
    )


def rejected_decision() -> RiskDecision:
    return RiskDecision(
        proposal_id="proposal-1",
        status=RiskDecisionStatus.REJECTED,
        reason_codes=(RiskReasonCode.MAX_PORTFOLIO_RISK,),
        created_at=NOW,
    )


def configured_policy() -> MasterRiskGatePolicy:
    return build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id="global-v1",
        allocation_policy_fingerprint_sha256=ALLOCATION_FINGERPRINT,
        max_total_open_risk_amount=Decimal("8"),
        max_total_gross_exposure_amount=Decimal("200"),
        source_ref="operator-config:global-v1",
    )


def authorized_candidate(*, resized: bool = False):
    status = RiskDecisionStatus.RESIZED if resized else RiskDecisionStatus.APPROVED
    return build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=approved_decision(status=status),
        reservation_id="reservation:proposal-1",
    )


def test_configured_gate_policy_is_explicit_and_operator_owned() -> None:
    policy = configured_policy()

    assert policy.status is MasterRiskGatePolicyStatus.CONFIGURED
    assert policy.source is MasterRiskGatePolicySource.OPERATOR_CONFIGURATION
    assert policy.max_total_open_risk_amount == Decimal("8")
    assert policy.max_total_gross_exposure_amount == Decimal("200")
    assert policy.reason_code is None


def test_gate_policy_requires_all_global_limits_or_none() -> None:
    with pytest.raises(ValueError, match="all configured or all absent"):
        build_master_risk_gate_policy(
            master_portfolio_id="master-main",
            gate_policy_id="global-v1",
            allocation_policy_fingerprint_sha256=ALLOCATION_FINGERPRINT,
            max_total_open_risk_amount=Decimal("8"),
        )


def test_not_configured_gate_policy_requires_operator_reason() -> None:
    with pytest.raises(ValueError, match="requires reason_code"):
        build_master_risk_gate_policy(
            master_portfolio_id="master-main",
            gate_policy_id="global-v1",
            allocation_policy_fingerprint_sha256=ALLOCATION_FINGERPRINT,
        )

    policy = build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id="global-v1",
        allocation_policy_fingerprint_sha256=ALLOCATION_FINGERPRINT,
        reason_code="OPERATOR_CONFIGURATION_REQUIRED",
    )
    assert policy.status is MasterRiskGatePolicyStatus.NOT_CONFIGURED
    assert policy.max_total_open_risk_amount is None
    assert policy.max_total_gross_exposure_amount is None


def test_zero_global_limits_are_valid_explicit_configuration() -> None:
    policy = build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id="zero-v1",
        allocation_policy_fingerprint_sha256=ALLOCATION_FINGERPRINT,
        max_total_open_risk_amount=Decimal("0"),
        max_total_gross_exposure_amount=Decimal("0"),
    )

    assert policy.status is MasterRiskGatePolicyStatus.CONFIGURED
    assert policy.max_total_open_risk_amount == Decimal("0")
    assert policy.max_total_gross_exposure_amount == Decimal("0")


def test_gate_policy_rejects_negative_or_non_finite_limits() -> None:
    with pytest.raises(ValueError, match="finite and >= 0"):
        build_master_risk_gate_policy(
            master_portfolio_id="master-main",
            gate_policy_id="global-v1",
            allocation_policy_fingerprint_sha256=ALLOCATION_FINGERPRINT,
            max_total_open_risk_amount=Decimal("-1"),
            max_total_gross_exposure_amount=Decimal("200"),
            )
    with pytest.raises(ValueError, match="finite and >= 0"):
        build_master_risk_gate_policy(
            master_portfolio_id="master-main",
            gate_policy_id="global-v1",
            allocation_policy_fingerprint_sha256=ALLOCATION_FINGERPRINT,
            max_total_open_risk_amount=Decimal("8"),
            max_total_gross_exposure_amount=Decimal("NaN"),
            )


def test_gate_policy_fingerprint_binds_limits_and_allocation_policy() -> None:
    policy = configured_policy()
    changed = build_master_risk_gate_policy(
        master_portfolio_id="master-main",
        gate_policy_id="global-v1",
        allocation_policy_fingerprint_sha256="e" * 64,
        max_total_open_risk_amount=Decimal("8"),
        max_total_gross_exposure_amount=Decimal("200"),
        source_ref="operator-config:global-v1",
    )

    assert changed.fingerprint_sha256 != policy.fingerprint_sha256
    with pytest.raises(ValueError, match="fingerprint does not match payload"):
        replace(policy, max_total_open_risk_amount=Decimal("9"))


def test_gate_policy_has_no_local_risk_or_live_override_authority() -> None:
    policy = configured_policy()

    assert policy.veto_only is True
    assert policy.local_risk_override is False
    assert policy.resize_authority is False
    assert policy.risk_authority is False
    assert policy.admission_authority is False
    assert policy.reservation_mutation is False
    assert policy.broker_authority is False
    assert policy.registry_mutation is False
    assert policy.live_authority is False
    assert policy.auto_execute is False


def test_authorized_candidate_requires_existing_reservation_context() -> None:
    with pytest.raises(ValueError, match="requires reservation_id"):
        build_master_risk_gate_candidate(
            master_portfolio_id="master-main",
            system_id="crew-a",
            local_risk_decision=approved_decision(),
            reservation_id=None,
        )


def test_rejected_local_risk_candidate_carries_no_reservation_or_amounts() -> None:
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=rejected_decision(),
        reservation_id=None,
    )

    assert candidate.local_risk_authorized is False
    assert candidate.local_risk_status is RiskDecisionStatus.REJECTED
    assert candidate.reservation_id is None
    assert candidate.local_approved_quantity == 0
    assert candidate.local_approved_risk_amount == 0
    assert candidate.local_approved_notional == 0


def test_rejected_local_risk_candidate_cannot_gain_a_reservation() -> None:
    with pytest.raises(ValueError, match="cannot carry reservation_id"):
        build_master_risk_gate_candidate(
            master_portfolio_id="master-main",
            system_id="crew-a",
            local_risk_decision=rejected_decision(),
            reservation_id="reservation:forbidden",
        )


def test_rejected_local_risk_candidate_cannot_carry_fake_approved_amounts() -> None:
    invalid = RiskDecision(
        proposal_id="proposal-1",
        status=RiskDecisionStatus.REJECTED,
        reason_codes=(RiskReasonCode.MAX_PORTFOLIO_RISK,),
        approved_quantity=Decimal("1"),
        approved_risk_amount=Decimal("1"),
        approved_notional=Decimal("10"),
        created_at=NOW,
    )

    with pytest.raises(ValueError, match="cannot carry approved amounts"):
        build_master_risk_gate_candidate(
            master_portfolio_id="master-main",
            system_id="crew-a",
            local_risk_decision=invalid,
            reservation_id=None,
        )


def test_candidate_fingerprint_binds_system_reservation_and_local_risk() -> None:
    candidate = authorized_candidate()
    other_system = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-b",
        local_risk_decision=approved_decision(),
        reservation_id="reservation:proposal-1",
    )
    other_reservation = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=approved_decision(),
        reservation_id="reservation:other",
    )

    assert candidate.fingerprint_sha256 != other_system.fingerprint_sha256
    assert candidate.fingerprint_sha256 != other_reservation.fingerprint_sha256
    with pytest.raises(ValueError, match="fingerprint does not match payload"):
        replace(candidate, reservation_id="reservation:tampered")


def test_admit_preserves_approved_local_risk_amounts_exactly() -> None:
    candidate = authorized_candidate()
    decision = _build_master_risk_gate_decision(
        candidate=candidate,
        status=MasterRiskGateDecisionStatus.ADMIT,
        reason_codes=(MasterRiskGateReasonCode.ADMITTED,),
        gate_policy_fingerprint_sha256=GATE_FINGERPRINT,
        portfolio_snapshot_fingerprint_sha256=SNAPSHOT_FINGERPRINT,
        reservation_ledger_fingerprint_sha256=LEDGER_FINGERPRINT,
        created_at=NOW,
    )

    assert decision.status is MasterRiskGateDecisionStatus.ADMIT
    assert decision.admitted_quantity == candidate.local_approved_quantity
    assert decision.admitted_risk_amount == candidate.local_approved_risk_amount
    assert decision.admitted_notional == candidate.local_approved_notional
    assert decision.resize_applied is False


def test_admit_preserves_resized_local_risk_amounts_exactly() -> None:
    candidate = authorized_candidate(resized=True)
    decision = _build_master_risk_gate_decision(
        candidate=candidate,
        status=MasterRiskGateDecisionStatus.ADMIT,
        reason_codes=(MasterRiskGateReasonCode.ADMITTED,),
        gate_policy_fingerprint_sha256=GATE_FINGERPRINT,
        portfolio_snapshot_fingerprint_sha256=SNAPSHOT_FINGERPRINT,
        reservation_ledger_fingerprint_sha256=LEDGER_FINGERPRINT,
        created_at=NOW,
    )

    assert decision.local_risk_status is RiskDecisionStatus.RESIZED
    assert decision.admitted_quantity == candidate.local_approved_quantity
    assert decision.admitted_risk_amount == candidate.local_approved_risk_amount
    assert decision.admitted_notional == candidate.local_approved_notional


def test_master_gate_can_never_admit_a_local_risk_rejection() -> None:
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=rejected_decision(),
        reservation_id=None,
    )

    with pytest.raises(ValueError, match="ADMIT requires an authorized local Risk decision"):
        _build_master_risk_gate_decision(
            candidate=candidate,
            status=MasterRiskGateDecisionStatus.ADMIT,
            reason_codes=(MasterRiskGateReasonCode.ADMITTED,),
            gate_policy_fingerprint_sha256=GATE_FINGERPRINT,
            portfolio_snapshot_fingerprint_sha256=SNAPSHOT_FINGERPRINT,
            reservation_ledger_fingerprint_sha256=LEDGER_FINGERPRINT,
            created_at=NOW,
        )


def test_reject_has_zero_admitted_amounts_and_preserves_local_authorization() -> None:
    candidate = authorized_candidate()
    decision = _build_master_risk_gate_decision(
        candidate=candidate,
        status=MasterRiskGateDecisionStatus.REJECT,
        reason_codes=(MasterRiskGateReasonCode.MASTER_OPEN_RISK_LIMIT_EXCEEDED,),
        gate_policy_fingerprint_sha256=GATE_FINGERPRINT,
        portfolio_snapshot_fingerprint_sha256=SNAPSHOT_FINGERPRINT,
        reservation_ledger_fingerprint_sha256=LEDGER_FINGERPRINT,
        created_at=NOW,
    )

    assert decision.local_risk_status is RiskDecisionStatus.APPROVED
    assert decision.local_approved_risk_amount == Decimal("3")
    assert decision.admitted_quantity == 0
    assert decision.admitted_risk_amount == 0
    assert decision.admitted_notional == 0


def test_local_risk_rejection_must_remain_explicit_in_master_rejection() -> None:
    candidate = build_master_risk_gate_candidate(
        master_portfolio_id="master-main",
        system_id="crew-a",
        local_risk_decision=rejected_decision(),
        reservation_id=None,
    )

    with pytest.raises(ValueError, match="local Risk rejection must remain explicit"):
        _build_master_risk_gate_decision(
            candidate=candidate,
            status=MasterRiskGateDecisionStatus.REJECT,
            reason_codes=(MasterRiskGateReasonCode.GATE_POLICY_NOT_CONFIGURED,),
            gate_policy_fingerprint_sha256=GATE_FINGERPRINT,
            portfolio_snapshot_fingerprint_sha256=SNAPSHOT_FINGERPRINT,
            reservation_ledger_fingerprint_sha256=LEDGER_FINGERPRINT,
            created_at=NOW,
        )

    decision = _build_master_risk_gate_decision(
        candidate=candidate,
        status=MasterRiskGateDecisionStatus.REJECT,
        reason_codes=(MasterRiskGateReasonCode.LOCAL_RISK_NOT_AUTHORIZED,),
        gate_policy_fingerprint_sha256=GATE_FINGERPRINT,
        portfolio_snapshot_fingerprint_sha256=SNAPSHOT_FINGERPRINT,
        reservation_ledger_fingerprint_sha256=LEDGER_FINGERPRINT,
        created_at=NOW,
    )
    assert decision.status is MasterRiskGateDecisionStatus.REJECT


def test_admit_cannot_resize_even_when_constructed_directly() -> None:
    candidate = authorized_candidate()
    valid = _build_master_risk_gate_decision(
        candidate=candidate,
        status=MasterRiskGateDecisionStatus.ADMIT,
        reason_codes=(MasterRiskGateReasonCode.ADMITTED,),
        gate_policy_fingerprint_sha256=GATE_FINGERPRINT,
        portfolio_snapshot_fingerprint_sha256=SNAPSHOT_FINGERPRINT,
        reservation_ledger_fingerprint_sha256=LEDGER_FINGERPRINT,
        created_at=NOW,
    )

    with pytest.raises(ValueError, match="cannot resize"):
        replace(valid, admitted_quantity=Decimal("1"))


def test_master_gate_decision_has_admission_but_no_risk_or_execution_authority() -> None:
    decision = _build_master_risk_gate_decision(
        candidate=authorized_candidate(),
        status=MasterRiskGateDecisionStatus.ADMIT,
        reason_codes=(MasterRiskGateReasonCode.ADMITTED,),
        gate_policy_fingerprint_sha256=GATE_FINGERPRINT,
        portfolio_snapshot_fingerprint_sha256=SNAPSHOT_FINGERPRINT,
        reservation_ledger_fingerprint_sha256=LEDGER_FINGERPRINT,
        created_at=NOW,
    )

    assert decision.veto_only is True
    assert decision.local_risk_override is False
    assert decision.resize_applied is False
    assert decision.risk_authority is False
    assert decision.admission_authority is True
    assert decision.reservation_mutation is False
    assert decision.broker_authority is False
    assert decision.registry_mutation is False
    assert decision.live_authority is False
    assert decision.auto_execute is False


def test_decision_fingerprint_binds_evidence_and_outcome() -> None:
    candidate = authorized_candidate()
    admitted = _build_master_risk_gate_decision(
        candidate=candidate,
        status=MasterRiskGateDecisionStatus.ADMIT,
        reason_codes=(MasterRiskGateReasonCode.ADMITTED,),
        gate_policy_fingerprint_sha256=GATE_FINGERPRINT,
        portfolio_snapshot_fingerprint_sha256=SNAPSHOT_FINGERPRINT,
        reservation_ledger_fingerprint_sha256=LEDGER_FINGERPRINT,
        created_at=NOW,
    )
    rejected = _build_master_risk_gate_decision(
        candidate=candidate,
        status=MasterRiskGateDecisionStatus.REJECT,
        reason_codes=(MasterRiskGateReasonCode.MASTER_GROSS_EXPOSURE_LIMIT_EXCEEDED,),
        gate_policy_fingerprint_sha256=GATE_FINGERPRINT,
        portfolio_snapshot_fingerprint_sha256=SNAPSHOT_FINGERPRINT,
        reservation_ledger_fingerprint_sha256=LEDGER_FINGERPRINT,
        created_at=NOW,
    )

    assert admitted.fingerprint_sha256 != rejected.fingerprint_sha256
    assert admitted.decision_id != rejected.decision_id
    with pytest.raises(ValueError, match="fingerprint does not match payload"):
        replace(rejected, portfolio_snapshot_fingerprint_sha256="e" * 64)


def test_policy_and_decision_contracts_are_immutable() -> None:
    policy = configured_policy()
    decision = _build_master_risk_gate_decision(
        candidate=authorized_candidate(),
        status=MasterRiskGateDecisionStatus.ADMIT,
        reason_codes=(MasterRiskGateReasonCode.ADMITTED,),
        gate_policy_fingerprint_sha256=GATE_FINGERPRINT,
        portfolio_snapshot_fingerprint_sha256=SNAPSHOT_FINGERPRINT,
        reservation_ledger_fingerprint_sha256=LEDGER_FINGERPRINT,
        created_at=NOW,
    )

    with pytest.raises(FrozenInstanceError):
        policy.gate_policy_id = "changed"
    with pytest.raises(FrozenInstanceError):
        decision.status = MasterRiskGateDecisionStatus.REJECT


def test_step1_contracts_do_not_perform_global_evaluation() -> None:
    assert not hasattr(MasterRiskGatePolicy, "evaluate")
    assert not hasattr(MasterRiskGateDecision, "evaluate")
