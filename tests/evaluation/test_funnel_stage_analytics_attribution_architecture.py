from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.evaluation.analytics_attribution.funnel_stage_attribution import (
    build_funnel_stage_analytics_attribution,
    project_funnel_stage_analytics_records,
)

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "app/evaluation/analytics_attribution/funnel_stage_attribution.py"
MODELS = ROOT / "app/evaluation/analytics_attribution/funnel_stage_models.py"


def imported_modules(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return tuple(names)


def app_python_files(relative: str) -> tuple[Path, ...]:
    base = ROOT / relative
    if not base.exists():
        return ()
    return tuple(sorted(base.rglob("*.py")))


def test_24b4_builder_depends_only_on_projection_and_canonical_helpers() -> None:
    imports = imported_modules(BUILDER)
    forbidden_prefixes = (
        "app.analytics",
        "app.market.scanner",
        "app.services.orchestration",
        "app.services.paper_pipeline",
        "app.trading.risk",
        "app.trading.paper",
        "app.trading.live",
        "app.evaluation.forward_outcomes",
        "app.evaluation.scanner_forward_outcomes",
        "app.evaluation.funnel_outcome_attribution",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imports
        for prefix in forbidden_prefixes
    )
    assert "app.evaluation.decision_intelligence.models" in imports
    assert "app.common.canonical" in imports


def test_24b4_models_have_no_business_service_dependencies() -> None:
    imports = imported_modules(MODELS)
    assert not any(module.startswith("app.") for module in imports)


def test_active_business_layers_do_not_import_24b4() -> None:
    active_roots = (
        "app/market/scanner",
        "app/services/decision_context",
        "app/agents",
        "app/services/orchestration",
        "app/services/paper_pipeline",
        "app/trading/risk",
        "app/trading/paper",
        "app/trading/live",
        "app/services/backtest",
    )
    forbidden = (
        "app.evaluation.analytics_attribution.funnel_stage_attribution",
        "app.evaluation.analytics_attribution.funnel_stage_models",
    )
    offenders: list[str] = []
    for relative in active_roots:
        for path in app_python_files(relative):
            imports = imported_modules(path)
            if any(module in forbidden for module in imports):
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders


def test_analytics_core_does_not_import_evaluation_attribution() -> None:
    offenders: list[str] = []
    forbidden_prefixes = (
        "app.evaluation.analytics_attribution",
        "app.evaluation.decision_intelligence",
        "app.evaluation.forward_outcomes",
        "app.evaluation.scanner_forward_outcomes",
        "app.evaluation.funnel_outcome_attribution",
    )
    for path in app_python_files("app/analytics"):
        imports = imported_modules(path)
        if any(
            module == prefix or module.startswith(f"{prefix}.")
            for module in imports
            for prefix in forbidden_prefixes
        ):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders


def test_builder_cannot_rematch_or_call_active_services() -> None:
    source = BUILDER.read_text(encoding="utf-8")
    forbidden_tokens = (
        "AnalyticsSnapshotResolver",
        "AnalyticsSnapshotIndex",
        "OpportunityAnalyticsLinker",
        "RiskEngine",
        "PaperBroker",
        "forward_outcome",
        "app.analytics",
    )
    for token in forbidden_tokens:
        assert token not in source


def test_public_builder_api_accepts_only_existing_24b2_projection() -> None:
    set_signature = inspect.signature(build_funnel_stage_analytics_attribution)
    record_signature = inspect.signature(project_funnel_stage_analytics_records)
    assert tuple(set_signature.parameters) == ("decision_records",)
    assert tuple(record_signature.parameters) == ("record",)
