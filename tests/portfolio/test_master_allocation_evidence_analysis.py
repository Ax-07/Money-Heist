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
from app.portfolio.allocation_advisory import build_master_allocation_advisory_evidence
from app.portfolio.allocation_evidence_analysis import (
    MasterAllocationAnalysisMetric,
    MasterAllocationAnalysisMetricStatus,
    MasterAllocationAnalysisScope,
    MasterAllocationEvidenceAnalysisStatus,
    build_master_allocation_evidence_analysis,
)
from app.portfolio.historical_replay_closure import (
    MasterHistoricalReplayAuditReport,
    MasterHistoricalReplayAuditStatus,
    MasterHistoricalReplayClosureSeal,
    MasterHistoricalReplayClosureStatus,
)
from app.portfolio.historical_replay_master_runner import (
    MasterHistoricalCrewEvaluation,
    MasterHistoricalEvaluation,
    master_historical_crew_evaluation_payload,
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



def _evidence_with_allocation_fp(
    allocation_fp: str,
    *,
    sealed_at: datetime = SEALED_AT,
    regime_label: str | None = None,
    regime_source_ref: str | None = None,
):
    evaluation = _evaluation()
    audit = _audit(
        evaluation,
        sealed_at=sealed_at,
        allocation_fp=allocation_fp,
    )
    closure = _closure(audit)
    return build_master_allocation_advisory_evidence(
        audit_report=audit,
        closure_seal=closure,
        evaluation=evaluation,
        regime_label=regime_label,
        regime_source_ref=regime_source_ref,
    )


def _overall_crew(report, system_id: str):
    return next(
        item
        for item in report.crew_analyses
        if item.scope is MasterAllocationAnalysisScope.ALL_EVIDENCE
        and item.system_id == system_id
    )


def _regime_crew(report, system_id: str, label: str, source_ref: str):
    return next(
        item
        for item in report.crew_analyses
        if item.scope is MasterAllocationAnalysisScope.REGIME
        and item.system_id == system_id
        and item.regime_label == label
        and item.regime_source_ref == source_ref
    )


def _overall_pair(report, left: str, right: str):
    return next(
        item
        for item in report.pairwise_comparisons
        if item.scope is MasterAllocationAnalysisScope.ALL_EVIDENCE
        and item.left_system_id == left
        and item.right_system_id == right
    )


def test_analysis_metric_available() -> None:
    metric = MasterAllocationAnalysisMetric.available(Decimal("1.25"))
    assert metric.status is MasterAllocationAnalysisMetricStatus.AVAILABLE
    assert metric.value == Decimal("1.25")
    assert metric.reason is None


def test_analysis_metric_unavailable() -> None:
    metric = MasterAllocationAnalysisMetric.unavailable("NO_SAMPLE")
    assert metric.status is MasterAllocationAnalysisMetricStatus.UNAVAILABLE
    assert metric.value is None
    assert metric.reason == "NO_SAMPLE"


def test_analysis_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires at least one sealed evidence"):
        build_master_allocation_evidence_analysis(
            current_allocation_policy=_policy(),
            evidence=(),
        )


def test_single_unlabeled_evidence_is_analyzed_fail_closed() -> None:
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=(_evidence(),),
    )
    assert report.status is MasterAllocationEvidenceAnalysisStatus.ANALYZED
    assert report.unlabeled_evidence_count == 1
    assert report.regime_keys == ()
    assert report.reason_codes == (
        "AI_ECONOMICS_NOT_FULLY_AVAILABLE",
        "SINGLE_EVIDENCE_ONLY",
        "UNLABELED_EVIDENCE_PRESENT",
    )


def test_analysis_builds_one_observation_per_crew_and_evidence() -> None:
    evidence = (
        _evidence(
            sealed_at=SEALED_AT,
            regime_label="TREND",
            regime_source_ref="operator-regime-v1",
        ),
        _evidence(
            sealed_at=SEALED_AT + timedelta(days=1),
            regime_label="RANGE",
            regime_source_ref="operator-regime-v1",
        ),
    )
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=evidence,
    )
    assert len(report.observations) == 4
    assert tuple(item.system_id for item in report.observations) == (
        "crew-a",
        "crew-a",
        "crew-b",
        "crew-b",
    )


def test_analysis_creates_overall_and_exact_regime_scopes() -> None:
    evidence = (
        _evidence(
            sealed_at=SEALED_AT,
            regime_label="TREND",
            regime_source_ref="classifier-v1",
        ),
        _evidence(
            sealed_at=SEALED_AT + timedelta(days=1),
            regime_label="RANGE",
            regime_source_ref="classifier-v1",
        ),
    )
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=evidence,
    )
    assert report.regime_keys == (
        ("RANGE", "classifier-v1"),
        ("TREND", "classifier-v1"),
    )
    assert len(report.crew_analyses) == 6
    assert len(report.pairwise_comparisons) == 3


