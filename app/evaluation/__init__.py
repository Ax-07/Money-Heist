"""Batch 10 deterministic evaluation and AI economics layer."""

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
from .service import EvaluationService
from .trading import calculate_trading_metrics

__all__ = [
    "AICostMetrics",
    "AgentMetrics",
    "CounterfactualOutcome",
    "DataKind",
    "DeterministicLisbonReporter",
    "EquityPoint",
    "EvaluationReport",
    "EvaluationService",
    "EvaluationSource",
    "ExecutionRecord",
    "LisbonEvaluationReport",
    "Metric",
    "MetricStatus",
    "OpportunityTrace",
    "SelfFundingRatio",
    "SelfFundingStatus",
    "TradingMetrics",
    "agent_metrics_to_csv",
    "build_evaluation_source",
    "calculate_agent_metrics",
    "calculate_ai_cost_metrics",
    "calculate_trading_metrics",
    "execution_records_from_paper",
    "report_to_dict",
    "report_to_json",
    "self_funding_ratio",
    "trace_from_paper_pipeline",
    "traces_from_paper_events",
    "usage_from_ai_gateway",
]
