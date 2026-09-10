from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.evaluation.models import Metric
from app.portfolio.allocation import (
    AllocationEnvelopeStatus,
    CrewAllocationEnvelope,
    MasterAllocationPolicy,
    build_master_allocation_policy,
)
from app.portfolio.allocation_advisory import (
    MasterAllocationAdvisoryAction,
    MasterAllocationAdvisoryEvidenceSource,
    MasterAllocationAdvisoryStatus,
    build_master_allocation_advisory_evidence,
    build_master_allocation_advisory_recommendation,
    build_master_allocation_advisory_report,
)
from app.portfolio.historical_replay_closure import (
    MasterHistoricalReplayAuditReport,
    MasterHistoricalReplayAuditStatus,
    MasterHistoricalReplayClosureSeal,
    MasterHistoricalReplayClosureStatus,
    master_historical_replay_audit_payload,
    master_historical_replay_closure_payload,
)
from app.portfolio.historical_replay_master_runner import (
    MasterHistoricalCrewEvaluation,
    MasterHistoricalEvaluation,
    master_historical_crew_evaluation_payload,
    master_historical_evaluation_payload,
)
from app.portfolio.models import PortfolioMemberRef
from app.services.backtest.ids import stable_digest

MASTER_ID = "master-main"
SEALED_AT = datetime(2026, 1, 31, 23, 0, tzinfo=UTC)


def _members(*system_ids: str) -> tuple[PortfolioMemberRef, ...]:
    return tuple(PortfolioMemberRef(system_id=value) for value in sorted(system_ids))


def _envelope(
    system_id: str,
    capital: str,
    risk: str,
    gross: str,
) -> CrewAllocationEnvelope:
    return CrewAllocationEnvelope(
        system_id=system_id,
        status=AllocationEnvelopeStatus.CONFIGURED,
        capital_ceiling_amount=Decimal(capital),
        open_risk_ceiling_amount=Decimal(risk),
        gross_exposure_ceiling_amount=Decimal(gross),
    )


def _policy(
    *,
    master_id: str = MASTER_ID,
    configured: bool = True,
    system_ids: tuple[str, ...] = ("crew-a", "crew-b"),
) -> MasterAllocationPolicy:
    members = _members(*system_ids)
    if configured:
        envelopes = tuple(
            _envelope(system_id, "50", "5", "40") for system_id in sorted(system_ids)
        )
    else:
        envelopes = tuple(
            CrewAllocationEnvelope(
                system_id=system_id,
                status=AllocationEnvelopeStatus.NOT_CONFIGURED,
                reason_code="OPERATOR_CONFIGURATION_REQUIRED",
            )
            for system_id in sorted(system_ids)
        )
    return build_master_allocation_policy(
        master_portfolio_id=master_id,
        policy_id="allocation-v1",
        members=members,
        envelopes=envelopes,
        source_ref="operator-test",
    )


def _metric_payload(metric: Metric) -> dict[str, object]:
    return {
        "status": metric.status,
        "value": metric.value,
        "reason": metric.reason,
    }


def _crew_evaluation(
    system_id: str,
    *,
    realized: str,
    wins: int,
    losses: int,
) -> MasterHistoricalCrewEvaluation:
    closed = wins + losses
    pnl = Decimal(realized)
    win_rate = Metric.available(Decimal(wins) / Decimal(closed))
    expectancy = Metric.available(pnl / Decimal(closed))
    if losses:
        profit_factor = Metric.available(Decimal("2"))
    else:
        profit_factor = Metric.unbounded("NO_LOSING_TRADES")
    body = {
        "schema": "money-heist.master-historical-crew-evaluation.v1",
        "schema_version": "1.0",
        "system_id": system_id,
        "entry_count": closed,
        "closed_lot_count": closed,
        "open_lot_count": 0,
        "winning_lots": wins,
        "losing_lots": losses,
        "breakeven_lots": 0,
        "realized_net_pnl": pnl,
        "final_open_risk_amount": Decimal("0"),
        "final_gross_exposure_amount": Decimal("0"),
        "win_rate": _metric_payload(win_rate),
        "profit_factor": _metric_payload(profit_factor),
        "expectancy": _metric_payload(expectancy),
    }
    return MasterHistoricalCrewEvaluation(
        system_id=system_id,
        entry_count=closed,
        closed_lot_count=closed,
        open_lot_count=0,
        winning_lots=wins,
        losing_lots=losses,
        breakeven_lots=0,
        realized_net_pnl=pnl,
        final_open_risk_amount=Decimal("0"),
        final_gross_exposure_amount=Decimal("0"),
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        fingerprint_sha256=stable_digest(body),
    )


