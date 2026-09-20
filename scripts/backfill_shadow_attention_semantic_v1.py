from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ROLES = ("DESIGN", "VALIDATION", "OOS")


def _load_shadow_package() -> tuple[Any, Any]:
    """Load v0 models + semantic v1 without importing app.evaluation.__init__."""

    package_name = "_money_heist_shadow_attention_semantic_v1"
    package_dir = PROJECT_ROOT / "app" / "evaluation" / "shadow_attention"
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_dir)]
    package.__package__ = package_name
    sys.modules[package_name] = package

    loaded: dict[str, Any] = {}
    for module_name in ("models", "semantic_v1"):
        qualified = f"{package_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(
            qualified,
            package_dir / f"{module_name}.py",
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"impossible de charger {qualified}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified] = module
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded["models"], loaded["semantic_v1"]


_MODELS, _SEMANTIC = _load_shadow_package()
ShadowAttentionReport = _MODELS.ShadowAttentionReport
build_semantic_attention_v1_report = _SEMANTIC.build_semantic_attention_v1_report
semantic_attention_v1_export_name = _SEMANTIC.semantic_attention_v1_export_name


def _storage_root() -> Path:
    configured = os.getenv("MONEY_HEIST_FRONTEND_V2_STORAGE_DIR", "").strip()
    root = (
        Path(configured)
        if configured
        else PROJECT_ROOT / ".money-heist" / "frontend-v2"
    )
    return root.resolve()


def _read(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"artefact persisté introuvable: {path}")
    return path.read_text(encoding="utf-8")


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _v0_export_name(role: str) -> str:
    return f"shadow-attention-v0-{role.lower()}.json"


def backfill(campaign_id: str) -> None:
    campaign = _storage_root() / "campaigns" / campaign_id
    exports = campaign / "exports"
    if not campaign.is_dir():
        raise FileNotFoundError(f"campagne V2 persistée introuvable: {campaign}")

    print(f"Campagne : {campaign_id}")
    print("Shadow Attention Semantic v1 : backfill depuis exports v0 persistés.")
    print("Policy figée; aucun outcome, direction de trade ou replay métier utilisé.")
    for role in ROLES:
        source = ShadowAttentionReport.model_validate_json(
            _read(exports / _v0_export_name(role))
        )
        report = build_semantic_attention_v1_report(source)
        target = exports / semantic_attention_v1_export_name(role)
        _atomic_write(target, report.to_json())
        summary = report.summary
        rate = (
            100.0 * summary.shadow_wakes / summary.scanner_evaluations
            if summary.scanner_evaluations
            else 0.0
        )
        coverage = (
            100.0 * summary.both / summary.scanner_wakes
            if summary.scanner_wakes
            else 0.0
        )
        print(
            f"{role}: evaluations={summary.scanner_evaluations} "
            f"shadow={summary.shadow_wakes} ({rate:.2f}%) "
            f"scanner={summary.scanner_wakes} both={summary.both} "
            f"coverage={coverage:.2f}% shadow_only={summary.shadow_only}"
        )
        print(
            "  clauses: "
            f"tech2={summary.diverse_technical_family_wakes} "
            f"tech+zigzag={summary.technical_plus_zigzag_wakes} "
            f"mature_pattern={summary.mature_pattern_transition_wakes} "
            f"multi={summary.multi_clause_wakes}"
        )
        print(f"  export: {target}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill Shadow Attention Semantic v1 depuis Shadow Attention v0."
    )
    parser.add_argument("--campaign-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    backfill(args.campaign_id.strip())


if __name__ == "__main__":
    main()
