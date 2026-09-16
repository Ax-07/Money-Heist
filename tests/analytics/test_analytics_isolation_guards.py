from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _python_files(path: Path):
    if path.is_file():
        yield path
        return
    if path.exists():
        yield from sorted(path.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    relative = path.relative_to(REPO_ROOT).with_suffix("")
    package_parts = list(relative.parts[:-1])
    imported: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 0:
            base = node.module or ""
        else:
            keep = len(package_parts) - (node.level - 1)
            prefix = package_parts[: max(keep, 0)]
            suffix = node.module.split(".") if node.module else []
            base = ".".join([*prefix, *suffix])
        if base:
            imported.add(base)
        for alias in node.names:
            if alias.name == "*":
                continue
            imported.add(".".join(item for item in (base, alias.name) if item))
    return imported


def _assert_no_import_prefix(paths: tuple[Path, ...], forbidden: tuple[str, ...]) -> None:
    violations: list[str] = []
    for root in paths:
        for path in _python_files(root):
            for target in sorted(_imports(path)):
                if any(target == prefix or target.startswith(f"{prefix}.") for prefix in forbidden):
                    violations.append(f"{path.relative_to(REPO_ROOT)} -> {target}")
    assert not violations, "forbidden imports:\n" + "\n".join(violations)


def test_decision_paths_do_not_import_analytics() -> None:
    _assert_no_import_prefix(
        (
            REPO_ROOT / "app/market/scanner",
            REPO_ROOT / "app/services/decision_context",
            REPO_ROOT / "app/agents",
            REPO_ROOT / "app/services/orchestration",
            REPO_ROOT / "app/services/paper_pipeline",
            REPO_ROOT / "app/trading/risk",
            REPO_ROOT / "app/trading/paper",
            REPO_ROOT / "app/trading/live",
        ),
        ("app.analytics",),
    )


def test_analytics_does_not_import_posthoc_outcomes_or_live() -> None:
    _assert_no_import_prefix(
        (REPO_ROOT / "app/analytics",),
        (
            "app.evaluation.forward_outcomes",
            "app.evaluation.scanner_forward_outcomes",
            "app.evaluation.funnel_outcome_attribution",
            "app.services.backtest.forward_outcomes",
            "app.services.backtest.scanner_forward_outcomes",
            "app.services.backtest.funnel_outcome_attribution",
            "app.trading.live",
        ),
    )


def test_backtest_business_identity_path_does_not_import_analytics() -> None:
    _assert_no_import_prefix(
        (
            REPO_ROOT / "app/services/backtest/models.py",
            REPO_ROOT / "app/services/backtest/reproducibility.py",
            REPO_ROOT / "app/services/backtest/runner.py",
        ),
        ("app.analytics",),
    )


def test_importing_analytics_does_not_load_posthoc_or_live_modules() -> None:
    code = r"""
import sys
import app.analytics
forbidden = (
    "app.services.backtest.forward_outcomes",
    "app.services.backtest.scanner_forward_outcomes",
    "app.services.backtest.funnel_outcome_attribution",
    "app.evaluation.forward_outcomes",
    "app.evaluation.scanner_forward_outcomes",
    "app.evaluation.funnel_outcome_attribution",
    "app.trading.live",
)
loaded = [name for name in sys.modules if any(
    name == prefix or name.startswith(prefix + ".") for prefix in forbidden
)]
if loaded:
    raise SystemExit("forbidden modules loaded: " + ", ".join(sorted(loaded)))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