def _evaluation(
    *,
    master_id: str = MASTER_ID,
    system_ids: tuple[str, ...] = ("crew-a", "crew-b"),
) -> MasterHistoricalEvaluation:
    crews = []
    for index, system_id in enumerate(sorted(system_ids)):
        crews.append(
            _crew_evaluation(
                system_id,
                realized="8" if index == 0 else "-3",
                wins=2 if index == 0 else 1,
                losses=1 if index == 0 else 2,
            )
        )
    crew_evaluations = tuple(crews)
    closed = sum(item.closed_lot_count for item in crew_evaluations)
    wins = sum(item.winning_lots for item in crew_evaluations)
    losses = sum(item.losing_lots for item in crew_evaluations)
    realized = sum((item.realized_net_pnl for item in crew_evaluations), Decimal("0"))
    return_pct = Metric.available(Decimal("0.05"))
    max_drawdown_abs = Metric.available(Decimal("4"))
    max_drawdown_pct = Metric.available(Decimal("0.04"))
    win_rate = Metric.available(Decimal(wins) / Decimal(closed))
    profit_factor = Metric.available(Decimal("1.7"))
    expectancy = Metric.available(realized / Decimal(closed))
    ai_cost = Metric.unavailable("AI_USAGE_NOT_SUPPLIED_BY_STEP7_INPUT_PORT")
    economic_net = Metric.unavailable("AI_COST_UNAVAILABLE")
    body = {
        "schema": "money-heist.master-historical-evaluation.v1",
        "schema_version": "1.0",
        "master_portfolio_id": master_id,
        "initial_capital": Decimal("100"),
        "final_equity": Decimal("105"),
        "master_account_net_pnl": Decimal("5"),
        "return_pct": _metric_payload(return_pct),
        "max_drawdown_abs": _metric_payload(max_drawdown_abs),
        "max_drawdown_pct": _metric_payload(max_drawdown_pct),
        "decision_cycle_count": 4,
        "local_authorized_candidate_count": closed,
        "not_reserved_count": 0,
        "master_admitted_count": closed,
        "master_rejected_count": 0,
        "paper_entry_count": closed,
        "paper_cash_blocked_count": 0,
        "closed_lot_count": closed,
        "open_lot_count": 0,
        "winning_lots": wins,
        "losing_lots": losses,
        "breakeven_lots": 0,
        "closed_lot_realized_net_pnl": realized,
        "fees_paid": Decimal("1"),
        "final_open_risk_amount": Decimal("0"),
        "final_virtual_gross_exposure_amount": Decimal("0"),
        "win_rate": _metric_payload(win_rate),
        "profit_factor": _metric_payload(profit_factor),
        "expectancy": _metric_payload(expectancy),
        "ai_cost_eur": _metric_payload(ai_cost),
        "economic_net": _metric_payload(economic_net),
        "crew_evaluations": [
            master_historical_crew_evaluation_payload(item) for item in crew_evaluations
        ],
    }
    return MasterHistoricalEvaluation(
        master_portfolio_id=master_id,
        initial_capital=Decimal("100"),
        final_equity=Decimal("105"),
        master_account_net_pnl=Decimal("5"),
        return_pct=return_pct,
        max_drawdown_abs=max_drawdown_abs,
        max_drawdown_pct=max_drawdown_pct,
        decision_cycle_count=4,
        local_authorized_candidate_count=closed,
        not_reserved_count=0,
        master_admitted_count=closed,
        master_rejected_count=0,
        paper_entry_count=closed,
        paper_cash_blocked_count=0,
        closed_lot_count=closed,
        open_lot_count=0,
        winning_lots=wins,
        losing_lots=losses,
        breakeven_lots=0,
        closed_lot_realized_net_pnl=realized,
        fees_paid=Decimal("1"),
        final_open_risk_amount=Decimal("0"),
        final_virtual_gross_exposure_amount=Decimal("0"),
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        ai_cost_eur=ai_cost,
        economic_net=economic_net,
        crew_evaluations=crew_evaluations,
        fingerprint_sha256=stable_digest(body),
    )