def test_overall_crew_analysis_pools_trade_counts_without_capital_aggregation() -> None:
    evidence = (
        _evidence(sealed_at=SEALED_AT),
        _evidence(sealed_at=SEALED_AT + timedelta(days=1)),
    )
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=evidence,
    )
    crew = _overall_crew(report, "crew-a")
    assert crew.evidence_count == 2
    assert crew.entry_count == 6
    assert crew.closed_lot_count == 6
    assert crew.winning_lots == 4
    assert crew.losing_lots == 2
    assert crew.replay_realized_net_pnl_sum == Decimal("16")
    assert crew.mean_replay_realized_net_pnl == Decimal("8")
    assert crew.pooled_win_rate.value == Decimal("4") / Decimal("6")
    assert crew.pooled_expectancy.value == Decimal("16") / Decimal("6")
    assert crew.physical_capital_aggregation is False


def test_regime_crew_analysis_keeps_exact_regime_provenance() -> None:
    evidence = _evidence(
        regime_label="TREND",
        regime_source_ref="operator-label-v2",
    )
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=(evidence,),
    )
    crew = _regime_crew(report, "crew-a", "TREND", "operator-label-v2")
    assert crew.evidence_count == 1
    assert crew.replay_realized_net_pnl_sum == Decimal("8")
    assert crew.regime_source_ref == "operator-label-v2"


def test_same_regime_label_from_different_sources_is_not_merged() -> None:
    evidence = (
        _evidence(
            sealed_at=SEALED_AT,
            regime_label="TREND",
            regime_source_ref="classifier-v1",
        ),
        _evidence(
            sealed_at=SEALED_AT + timedelta(days=1),
            regime_label="TREND",
            regime_source_ref="classifier-v2",
        ),
    )
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=evidence,
    )
    assert report.regime_keys == (
        ("TREND", "classifier-v1"),
        ("TREND", "classifier-v2"),
    )


def test_pairwise_comparison_reports_deltas_without_winner_or_score() -> None:
    evidence = (
        _evidence(sealed_at=SEALED_AT),
        _evidence(sealed_at=SEALED_AT + timedelta(days=1)),
    )
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=evidence,
    )
    comparison = _overall_pair(report, "crew-a", "crew-b")
    assert comparison.evidence_count == 2
    assert comparison.realized_pnl_left_better_count == 2
    assert comparison.realized_pnl_right_better_count == 0
    assert comparison.realized_pnl_tie_count == 0
    assert comparison.mean_realized_net_pnl_delta == Decimal("11")
    assert comparison.mean_win_rate_delta.value == (
        Decimal("2") / Decimal("3") - Decimal("1") / Decimal("3")
    )
    assert comparison.mean_expectancy_delta.value == Decimal("11") / Decimal("3")
    assert comparison.ranking_generated is False
    assert comparison.score_generated is False
    assert comparison.allocation_generated is False


def test_pairwise_regime_comparison_uses_only_matching_regime_evidence() -> None:
    trend = _evidence(
        sealed_at=SEALED_AT,
        regime_label="TREND",
        regime_source_ref="classifier-v1",
    )
    range_evidence = _evidence(
        sealed_at=SEALED_AT + timedelta(days=1),
        regime_label="RANGE",
        regime_source_ref="classifier-v1",
    )
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=(trend, range_evidence),
    )
    trend_pair = next(
        item
        for item in report.pairwise_comparisons
        if item.scope is MasterAllocationAnalysisScope.REGIME
        and item.regime_label == "TREND"
    )
    assert trend_pair.evidence_count == 1
    assert trend_pair.evidence_ids == (trend.evidence_id,)


def test_analysis_is_deterministic_under_input_permutation() -> None:
    first = _evidence(
        sealed_at=SEALED_AT,
        regime_label="TREND",
        regime_source_ref="classifier-v1",
    )
    second = _evidence(
        sealed_at=SEALED_AT + timedelta(days=1),
        regime_label="RANGE",
        regime_source_ref="classifier-v1",
    )
    forward = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=(first, second),
    )
    reverse = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=(second, first),
    )
    assert forward.fingerprint_sha256 == reverse.fingerprint_sha256
    assert forward.analysis_id == reverse.analysis_id


def test_duplicate_evidence_is_rejected() -> None:
    evidence = _evidence()
    with pytest.raises(ValueError, match="unique evidence fingerprints"):
        build_master_allocation_evidence_analysis(
            current_allocation_policy=_policy(),
            evidence=(evidence, evidence),
        )


