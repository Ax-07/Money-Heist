from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DECISION_QUALITY_IMPORT = "app.evaluation.decision_quality"


def _python_files(root: Path):
    if root.is_file():
        return (root,)
    if not root.exists():
        return ()
    return tuple(sorted(root.rglob("*.py")))


def _assert_no_decision_quality_import(root: Path) -> None:
    violations = []
    for path in _python_files(root):
        if DECISION_QUALITY_IMPORT in path.read_text(encoding="utf-8"):
            violations.append(path.relative_to(REPO_ROOT).as_posix())
    assert not violations, f"24D import forbidden from runtime boundary: {violations}"


def test_analytics_does_not_import_decision_quality() -> None:
    _assert_no_decision_quality_import(REPO_ROOT / "app/analytics")


def test_scanner_agents_risk_paper_and_live_do_not_import_decision_quality() -> None:
    roots = (
        REPO_ROOT / "app/market/scanner",
        REPO_ROOT / "app/agents",
        REPO_ROOT / "app/trading/risk",
        REPO_ROOT / "app/services/paper_pipeline",
        REPO_ROOT / "app/trading/paper",
        REPO_ROOT / "app/trading/live",
    )
    for root in roots:
        _assert_no_decision_quality_import(root)


def test_24b_remains_forward_outcome_and_decision_quality_independent() -> None:
    forbidden = (
        "app.evaluation.forward_outcomes",
        "app.evaluation.scanner_forward_outcomes",
        DECISION_QUALITY_IMPORT,
    )
    roots = (
        REPO_ROOT / "app/evaluation/analytics_attribution",
        REPO_ROOT / "app/evaluation/decision_intelligence",
    )
    violations = []
    for root in roots:
        for path in _python_files(root):
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in source:
                    violations.append((path.relative_to(REPO_ROOT).as_posix(), token))
    assert not violations, f"24B purity regression: {violations}"


def test_decision_quality_has_no_trading_authority_or_recompute_calls() -> None:
    root = REPO_ROOT / "app/evaluation/decision_quality"
    forbidden = (
        "DeterministicScanner",
        "ScannerConfig",
        "RiskEngine",
        "RiskProfile",
        "PaperBroker",
        "PaperTradingPipeline",
        "KrakenSpotLiveBroker",
        "BacktestConfig",
        "build_analytics_",
        "compute_forward_outcomes",
        "compute_scanner_forward_outcomes",
        "app.agents.prompts",
        "app.trading.live",
    )
    violations = []
    for path in _python_files(root):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in source:
                violations.append((path.relative_to(REPO_ROOT).as_posix(), token))
    assert not violations, f"24D must stay read-only/research-only: {violations}"