def _audit(
    evaluation: MasterHistoricalEvaluation,
    *,
    sealed_at: datetime = SEALED_AT,
    allocation_fp: str = "a" * 64,
) -> MasterHistoricalReplayAuditReport:
    body = {
        "schema": "money-heist.master-historical-replay-audit.v1",
        "schema_version": "1.0",
        "audit_id": "audit-1",
        "status": MasterHistoricalReplayAuditStatus.VERIFIED,
        "master_portfolio_id": evaluation.master_portfolio_id,
        "plan_id": "plan-1",
        "timeline_id": "timeline-1",
        "result_id": "result-1",
        "sealed_at": sealed_at,
        "plan_fingerprint_sha256": "1" * 64,
        "timeline_fingerprint_sha256": "2" * 64,
        "allocation_policy_fingerprint_sha256": allocation_fp,
        "gate_policy_fingerprint_sha256": "3" * 64,
        "arbitration_policy_fingerprint_sha256": "4" * 64,
        "result_fingerprint_sha256": "5" * 64,
        "opening_snapshot_fingerprint_sha256": "6" * 64,
        "final_account_fingerprint_sha256": "7" * 64,
        "final_book_fingerprint_sha256": "8" * 64,
        "final_ledger_fingerprint_sha256": "9" * 64,
        "evaluation_fingerprint_sha256": evaluation.fingerprint_sha256,
        "processed_barrier_count": 8,
        "decision_cycle_count": 4,
        "equity_point_count": 8,
        "paper_entry_count": evaluation.paper_entry_count,
        "closed_lot_count": evaluation.closed_lot_count,
        "open_lot_count": evaluation.open_lot_count,
        "reserved_reservation_count": 0,
        "committed_reservation_count": evaluation.open_lot_count,
        "released_reservation_count": evaluation.closed_lot_count,
        "final_equity": evaluation.final_equity,
        "final_open_risk_amount": evaluation.final_open_risk_amount,
        "final_virtual_gross_exposure_amount": (
            evaluation.final_virtual_gross_exposure_amount
        ),
        "single_master_capital_verified": True,
        "full_barrier_chain_verified": True,
        "reservation_lifecycle_verified": True,
        "virtual_lot_accounting_verified": True,
        "evaluation_accounting_verified": True,
    }
    return MasterHistoricalReplayAuditReport(
        audit_id="audit-1",
        status=MasterHistoricalReplayAuditStatus.VERIFIED,
        master_portfolio_id=evaluation.master_portfolio_id,
        plan_id="plan-1",
        timeline_id="timeline-1",
        result_id="result-1",
        sealed_at=sealed_at,
        plan_fingerprint_sha256="1" * 64,
        timeline_fingerprint_sha256="2" * 64,
        allocation_policy_fingerprint_sha256=allocation_fp,
        gate_policy_fingerprint_sha256="3" * 64,
        arbitration_policy_fingerprint_sha256="4" * 64,
        result_fingerprint_sha256="5" * 64,
        opening_snapshot_fingerprint_sha256="6" * 64,
        final_account_fingerprint_sha256="7" * 64,
        final_book_fingerprint_sha256="8" * 64,
        final_ledger_fingerprint_sha256="9" * 64,
        evaluation_fingerprint_sha256=evaluation.fingerprint_sha256,
        processed_barrier_count=8,
        decision_cycle_count=4,
        equity_point_count=8,
        paper_entry_count=evaluation.paper_entry_count,
        closed_lot_count=evaluation.closed_lot_count,
        open_lot_count=evaluation.open_lot_count,
        reserved_reservation_count=0,
        committed_reservation_count=evaluation.open_lot_count,
        released_reservation_count=evaluation.closed_lot_count,
        final_equity=evaluation.final_equity,
        final_open_risk_amount=evaluation.final_open_risk_amount,
        final_virtual_gross_exposure_amount=(
            evaluation.final_virtual_gross_exposure_amount
        ),
        single_master_capital_verified=True,
        full_barrier_chain_verified=True,
        reservation_lifecycle_verified=True,
        virtual_lot_accounting_verified=True,
        evaluation_accounting_verified=True,
        fingerprint_sha256=stable_digest(body),
    )


