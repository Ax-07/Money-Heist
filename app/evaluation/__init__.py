"""Deterministic evaluation, AI economics, reputation and ablation layer."""

from importlib import import_module

from .ablation import (
    AblationAggregate,
    AblationComparison,
    AblationMetricDelta,
    AblationMetricStatus,
    AblationRunDescriptor,
    aggregate_ablation,
    compare_ablation,
)
from .adapters import (
    build_evaluation_source,
    execution_records_from_paper,
    trace_from_paper_pipeline,
    traces_from_paper_events,
    usage_from_ai_gateway,
)
from .agents import calculate_agent_metrics
from .ai_costs import calculate_ai_cost_metrics
from .exports import agent_metrics_to_csv, report_to_dict, report_to_json
from .lisbon import DeterministicLisbonReporter, self_funding_ratio
from .models import (
    AICostMetrics,
    AgentMetrics,
    CounterfactualOutcome,
    DataKind,
    EquityPoint,
    EvaluationReport,
    EvaluationSource,
    ExecutionRecord,
    LisbonEvaluationReport,
    Metric,
    MetricStatus,
    OpportunityTrace,
    SelfFundingRatio,
    SelfFundingStatus,
    TradingMetrics,
)
from .reputation import AgentReputationProfile, ReputationPolicy, build_agent_reputation
from .reputation_advisory import (
    AgentReputationAdvisoryReport,
    ReputationAdvisoryService,
    ReputationEvidenceProvenance,
    build_agent_state_evidence,
)
from .reputation_exports import (
    reputation_advisory_to_dict,
    reputation_advisory_to_json,
)
from .reputation_policy import (
    AgentStateEvidence,
    AgentStateRecommendation,
    DeterministicAgentStateAdvisor,
    EvidenceSufficiency,
    ReputationPolicyThresholds,
    StateRecommendationAction,
)
from .service import EvaluationService
from .trading import calculate_trading_metrics

_BATCH18B_LAZY_EXPORTS = {
    "AblationCampaignPlan": (".ablation_campaign", "AblationCampaignPlan"),
    "AblationCampaignVariant": (".ablation_campaign", "AblationCampaignVariant"),
    "AblationCampaignVariantKind": (
        ".ablation_campaign",
        "AblationCampaignVariantKind",
    ),
    "build_ablation_campaign": (".ablation_campaign", "build_ablation_campaign"),
    "build_variant_specialists": (".ablation_campaign", "build_variant_specialists"),
    "AblationCampaignExecutionReport": (
        ".ablation_campaign_execution",
        "AblationCampaignExecutionReport",
    ),
    "AblationCampaignExecutor": (
        ".ablation_campaign_execution",
        "AblationCampaignExecutor",
    ),
    "AblationVariantExecution": (
        ".ablation_campaign_execution",
        "AblationVariantExecution",
    ),
    "AblationVariantRuntime": (
        ".ablation_campaign_execution",
        "AblationVariantRuntime",
    ),
    "AblationVariantRuntimeFactory": (
        ".ablation_campaign_execution",
        "AblationVariantRuntimeFactory",
    ),
    "HistoricalReplayRunnerPort": (
        ".ablation_campaign_execution",
        "HistoricalReplayRunnerPort",
    ),
    "ablation_campaign_execution_to_dict": (
        ".ablation_campaign_exports",
        "ablation_campaign_execution_to_dict",
    ),
    "ablation_campaign_execution_to_json": (
        ".ablation_campaign_exports",
        "ablation_campaign_execution_to_json",
    ),
}


def __getattr__(name: str):
    target = _BATCH18B_LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "AICostMetrics",
    "AblationAggregate",
    "AblationCampaignExecutionReport",
    "AblationCampaignExecutor",
    "AblationCampaignPlan",
    "AblationCampaignVariant",
    "AblationCampaignVariantKind",
    "AblationComparison",
    "AblationMetricDelta",
    "AblationMetricStatus",
    "AblationRunDescriptor",
    "AblationVariantExecution",
    "AblationVariantRuntime",
    "AblationVariantRuntimeFactory",
    "AgentMetrics",
    "AgentReputationAdvisoryReport",
    "AgentReputationProfile",
    "AgentStateEvidence",
    "AgentStateRecommendation",
    "CounterfactualOutcome",
    "DataKind",
    "DeterministicAgentStateAdvisor",
    "DeterministicLisbonReporter",
    "EquityPoint",
    "EvaluationReport",
    "EvaluationService",
    "EvaluationSource",
    "EvidenceSufficiency",
    "ExecutionRecord",
    "HistoricalReplayRunnerPort",
    "LisbonEvaluationReport",
    "Metric",
    "MetricStatus",
    "OpportunityTrace",
    "ReputationAdvisoryService",
    "ReputationEvidenceProvenance",
    "ReputationPolicy",
    "ReputationPolicyThresholds",
    "SelfFundingRatio",
    "SelfFundingStatus",
    "StateRecommendationAction",
    "TradingMetrics",
    "ablation_campaign_execution_to_dict",
    "ablation_campaign_execution_to_json",
    "agent_metrics_to_csv",
    "aggregate_ablation",
    "build_ablation_campaign",
    "build_agent_reputation",
    "build_agent_state_evidence",
    "build_evaluation_source",
    "build_variant_specialists",
    "calculate_agent_metrics",
    "calculate_ai_cost_metrics",
    "calculate_trading_metrics",
    "compare_ablation",
    "execution_records_from_paper",
    "report_to_dict",
    "report_to_json",
    "reputation_advisory_to_dict",
    "reputation_advisory_to_json",
    "self_funding_ratio",
    "trace_from_paper_pipeline",
    "traces_from_paper_events",
    "usage_from_ai_gateway",
]
