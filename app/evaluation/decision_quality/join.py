from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from app.common.canonical import stable_digest, stable_uuid
from app.evaluation.forward_outcomes.models import ForwardOutcomeRecord, ForwardOutcomeReport
from app.evaluation.scanner_forward_outcomes.models import (
    ScannerForwardOutcomeRecord,
    ScannerForwardOutcomeReport,
)

from .models import (
    DECISION_QUALITY_RESEARCH_HORIZONS,
    DECISION_QUALITY_RESEARCH_POLICY_VERSION,
    AnalyticsResearchRef,
    CandidateCausalBlock,
    CandidateDecisionResearchRef,
    CandidatePosthocBlock,
    CandidateResearchRecord,
    DecisionQualityResearchBundle,
    DecisionQualityResearchRun,
    ResearchIntegrityCode,
    ResearchJoinIssue,
    ResearchJoinStatus,
    ResearchOutcomeDefinition,
    ResearchSourceIdentity,
    ScannerCausalBlock,
    ScannerPosthocBlock,
    ScannerResearchProjection,
    ScannerResearchRecord,
)

if TYPE_CHECKING:
    from app.evaluation.analytics_attribution.funnel_stage_models import (
        FunnelStageAnalyticsAttributionSet,
    )
    from app.evaluation.analytics_attribution.scanner_attribution import (
        ScannerAnalyticsAttributionRecord,
        ScannerAnalyticsAttributionSet,
    )
    from app.evaluation.decision_intelligence.models import (
        DecisionIntelligenceRecord,
        DecisionIntelligenceRecordSet,
    )