def _closure(
    audit: MasterHistoricalReplayAuditReport,
) -> MasterHistoricalReplayClosureSeal:
    body = {
        "schema": "money-heist.master-historical-replay-closure.v1",
        "schema_version": "1.0",
        "closure_id": "closure-1",
        "status": MasterHistoricalReplayClosureStatus.SEALED,
        "master_portfolio_id": audit.master_portfolio_id,
        "plan_id": audit.plan_id,
        "timeline_id": audit.timeline_id,
        "result_id": audit.result_id,
        "sealed_at": audit.sealed_at,
        "audit_fingerprint_sha256": audit.fingerprint_sha256,
        "result_fingerprint_sha256": audit.result_fingerprint_sha256,
        "final_account_fingerprint_sha256": audit.final_account_fingerprint_sha256,
        "final_book_fingerprint_sha256": audit.final_book_fingerprint_sha256,
        "final_ledger_fingerprint_sha256": audit.final_ledger_fingerprint_sha256,
        "evaluation_fingerprint_sha256": audit.evaluation_fingerprint_sha256,
    }
    return MasterHistoricalReplayClosureSeal(
        closure_id="closure-1",
        status=MasterHistoricalReplayClosureStatus.SEALED,
        master_portfolio_id=audit.master_portfolio_id,
        plan_id=audit.plan_id,
        timeline_id=audit.timeline_id,
        result_id=audit.result_id,
        sealed_at=audit.sealed_at,
        audit_fingerprint_sha256=audit.fingerprint_sha256,
        result_fingerprint_sha256=audit.result_fingerprint_sha256,
        final_account_fingerprint_sha256=audit.final_account_fingerprint_sha256,
        final_book_fingerprint_sha256=audit.final_book_fingerprint_sha256,
        final_ledger_fingerprint_sha256=audit.final_ledger_fingerprint_sha256,
        evaluation_fingerprint_sha256=audit.evaluation_fingerprint_sha256,
        closure_fingerprint_sha256=stable_digest(body),
    )


def _evidence(
    *,
    sealed_at: datetime = SEALED_AT,
    regime_label: str | None = None,
    regime_source_ref: str | None = None,
    master_id: str = MASTER_ID,
    system_ids: tuple[str, ...] = ("crew-a", "crew-b"),
):
    evaluation = _evaluation(master_id=master_id, system_ids=system_ids)
    audit = _audit(evaluation, sealed_at=sealed_at)
    closure = _closure(audit)
    return build_master_allocation_advisory_evidence(
        audit_report=audit,
        closure_seal=closure,
        evaluation=evaluation,
        regime_label=regime_label,
        regime_source_ref=regime_source_ref,
    )