def test_cross_master_evidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="multiple Master Portfolios"):
        build_master_allocation_evidence_analysis(
            current_allocation_policy=_policy(),
            evidence=(_evidence(master_id="other-master"),),
        )


def test_membership_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="membership mismatch"):
        build_master_allocation_evidence_analysis(
            current_allocation_policy=_policy(),
            evidence=(_evidence(system_ids=("crew-a", "crew-c")),),
        )


def test_tampered_nested_evaluation_is_rejected() -> None:
    evidence = _evidence()
    object.__setattr__(evidence.evaluation, "final_equity", Decimal("999"))
    with pytest.raises(ValueError, match="evaluation fingerprint integrity failure"):
        build_master_allocation_evidence_analysis(
            current_allocation_policy=_policy(),
            evidence=(evidence,),
        )


def test_tampered_current_policy_is_rejected() -> None:
    policy = _policy()
    object.__setattr__(policy, "source_ref", "tampered")
    with pytest.raises(ValueError, match="current policy fingerprint integrity failure"):
        build_master_allocation_evidence_analysis(
            current_allocation_policy=policy,
            evidence=(_evidence(),),
        )


def test_unconfigured_current_policy_can_be_analyzed_without_creating_values() -> None:
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(configured=False),
        evidence=(_evidence(),),
    )
    assert report.status is MasterAllocationEvidenceAnalysisStatus.ANALYZED
    assert report.recommendation_generated is False
    assert report.allocation_generated is False
    assert report.policy_mutation is False


def test_multiple_historical_allocation_policies_are_preserved_not_normalized() -> None:
    first = _evidence_with_allocation_fp(
        "a" * 64,
        sealed_at=SEALED_AT,
    )
    second = _evidence_with_allocation_fp(
        "b" * 64,
        sealed_at=SEALED_AT + timedelta(days=1),
    )
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=(first, second),
    )
    assert report.historical_allocation_policy_fingerprints_sha256 == (
        "a" * 64,
        "b" * 64,
    )
    assert "MULTIPLE_HISTORICAL_ALLOCATION_POLICIES" in report.reason_codes


def test_unlabeled_evidence_does_not_create_synthetic_regime() -> None:
    unlabeled = _evidence(sealed_at=SEALED_AT)
    labeled = _evidence(
        sealed_at=SEALED_AT + timedelta(days=1),
        regime_label="TREND",
        regime_source_ref="classifier-v1",
    )
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=(unlabeled, labeled),
    )
    assert report.regime_keys == (("TREND", "classifier-v1"),)
    assert report.unlabeled_evidence_count == 1


def test_report_exposes_no_execution_or_allocation_authority() -> None:
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=(_evidence(),),
    )
    assert report.advisor_role == "MASTER_PROFESSOR"
    assert report.mode == "SHADOW"
    assert report.advisory_only is True
    assert report.descriptive_analysis_only is True
    assert report.recommendation_generated is False
    assert report.allocation_generated is False
    assert report.score_generated is False
    assert report.ranking_generated is False
    assert report.optimization_performed is False
    assert report.statistical_correlation_inferred is False
    assert report.kelly_sizing is False
    assert report.policy_mutation is False
    assert report.reservation_authority is False
    assert report.risk_authority is False
    assert report.admission_authority is False
    assert report.local_risk_override is False
    assert report.resize_authority is False
    assert report.registry_mutation is False
    assert report.broker_authority is False
    assert report.live_authority is False
    assert report.auto_execute is False
    assert report.physical_capital_aggregation is False


def test_observations_copy_metrics_into_portfolio_local_contracts() -> None:
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=(_evidence(),),
    )
    observation = next(item for item in report.observations if item.system_id == "crew-a")
    assert isinstance(observation.win_rate, MasterAllocationAnalysisMetric)
    assert observation.win_rate.status is MasterAllocationAnalysisMetricStatus.AVAILABLE
    assert observation.profit_factor.status is MasterAllocationAnalysisMetricStatus.AVAILABLE
    assert observation.expectancy.status is MasterAllocationAnalysisMetricStatus.AVAILABLE


def test_evidence_through_uses_latest_sealed_timestamp() -> None:
    first = _evidence(sealed_at=SEALED_AT)
    second_at = SEALED_AT + timedelta(days=7)
    second = _evidence(sealed_at=second_at)
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=(second, first),
    )
    assert report.evidence_through == second_at


def test_analysis_fingerprint_detects_post_construction_tampering() -> None:
    report = build_master_allocation_evidence_analysis(
        current_allocation_policy=_policy(),
        evidence=(_evidence(),),
    )
    original = report.fingerprint_sha256
    object.__setattr__(report, "unlabeled_evidence_count", 0)
    assert report.fingerprint_sha256 == original
    assert stable_digest(report.canonical_payload()) != report.fingerprint_sha256