class DecisionQualityIntegrityError(ValueError):
    def __init__(self, code: ResearchIntegrityCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: ResearchIntegrityCode, message: str) -> None:
    raise DecisionQualityIntegrityError(code, message)


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _record_map(records: Iterable[Any], *, key: str, label: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for record in records:
        identity = str(getattr(record, key))
        if identity in output:
            _fail(ResearchIntegrityCode.DUPLICATE_ID, f"duplicate {label}: {identity}")
        output[identity] = record
    return output


def _issues_status(issues: Iterable[ResearchJoinIssue]) -> tuple[
    ResearchJoinStatus, tuple[ResearchJoinIssue, ...]
]:
    ordered = tuple(sorted(set(issues), key=lambda item: item.value))
    if not ordered:
        return ResearchJoinStatus.MATCHED, ()
    precedence = (
        (
            ResearchJoinIssue.MISSING_DECISION_INTELLIGENCE,
            ResearchJoinStatus.MISSING_DECISION_INTELLIGENCE,
        ),
        (
            ResearchJoinIssue.MISSING_FORWARD_OUTCOME,
            ResearchJoinStatus.MISSING_FORWARD_OUTCOME,
        ),
        (ResearchJoinIssue.MISSING_ANALYTICS, ResearchJoinStatus.MISSING_ANALYTICS),
    )
    for issue, status in precedence:
        if issue in ordered:
            return status, ordered
    raise AssertionError("unhandled Decision Quality join issue")


def _analytics_ref(record: ScannerAnalyticsAttributionRecord) -> AnalyticsResearchRef:
    analytics = record.analytics
    snapshot = analytics.analytics_snapshot
    diagnostics = tuple(sorted(set(str(item) for item in analytics.diagnostics)))
    return AnalyticsResearchRef(
        attribution_record_id=str(record.record_id),
        attribution_record_fingerprint=str(record.record_fingerprint),
        analytics_run_id=str(record.analytics_run_id),
        status=_value(analytics.status),
        analytics_snapshot_id=(
            None if snapshot is None else str(snapshot.analytics_snapshot_id)
        ),
        analytics_snapshot_fingerprint=(
            None if snapshot is None else str(snapshot.analytics_snapshot_fingerprint)
        ),
        analytics_as_of=None if snapshot is None else snapshot.as_of,
        diagnostics=diagnostics,
    )


def _scanner_projection(record: ScannerAnalyticsAttributionRecord) -> ScannerResearchProjection:
    scanner = record.scanner
    return ScannerResearchProjection(
        scanner_evaluation_id=str(scanner.scanner_evaluation_id),
        snapshot_id=str(scanner.snapshot_id),
        classification=_value(scanner.classification),
        score=int(scanner.score),
        candidate_threshold=int(scanner.candidate_threshold),
        score_margin=int(scanner.score_margin),
        triggers=tuple(sorted(set(str(item) for item in scanner.triggers))),
        market_regime=None if scanner.market_regime is None else str(scanner.market_regime),
        candidate_opportunity_id=(
            None
            if scanner.candidate_opportunity_id is None
            else str(scanner.candidate_opportunity_id)
        ),
    )


def _decision_ref(record: DecisionIntelligenceRecord) -> CandidateDecisionResearchRef:
    decision = record.decision
    return CandidateDecisionResearchRef(
        record_id=str(record.record_id),
        record_fingerprint=str(record.record_fingerprint),
        opportunity_fingerprint=str(record.opportunity_fingerprint),
        professor_final_direction=decision.professor_final.direction,
        palermo_verdict=decision.palermo.verdict,
        risk_status=decision.risk.status,
        risk_reason_codes=tuple(sorted(set(str(item) for item in decision.risk.reason_codes))),
        paper_pipeline_status=decision.paper_pipeline_status,
        orchestration_status=decision.orchestration_status,
    )


def _source_identity(
    *,
    period_role: str,
    scanner_record: ScannerAnalyticsAttributionRecord,
) -> ResearchSourceIdentity:
    observation = scanner_record.observation
    return ResearchSourceIdentity(
        source_backtest_run_id=str(scanner_record.source_backtest_run_id),
        analytics_run_id=str(scanner_record.analytics_run_id),
        period_role=period_role,
        dataset_id=str(observation.dataset_id),
        dataset_version=str(observation.dataset_version),
        dataset_content_sha256=str(observation.dataset_content_sha256),
        dataset_source=str(observation.dataset_source),
        system_id=str(observation.system_id),
        symbol=str(observation.symbol),
        source_timeframe=str(observation.source_timeframe),
        decision_timeframe=str(observation.decision_timeframe),
    )


def _same_source(left: ResearchSourceIdentity, right: ResearchSourceIdentity) -> bool:
    return left == right


def _validate_report_scope(
    *,
    source: ResearchSourceIdentity,
    forward_outcomes: ForwardOutcomeReport,
    scanner_forward_outcomes: ScannerForwardOutcomeReport,
) -> None:
    if forward_outcomes.run_id != source.source_backtest_run_id:
        _fail(ResearchIntegrityCode.RUN_MISMATCH, "ForwardOutcomeReport belongs to another run")
    if scanner_forward_outcomes.run_id != source.source_backtest_run_id:
        _fail(
            ResearchIntegrityCode.RUN_MISMATCH,
            "ScannerForwardOutcomeReport belongs to another run",
        )

    report_dataset = (
        forward_outcomes.dataset_id,
        forward_outcomes.dataset_version,
        forward_outcomes.dataset_content_sha256,
        forward_outcomes.dataset_source,
    )
    scanner_dataset = (
        scanner_forward_outcomes.dataset_id,
        scanner_forward_outcomes.dataset_version,
        scanner_forward_outcomes.dataset_content_sha256,
        scanner_forward_outcomes.dataset_source,
    )
    expected_dataset = (
        source.dataset_id,
        source.dataset_version,
        source.dataset_content_sha256,
        source.dataset_source,
    )
    if report_dataset != expected_dataset or scanner_dataset != expected_dataset:
        _fail(ResearchIntegrityCode.DATASET_MISMATCH, "Outcome report dataset identity mismatch")

    if (
        forward_outcomes.system_id != source.system_id
        or scanner_forward_outcomes.system_id != source.system_id
    ):
        _fail(ResearchIntegrityCode.SYSTEM_MISMATCH, "Outcome report system_id mismatch")
    if (
        forward_outcomes.source_timeframe != source.source_timeframe
        or scanner_forward_outcomes.source_timeframe != source.source_timeframe
    ):
        _fail(ResearchIntegrityCode.TIMEFRAME_MISMATCH, "source timeframe mismatch")
    if (
        forward_outcomes.decision_timeframe != source.decision_timeframe
        or scanner_forward_outcomes.decision_timeframe != source.decision_timeframe
    ):
        _fail(ResearchIntegrityCode.TIMEFRAME_MISMATCH, "decision timeframe mismatch")

    if tuple(forward_outcomes.horizons) != DECISION_QUALITY_RESEARCH_HORIZONS:
        _fail(
            ResearchIntegrityCode.HORIZON_MISMATCH,
            "Forward Outcomes must use H1/H3/H5/H10/H20",
        )
    if tuple(scanner_forward_outcomes.horizons) != DECISION_QUALITY_RESEARCH_HORIZONS:
        _fail(
            ResearchIntegrityCode.HORIZON_MISMATCH,
            "Scanner Forward Outcomes must use H1/H3/H5/H10/H20",
        )
    if (
        forward_outcomes.period_start != scanner_forward_outcomes.period_start
        or forward_outcomes.period_end != scanner_forward_outcomes.period_end
    ):
        _fail(ResearchIntegrityCode.ROLE_MISMATCH, "Outcome report period bounds mismatch")


def _validate_scanner_outcome(
    *,
    scanner_record: ScannerAnalyticsAttributionRecord,
    outcome: ScannerForwardOutcomeRecord,
) -> None:
    scanner = scanner_record.scanner
    expected = (
        str(scanner.scanner_evaluation_id),
        str(scanner.snapshot_id),
        scanner.observed_at,
        _value(scanner.classification),
        int(scanner.score),
        int(scanner.candidate_threshold),
        int(scanner.score_margin),
        tuple(scanner.triggers),
        None if scanner.market_regime is None else str(scanner.market_regime),
        None
        if scanner.candidate_opportunity_id is None
        else str(scanner.candidate_opportunity_id),
    )
    actual = (
        str(outcome.scan_id),
        str(outcome.snapshot_id),
        outcome.observed_at,
        _value(outcome.classification),
        int(outcome.score),
        int(outcome.min_priority_score),
        int(outcome.score_margin_to_threshold),
        tuple(outcome.triggers),
        None if outcome.market_regime is None else str(outcome.market_regime),
        None if outcome.candidate_opportunity_id is None else str(outcome.candidate_opportunity_id),
    )
    if expected != actual:
        _fail(
            ResearchIntegrityCode.OBSERVATION_MISMATCH,
            f"Scanner outcome identity/facts diverge for {scanner.scanner_evaluation_id}",
        )


def _validate_decision_record(
    *,
    scanner_record: ScannerAnalyticsAttributionRecord,
    decision_record: DecisionIntelligenceRecord,
    opportunity_id: str,
) -> None:
    source = scanner_record.observation
    scanner = scanner_record.scanner
    if str(decision_record.source_backtest_run_id) != str(scanner_record.source_backtest_run_id):
        _fail(ResearchIntegrityCode.RUN_MISMATCH, "Decision Intelligence run mismatch")
    if str(decision_record.analytics_run_id) != str(scanner_record.analytics_run_id):
        _fail(
            ResearchIntegrityCode.IDENTITY_MISMATCH,
            "Decision Intelligence AnalyticsRun mismatch",
        )
    if str(decision_record.opportunity_id) != opportunity_id:
        _fail(ResearchIntegrityCode.IDENTITY_MISMATCH, "Decision Intelligence opportunity mismatch")
    if str(decision_record.system_id) != str(source.system_id):
        _fail(ResearchIntegrityCode.SYSTEM_MISMATCH, "Decision Intelligence system mismatch")
    if str(decision_record.symbol) != str(source.symbol):
        _fail(ResearchIntegrityCode.SYMBOL_MISMATCH, "Decision Intelligence symbol mismatch")
    if str(decision_record.decision_timeframe) != str(source.decision_timeframe):
        _fail(ResearchIntegrityCode.TIMEFRAME_MISMATCH, "Decision Intelligence timeframe mismatch")
    if decision_record.observed_at != source.observed_at:
        _fail(ResearchIntegrityCode.OBSERVATION_MISMATCH, "Decision Intelligence as-of mismatch")
    if str(decision_record.scanner.snapshot_id) != str(scanner.scanner_evaluation_id):
        _fail(ResearchIntegrityCode.IDENTITY_MISMATCH, "Decision Intelligence Scanner id mismatch")
    if str(decision_record.analytics.status) != _value(scanner_record.analytics.status):
        _fail(ResearchIntegrityCode.IDENTITY_MISMATCH, "candidate Analytics status mismatch")


def _validate_candidate_outcome(
    *,
    scanner_record: ScannerAnalyticsAttributionRecord,
    decision_record: DecisionIntelligenceRecord | None,
    outcome: ForwardOutcomeRecord,
    opportunity_id: str,
) -> None:
    scanner = scanner_record.scanner
    if str(outcome.opportunity_id) != opportunity_id:
        _fail(ResearchIntegrityCode.IDENTITY_MISMATCH, "Forward Outcome opportunity mismatch")
    if str(outcome.snapshot_id) != str(scanner.scanner_evaluation_id):
        _fail(ResearchIntegrityCode.IDENTITY_MISMATCH, "Forward Outcome snapshot mismatch")
    if outcome.observed_at != scanner.observed_at:
        _fail(ResearchIntegrityCode.OBSERVATION_MISMATCH, "Forward Outcome as-of mismatch")
    if decision_record is not None:
        professor_direction = decision_record.decision.professor_final.direction
        proposal_side = decision_record.decision.trade_proposal.side
        if outcome.professor_direction != professor_direction:
            _fail(
                ResearchIntegrityCode.OBSERVATION_MISMATCH,
                "Forward Outcome Professor direction diverges from Decision Intelligence",
            )
        if outcome.proposal_side != proposal_side:
            _fail(
                ResearchIntegrityCode.OBSERVATION_MISMATCH,
                "Forward Outcome proposal side diverges from Decision Intelligence",
            )


def _build_candidate_record(
    *,
    research_run: DecisionQualityResearchRun,
    source: ResearchSourceIdentity,
    scanner_record: ScannerAnalyticsAttributionRecord,
    decision_record: DecisionIntelligenceRecord | None,
    outcome: ForwardOutcomeRecord | None,
) -> CandidateResearchRecord:
    scanner_projection = _scanner_projection(scanner_record)
    opportunity_id = scanner_projection.candidate_opportunity_id
    if opportunity_id is None:
        _fail(
            ResearchIntegrityCode.CANDIDATE_INCONSISTENCY,
            "Candidate Scanner record is missing opportunity id",
        )
    if decision_record is not None:
        _validate_decision_record(
            scanner_record=scanner_record,
            decision_record=decision_record,
            opportunity_id=opportunity_id,
        )
    if outcome is not None:
        _validate_candidate_outcome(
            scanner_record=scanner_record,
            decision_record=decision_record,
            outcome=outcome,
            opportunity_id=opportunity_id,
        )

    analytics = _analytics_ref(scanner_record)
    decision = None if decision_record is None else _decision_ref(decision_record)
    causal_payload = {
        "policy_version": DECISION_QUALITY_RESEARCH_POLICY_VERSION,
        "source": source.model_dump(mode="python"),
        "opportunity_id": opportunity_id,
        "observed_at": scanner_record.observation.observed_at,
        "scanner_attribution_record_fingerprint": str(scanner_record.record_fingerprint),
        "decision_intelligence_record_fingerprint": (
            None if decision_record is None else str(decision_record.record_fingerprint)
        ),
        "scanner": scanner_projection.model_dump(mode="python"),
        "analytics": analytics.model_dump(mode="python"),
        "decision": None if decision is None else decision.model_dump(mode="python"),
    }
    causal = CandidateCausalBlock(
        source=source,
        opportunity_id=opportunity_id,
        observed_at=scanner_record.observation.observed_at,
        scanner=scanner_projection,
        analytics=analytics,
        decision=decision,
        causal_fingerprint=stable_digest(causal_payload),
    )
    posthoc = CandidatePosthocBlock(
        future_outcome=outcome,
        outcome_fingerprint=(
            None if outcome is None else stable_digest(outcome.model_dump(mode="python"))
        ),
    )
    issues: list[ResearchJoinIssue] = []
    if decision_record is None:
        issues.append(ResearchJoinIssue.MISSING_DECISION_INTELLIGENCE)
    if outcome is None:
        issues.append(ResearchJoinIssue.MISSING_FORWARD_OUTCOME)
    if analytics.status != "MATCHED":
        issues.append(ResearchJoinIssue.MISSING_ANALYTICS)
    join_status, join_issues = _issues_status(issues)

    identity_payload = {
        "policy_version": DECISION_QUALITY_RESEARCH_POLICY_VERSION,
        "research_run_id": research_run.research_run_id,
        "source_backtest_run_id": source.source_backtest_run_id,
        "analytics_run_id": source.analytics_run_id,
        "period_role": source.period_role,
        "opportunity_id": opportunity_id,
    }
    record_fingerprint = stable_digest(
        {
            **identity_payload,
            "causal_fingerprint": causal.causal_fingerprint,
            "outcome_fingerprint": posthoc.outcome_fingerprint,
            "join_status": join_status,
            "join_issues": join_issues,
        }
    )
    return CandidateResearchRecord(
        research_run_id=research_run.research_run_id,
        record_id=stable_uuid("candidate-decision-quality-research", identity_payload),
        record_fingerprint=record_fingerprint,
        period_role=source.period_role,
        opportunity_id=opportunity_id,
        causal=causal,
        posthoc=posthoc,
        join_status=join_status,
        join_issues=join_issues,
    )


def _build_scanner_record(
    *,
    research_run: DecisionQualityResearchRun,
    source: ResearchSourceIdentity,
    scanner_record: ScannerAnalyticsAttributionRecord,
    outcome: ScannerForwardOutcomeRecord | None,
) -> ScannerResearchRecord:
    scanner_projection = _scanner_projection(scanner_record)
    scan_id = scanner_projection.scanner_evaluation_id
    if outcome is not None:
        _validate_scanner_outcome(scanner_record=scanner_record, outcome=outcome)
    analytics = _analytics_ref(scanner_record)
    causal_payload = {
        "policy_version": DECISION_QUALITY_RESEARCH_POLICY_VERSION,
        "source": source.model_dump(mode="python"),
        "scan_id": scan_id,
        "observed_at": scanner_record.observation.observed_at,
        "scanner_attribution_record_fingerprint": str(scanner_record.record_fingerprint),
        "scanner": scanner_projection.model_dump(mode="python"),
        "analytics": analytics.model_dump(mode="python"),
    }
    causal = ScannerCausalBlock(
        source=source,
        scan_id=scan_id,
        observed_at=scanner_record.observation.observed_at,
        scanner=scanner_projection,
        analytics=analytics,
        causal_fingerprint=stable_digest(causal_payload),
    )
    posthoc = ScannerPosthocBlock(
        future_outcome=outcome,
        outcome_fingerprint=(
            None if outcome is None else stable_digest(outcome.model_dump(mode="python"))
        ),
    )
    issues: list[ResearchJoinIssue] = []
    if outcome is None:
        issues.append(ResearchJoinIssue.MISSING_FORWARD_OUTCOME)
    if analytics.status != "MATCHED":
        issues.append(ResearchJoinIssue.MISSING_ANALYTICS)
    join_status, join_issues = _issues_status(issues)
    identity_payload = {
        "policy_version": DECISION_QUALITY_RESEARCH_POLICY_VERSION,
        "research_run_id": research_run.research_run_id,
        "source_backtest_run_id": source.source_backtest_run_id,
        "analytics_run_id": source.analytics_run_id,
        "period_role": source.period_role,
        "scan_id": scan_id,
    }
    record_fingerprint = stable_digest(
        {
            **identity_payload,
            "causal_fingerprint": causal.causal_fingerprint,
            "outcome_fingerprint": posthoc.outcome_fingerprint,
            "join_status": join_status,
            "join_issues": join_issues,
        }
    )
    return ScannerResearchRecord(
        research_run_id=research_run.research_run_id,
        record_id=stable_uuid("scanner-decision-quality-research", identity_payload),
        record_fingerprint=record_fingerprint,
        period_role=source.period_role,
        scan_id=scan_id,
        causal=causal,
        posthoc=posthoc,
        join_status=join_status,
        join_issues=join_issues,
    )


def _validate_source_records(
    *,
    expected: ResearchSourceIdentity,
    scanner_attribution: ScannerAnalyticsAttributionSet,
) -> None:
    for record in scanner_attribution.records:
        source = _source_identity(period_role=expected.period_role, scanner_record=record)
        if not _same_source(expected, source):
            _fail(
                ResearchIntegrityCode.IDENTITY_MISMATCH,
                f"Scanner attribution source identity diverges at {record.scanner_evaluation_id}",
            )


def _validate_candidate_consistency(
    *,
    candidate_records: tuple[CandidateResearchRecord, ...],
    scanner_records: tuple[ScannerResearchRecord, ...],
) -> None:
    candidates = {item.opportunity_id: item for item in candidate_records}
    for record in scanner_records:
        opportunity_id = record.causal.scanner.candidate_opportunity_id
        if opportunity_id is None:
            continue
        candidate = candidates.get(opportunity_id)
        if candidate is None:
            _fail(
                ResearchIntegrityCode.CANDIDATE_INCONSISTENCY,
                f"candidate Scanner record has no Candidate research record: {opportunity_id}",
            )
        if candidate.causal.scanner.scanner_evaluation_id != record.scan_id:
            _fail(
                ResearchIntegrityCode.CANDIDATE_INCONSISTENCY,
                f"candidate Scanner identity diverges for {opportunity_id}",
            )


def build_decision_quality_research_bundle(
    *,
    period_role: str,
    decision_intelligence: DecisionIntelligenceRecordSet,
    scanner_attribution: ScannerAnalyticsAttributionSet,
    forward_outcomes: ForwardOutcomeReport,
    scanner_forward_outcomes: ScannerForwardOutcomeReport,
    funnel_stage_attribution: FunnelStageAnalyticsAttributionSet | None = None,
    strict: bool = False,
) -> DecisionQualityResearchBundle:
    """Join causal @T artifacts with already-computed future outcomes, post-hoc only.

    The function never invokes Scanner, agents, Risk, PAPER, Analytics engines or an
    outcome calculator. Missing per-subject artifacts remain explicit research records.
    Cross-run, role, dataset and identity contamination fail closed.
    """

    role = _value(period_role)
    if role != str(scanner_attribution.analytics_period_role):
        _fail(ResearchIntegrityCode.ROLE_MISMATCH, "requested role differs from Analytics role")
    if not scanner_attribution.records:
        _fail(
            ResearchIntegrityCode.IDENTITY_MISMATCH,
            "Decision Quality research requires at least one Scanner attribution record",
        )

    source = _source_identity(period_role=role, scanner_record=scanner_attribution.records[0])
    if str(decision_intelligence.source_backtest_run_id) != source.source_backtest_run_id:
        _fail(ResearchIntegrityCode.RUN_MISMATCH, "Decision Intelligence set run mismatch")
    if str(scanner_attribution.source_backtest_run_id) != source.source_backtest_run_id:
        _fail(ResearchIntegrityCode.RUN_MISMATCH, "Scanner attribution set run mismatch")
    if str(decision_intelligence.analytics_run_id) != source.analytics_run_id:
        _fail(
            ResearchIntegrityCode.IDENTITY_MISMATCH,
            "Decision Intelligence AnalyticsRun mismatch",
        )
    if str(scanner_attribution.analytics_run_id) != source.analytics_run_id:
        _fail(ResearchIntegrityCode.IDENTITY_MISMATCH, "Scanner attribution AnalyticsRun mismatch")

    _validate_source_records(expected=source, scanner_attribution=scanner_attribution)
    _validate_report_scope(
        source=source,
        forward_outcomes=forward_outcomes,
        scanner_forward_outcomes=scanner_forward_outcomes,
    )
    for record in scanner_attribution.records:
        if str(record.scanner.scanner_version) != str(scanner_forward_outcomes.scanner_version):
            _fail(
                ResearchIntegrityCode.IDENTITY_MISMATCH,
                "Scanner Forward Outcome report scanner_version mismatch",
            )
        if int(record.scanner.candidate_threshold) != int(
            scanner_forward_outcomes.min_priority_score
        ):
            _fail(
                ResearchIntegrityCode.IDENTITY_MISMATCH,
                "Scanner Forward Outcome report threshold mismatch",
            )

    if funnel_stage_attribution is not None:
        if str(funnel_stage_attribution.source_backtest_run_id) != source.source_backtest_run_id:
            _fail(ResearchIntegrityCode.RUN_MISMATCH, "Funnel-stage attribution run mismatch")
        if str(funnel_stage_attribution.analytics_run_id) != source.analytics_run_id:
            _fail(ResearchIntegrityCode.IDENTITY_MISMATCH, "Funnel-stage AnalyticsRun mismatch")
        if (
            str(funnel_stage_attribution.source_decision_record_set_fingerprint)
            != str(decision_intelligence.set_fingerprint)
        ):
            _fail(
                ResearchIntegrityCode.SOURCE_FINGERPRINT_MISMATCH,
                "Funnel-stage attribution does not reference this Decision Intelligence set",
            )

    outcome_definition = ResearchOutcomeDefinition(
        forward_outcome_schema_version=forward_outcomes.schema_version,
        forward_outcome_policy_version=forward_outcomes.policy_version,
        scanner_forward_outcome_schema_version=scanner_forward_outcomes.schema_version,
        scanner_forward_outcome_policy_version=scanner_forward_outcomes.policy_version,
        horizons=tuple(forward_outcomes.horizons),
    )
    research_run = DecisionQualityResearchRun.create(
        source=source,
        outcome_definition=outcome_definition,
    )

    scanner_by_id = _record_map(
        scanner_attribution.records,
        key="scanner_evaluation_id",
        label="Scanner evaluation id",
    )
    decision_by_opportunity = _record_map(
        decision_intelligence.records,
        key="opportunity_id",
        label="Decision Intelligence opportunity id",
    )
    candidate_outcomes = _record_map(
        forward_outcomes.records,
        key="opportunity_id",
        label="Forward Outcome opportunity id",
    )
    scanner_outcomes = _record_map(
        scanner_forward_outcomes.records,
        key="scan_id",
        label="Scanner Forward Outcome scan id",
    )

    candidate_scanner_records = tuple(
        record
        for record in scanner_attribution.records
        if _value(record.scanner.classification) == "CANDIDATE_OPPORTUNITY"
    )
    candidate_ids = {
        str(record.scanner.candidate_opportunity_id) for record in candidate_scanner_records
    }
    scan_ids = set(scanner_by_id)

    extra_decisions = set(decision_by_opportunity) - candidate_ids
    extra_candidate_outcomes = set(candidate_outcomes) - candidate_ids
    extra_scanner_outcomes = set(scanner_outcomes) - scan_ids
    if extra_decisions:
        _fail(
            ResearchIntegrityCode.CANDIDATE_INCONSISTENCY,
            f"Decision Intelligence contains unknown candidates: {sorted(extra_decisions)!r}",
        )
    if extra_candidate_outcomes:
        _fail(
            ResearchIntegrityCode.CANDIDATE_INCONSISTENCY,
            f"Forward Outcomes contain unknown candidates: {sorted(extra_candidate_outcomes)!r}",
        )
    if extra_scanner_outcomes:
        _fail(
            ResearchIntegrityCode.IDENTITY_MISMATCH,
            f"Scanner outcomes contain unknown scan ids: {sorted(extra_scanner_outcomes)!r}",
        )

    candidates = tuple(
        _build_candidate_record(
            research_run=research_run,
            source=source,
            scanner_record=record,
            decision_record=decision_by_opportunity.get(
                str(record.scanner.candidate_opportunity_id)
            ),
            outcome=candidate_outcomes.get(str(record.scanner.candidate_opportunity_id)),
        )
        for record in candidate_scanner_records
    )
    scanners = tuple(
        _build_scanner_record(
            research_run=research_run,
            source=source,
            scanner_record=record,
            outcome=scanner_outcomes.get(str(record.scanner_evaluation_id)),
        )
        for record in scanner_attribution.records
    )
    _validate_candidate_consistency(candidate_records=candidates, scanner_records=scanners)

    bundle = DecisionQualityResearchBundle.create(
        research_run=research_run,
        candidate_records=candidates,
        scanner_records=scanners,
    )
    if strict and (
        bundle.candidate_coverage.joined != bundle.candidate_coverage.total
        or bundle.scanner_coverage.joined != bundle.scanner_coverage.total
    ):
        raise ValueError("strict Decision Quality research join requires 100% expected joins")
    return bundle


__all__ = [
    "DecisionQualityIntegrityError",
    "build_decision_quality_research_bundle",
]