def _keep_recommendation(policy: MasterAllocationPolicy):
    return build_master_allocation_advisory_recommendation(
        action=MasterAllocationAdvisoryAction.KEEP_CURRENT,
        proposed_envelopes=policy.envelopes,
        rationale_codes=("SEALED_EVIDENCE_SUPPORTS_CURRENT_ENVELOPES",),
        source_ref="master-professor-shadow:test",
    )


def _change_recommendation():
    return build_master_allocation_advisory_recommendation(
        action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE,
        proposed_envelopes=(
            _envelope("crew-a", "60", "6", "45"),
            _envelope("crew-b", "40", "4", "35"),
        ),
        rationale_codes=("SEALED_REPLAY_COMPARISON",),
        source_ref="master-professor-shadow:test",
    )


def test_evidence_binds_verified_sealed_replay() -> None:
    evidence = _evidence()
    assert evidence.source is MasterAllocationAdvisoryEvidenceSource.SEALED_MASTER_HISTORICAL_REPLAY
    assert evidence.master_portfolio_id == MASTER_ID
    assert evidence.crew_system_ids == ("crew-a", "crew-b")
    assert evidence.advisory_only is True
    assert evidence.mutation_applied is False


def test_evidence_accepts_explicit_regime_metadata() -> None:
    evidence = _evidence(regime_label="TREND_UP", regime_source_ref="regime:v1:btc")
    assert evidence.regime_label == "TREND_UP"
    assert evidence.regime_source_ref == "regime:v1:btc"


@pytest.mark.parametrize(
    ("label", "source_ref"),
    [("TREND_UP", None), (None, "regime:v1")],
)
def test_evidence_requires_complete_regime_metadata(label, source_ref) -> None:
    evaluation = _evaluation()
    audit = _audit(evaluation)
    closure = _closure(audit)
    with pytest.raises(ValueError, match="supplied together"):
        build_master_allocation_advisory_evidence(
            audit_report=audit,
            closure_seal=closure,
            evaluation=evaluation,
            regime_label=label,
            regime_source_ref=source_ref,
        )


def test_evidence_rejects_cross_master_chain() -> None:
    evaluation = _evaluation(master_id="other-master")
    audit = _audit(_evaluation())
    closure = _closure(audit)
    with pytest.raises(ValueError, match="multiple Master Portfolios"):
        build_master_allocation_advisory_evidence(
            audit_report=audit,
            closure_seal=closure,
            evaluation=evaluation,
        )


def test_evidence_rejects_tampered_evaluation() -> None:
    evaluation = _evaluation()
    audit = _audit(evaluation)
    closure = _closure(audit)
    object.__setattr__(evaluation, "final_equity", Decimal("999"))
    with pytest.raises(ValueError, match="evaluation fingerprint integrity"):
        build_master_allocation_advisory_evidence(
            audit_report=audit,
            closure_seal=closure,
            evaluation=evaluation,
        )


def test_evidence_rejects_mismatched_closure_audit_binding() -> None:
    evaluation = _evaluation()
    audit = _audit(evaluation)
    other = _audit(evaluation, sealed_at=SEALED_AT + timedelta(days=1))
    closure = _closure(other)
    with pytest.raises(ValueError, match="provenance mismatch"):
        build_master_allocation_advisory_evidence(
            audit_report=audit,
            closure_seal=closure,
            evaluation=evaluation,
        )


def test_recommendation_builder_canonicalizes_inputs() -> None:
    recommendation = build_master_allocation_advisory_recommendation(
        action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE,
        proposed_envelopes=(
            _envelope("crew-b", "40", "4", "35"),
            _envelope("crew-a", "60", "6", "45"),
        ),
        rationale_codes=("Z_REASON", "A_REASON"),
        source_ref="shadow:1",
    )
    assert tuple(item.system_id for item in recommendation.proposed_envelopes) == (
        "crew-a",
        "crew-b",
    )
    assert recommendation.rationale_codes == ("A_REASON", "Z_REASON")


