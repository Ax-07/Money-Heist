from pathlib import Path
from types import SimpleNamespace

from app.analytics.models import AnalyticsPeriodRole
from app.analytics.research import (
    ANALYTICS_24A7_BUNDLE_VERSION,
    CONTEXT_RESOLVER_VERSION,
    SEQUENCE_RESOLVER_VERSION,
    AnalyticsAnchorSpec,
    AnalyticsContextDefinition,
    AnalyticsResearchRun,
    causal_research_component_versions,
)
from app.analytics.research.registry import AnalyticsAnchorType


def test_research_definition_changes_research_identity_not_analytics_identity(event_types):
    analytics = SimpleNamespace(analytics_run_id="base-analytics-run")
    anchor = AnalyticsAnchorSpec(
        AnalyticsAnchorType.TECHNICAL_EVENT,
        "1h",
        event_type=event_types[0]
    )
    d1 = AnalyticsContextDefinition.create(
        definition_id="ctx",
        revision_number=1,
        name="ctx",
        description="v1",
        anchor=anchor,
        conditions=(),
        timeframe="1h",
        origin_period_role=AnalyticsPeriodRole.DESIGN
    )
    d2 = AnalyticsContextDefinition.create(
        definition_id="ctx",
        revision_number=2,
        name="ctx",
        description="v2",
        anchor=anchor,
        conditions=(),
        timeframe="1h",
        origin_period_role=AnalyticsPeriodRole.DESIGN
    )
    r1 = AnalyticsResearchRun.create(analytics, d1)
    r2 = AnalyticsResearchRun.create(analytics, d2)
    assert r1.analytics_run_id == r2.analytics_run_id == "base-analytics-run"
    assert r1.research_run_id != r2.research_run_id


def test_research_package_has_no_forward_outcome_or_trading_dependencies():
    root = Path("app/analytics/research")
    forbidden = (
        "app.evaluation.forward_outcomes",
        "app.evaluation.scanner_forward_outcomes",
        "app.evaluation.funnel_outcome_attribution",
        "app.trading",
        "app.agents",
        "DecisionContextV1",
        "CandidateOpportunity",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for token in forbidden:
        assert token not in combined


def test_decision_path_does_not_import_research_package():
    roots = [Path("app/agents"), Path("app/trading"), Path("app/risk"), Path("app/services")]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            assert "app.analytics.research" not in path.read_text(encoding="utf-8")


def test_batch_24a7_component_manifest_installs_context_and_sequence_engines():
    versions = causal_research_component_versions()

    assert versions.analytics_bundle_version == ANALYTICS_24A7_BUNDLE_VERSION
    assert versions.context_engine_version == CONTEXT_RESOLVER_VERSION
    assert versions.sequence_engine_version == SEQUENCE_RESOLVER_VERSION
    assert "not-installed" not in versions.canonical_payload().values()