def test_abstain_recommendation_has_no_proposed_envelopes() -> None:
    recommendation = build_master_allocation_advisory_recommendation(
        action=MasterAllocationAdvisoryAction.ABSTAIN,
        rationale_codes=("INSUFFICIENT_EVIDENCE",),
        source_ref="shadow:1",
    )
    assert recommendation.proposed_envelopes == ()
    assert recommendation.auto_apply is False


def test_abstain_rejects_proposed_envelopes() -> None:
    with pytest.raises(ValueError, match="ABSTAIN"):
        build_master_allocation_advisory_recommendation(
            action=MasterAllocationAdvisoryAction.ABSTAIN,
            proposed_envelopes=(_envelope("crew-a", "50", "5", "40"),),
            rationale_codes=("INSUFFICIENT_EVIDENCE",),
            source_ref="shadow:1",
        )


def test_non_abstaining_recommendation_requires_envelopes() -> None:
    with pytest.raises(ValueError, match="requires proposed envelopes"):
        build_master_allocation_advisory_recommendation(
            action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE,
            rationale_codes=("CHANGE",),
            source_ref="shadow:1",
        )


def test_recommendation_rejects_unconfigured_proposed_envelope() -> None:
    envelope = CrewAllocationEnvelope(
        system_id="crew-a",
        status=AllocationEnvelopeStatus.NOT_CONFIGURED,
        reason_code="MISSING",
    )
    with pytest.raises(ValueError, match="must be CONFIGURED"):
        build_master_allocation_advisory_recommendation(
            action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE,
            proposed_envelopes=(envelope,),
            rationale_codes=("CHANGE",),
            source_ref="shadow:1",
        )


def test_recommendation_requires_unique_rationale_codes() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        build_master_allocation_advisory_recommendation(
            action=MasterAllocationAdvisoryAction.ABSTAIN,
            rationale_codes=("A", "A"),
            source_ref="shadow:1",
        )


def test_keep_current_report_is_operator_review_only() -> None:
    policy = _policy()
    report = build_master_allocation_advisory_report(
        current_allocation_policy=policy,
        evidence=(_evidence(),),
        recommendation=_keep_recommendation(policy),
    )
    assert report.status is MasterAllocationAdvisoryStatus.READY_FOR_OPERATOR_REVIEW
    assert report.mode == "SHADOW"
    assert report.advisor_role == "MASTER_PROFESSOR"
    assert report.operator_review_required is True
    assert report.auto_apply is False
    assert report.policy_mutation is False


def test_propose_change_report_is_valid_but_not_applied() -> None:
    policy = _policy()
    before = policy.fingerprint_sha256
    report = build_master_allocation_advisory_report(
        current_allocation_policy=policy,
        evidence=(_evidence(),),
        recommendation=_change_recommendation(),
    )
    assert report.status is MasterAllocationAdvisoryStatus.READY_FOR_OPERATOR_REVIEW
    assert report.recommendation.action is MasterAllocationAdvisoryAction.PROPOSE_CHANGE
    assert policy.fingerprint_sha256 == before
    assert report.current_allocation_policy is policy


def test_propose_change_must_change_an_envelope() -> None:
    policy = _policy()
    recommendation = build_master_allocation_advisory_recommendation(
        action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE,
        proposed_envelopes=policy.envelopes,
        rationale_codes=("CHANGE",),
        source_ref="shadow:1",
    )
    with pytest.raises(ValueError, match="actually change"):
        build_master_allocation_advisory_report(
            current_allocation_policy=policy,
            evidence=(_evidence(),),
            recommendation=recommendation,
        )


def test_keep_current_must_reproduce_current_envelopes() -> None:
    policy = _policy()
    recommendation = build_master_allocation_advisory_recommendation(
        action=MasterAllocationAdvisoryAction.KEEP_CURRENT,
        proposed_envelopes=_change_recommendation().proposed_envelopes,
        rationale_codes=("KEEP",),
        source_ref="shadow:1",
    )
    with pytest.raises(ValueError, match="reproduce current"):
        build_master_allocation_advisory_report(
            current_allocation_policy=policy,
            evidence=(_evidence(),),
            recommendation=recommendation,
        )


def test_recommendation_cannot_change_crew_membership() -> None:
    policy = _policy()
    recommendation = build_master_allocation_advisory_recommendation(
        action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE,
        proposed_envelopes=(
            _envelope("crew-a", "60", "6", "45"),
            _envelope("crew-c", "40", "4", "35"),
        ),
        rationale_codes=("CHANGE",),
        source_ref="shadow:1",
    )
    with pytest.raises(ValueError, match="preserve exact crew membership"):
        build_master_allocation_advisory_report(
            current_allocation_policy=policy,
            evidence=(_evidence(),),
            recommendation=recommendation,
        )


def test_no_evidence_cannot_propose_change() -> None:
    with pytest.raises(ValueError, match="without evidence"):
        build_master_allocation_advisory_report(
            current_allocation_policy=_policy(),
            evidence=(),
            recommendation=_change_recommendation(),
        )


def test_no_evidence_can_seal_abstention() -> None:
    recommendation = build_master_allocation_advisory_recommendation(
        action=MasterAllocationAdvisoryAction.ABSTAIN,
        rationale_codes=("NO_SEALED_EVIDENCE",),
        source_ref="master-professor-shadow:no-evidence",
    )
    report = build_master_allocation_advisory_report(
        current_allocation_policy=_policy(),
        evidence=(),
        recommendation=recommendation,
    )
    assert report.status is MasterAllocationAdvisoryStatus.ABSTAINED
    assert report.evidence_through is None


def test_unconfigured_current_policy_forces_abstention() -> None:
    with pytest.raises(ValueError, match="requires advisory abstention"):
        build_master_allocation_advisory_report(
            current_allocation_policy=_policy(configured=False),
            evidence=(_evidence(),),
            recommendation=_change_recommendation(),
        )


def test_unconfigured_policy_can_abstain_without_inventing_numbers() -> None:
    recommendation = build_master_allocation_advisory_recommendation(
        action=MasterAllocationAdvisoryAction.ABSTAIN,
        rationale_codes=("CURRENT_POLICY_NOT_CONFIGURED",),
        source_ref="shadow:1",
    )
    report = build_master_allocation_advisory_report(
        current_allocation_policy=_policy(configured=False),
        evidence=(_evidence(),),
        recommendation=recommendation,
    )
    assert report.status is MasterAllocationAdvisoryStatus.ABSTAINED
    assert report.recommendation.proposed_envelopes == ()


def test_evidence_must_match_current_policy_membership() -> None:
    with pytest.raises(ValueError, match="evidence membership mismatch"):
        build_master_allocation_advisory_report(
            current_allocation_policy=_policy(),
            evidence=(_evidence(system_ids=("crew-a", "crew-c")),),
            recommendation=build_master_allocation_advisory_recommendation(
                action=MasterAllocationAdvisoryAction.ABSTAIN,
                rationale_codes=("MEMBERSHIP_MISMATCH",),
                source_ref="shadow:1",
            ),
        )


def test_evidence_is_sorted_by_sealed_time() -> None:
    older = _evidence(sealed_at=SEALED_AT - timedelta(days=10))
    newer = _evidence(
        sealed_at=SEALED_AT,
        regime_label="TREND_UP",
        regime_source_ref="regime:trend-up",
    )
    report = build_master_allocation_advisory_report(
        current_allocation_policy=_policy(),
        evidence=(newer, older),
        recommendation=_keep_recommendation(_policy()),
    )
    assert report.evidence == (older, newer)
    assert report.evidence_through == SEALED_AT


def test_duplicate_evidence_is_rejected() -> None:
    evidence = _evidence()
    with pytest.raises(ValueError, match="evidence must be unique"):
        build_master_allocation_advisory_report(
            current_allocation_policy=_policy(),
            evidence=(evidence, evidence),
            recommendation=_keep_recommendation(_policy()),
        )


def test_report_has_no_trading_or_governance_authority() -> None:
    policy = _policy()
    report = build_master_allocation_advisory_report(
        current_allocation_policy=policy,
        evidence=(_evidence(),),
        recommendation=_keep_recommendation(policy),
    )
    assert report.dynamic_allocation_authority is False
    assert report.reservation_authority is False
    assert report.risk_authority is False
    assert report.admission_authority is False
    assert report.local_risk_override is False
    assert report.resize_authority is False
    assert report.registry_mutation is False
    assert report.broker_authority is False
    assert report.live_authority is False
    assert report.auto_execute is False


def test_builders_are_deterministic() -> None:
    policy_a = _policy()
    policy_b = _policy()
    evidence_a = _evidence(regime_label="RANGE", regime_source_ref="regime:range")
    evidence_b = _evidence(regime_label="RANGE", regime_source_ref="regime:range")
    recommendation_a = _keep_recommendation(policy_a)
    recommendation_b = _keep_recommendation(policy_b)
    report_a = build_master_allocation_advisory_report(
        current_allocation_policy=policy_a,
        evidence=(evidence_a,),
        recommendation=recommendation_a,
    )
    report_b = build_master_allocation_advisory_report(
        current_allocation_policy=policy_b,
        evidence=(evidence_b,),
        recommendation=recommendation_b,
    )
    assert evidence_a.fingerprint_sha256 == evidence_b.fingerprint_sha256
    assert recommendation_a.fingerprint_sha256 == recommendation_b.fingerprint_sha256
    assert report_a.fingerprint_sha256 == report_b.fingerprint_sha256


def test_report_rejects_tampered_current_policy() -> None:
    policy = _policy()
    recommendation = _keep_recommendation(policy)
    object.__setattr__(policy, "policy_id", "tampered")
    with pytest.raises(ValueError, match="current policy fingerprint integrity"):
        build_master_allocation_advisory_report(
            current_allocation_policy=policy,
            evidence=(_evidence(),),
            recommendation=recommendation,
        )


def test_multiple_regime_evidence_items_are_allowed_for_same_membership() -> None:
    evidence = (
        _evidence(regime_label="TREND_UP", regime_source_ref="regime:up"),
        _evidence(
            sealed_at=SEALED_AT + timedelta(days=1),
            regime_label="RANGE",
            regime_source_ref="regime:range",
        ),
    )
    policy = _policy()
    report = build_master_allocation_advisory_report(
        current_allocation_policy=policy,
        evidence=evidence,
        recommendation=_keep_recommendation(policy),
    )
    assert len(report.evidence) == 2
    assert {item.regime_label for item in report.evidence} == {"TREND_UP", "RANGE"}


def test_recommendation_is_not_a_master_allocation_policy() -> None:
    recommendation = _change_recommendation()
    assert not isinstance(recommendation, MasterAllocationPolicy)
    assert not hasattr(recommendation, "policy_id")


def test_evidence_payload_rehash_matches_stored_source_objects() -> None:
    evidence = _evidence()
    assert stable_digest(master_historical_replay_audit_payload(evidence.audit_report)) == (
        evidence.audit_report.fingerprint_sha256
    )
    assert stable_digest(
        master_historical_replay_closure_payload(evidence.closure_seal)
    ) == evidence.closure_seal.closure_fingerprint_sha256
    assert stable_digest(master_historical_evaluation_payload(evidence.evaluation)) == (
        evidence.evaluation.fingerprint_sha256
    )


def test_current_policy_fingerprint_is_not_replaced_by_recommendation() -> None:
    policy = _policy()
    report = build_master_allocation_advisory_report(
        current_allocation_policy=policy,
        evidence=(_evidence(),),
        recommendation=_change_recommendation(),
    )
    assert report.current_allocation_policy.fingerprint_sha256 == policy.fingerprint_sha256
    assert report.recommendation.fingerprint_sha256 != policy.fingerprint_sha256
