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

from app.services.frontend_v2.analytics_overlays import (  # noqa: E402
    FrontendAnalyticsGeometryProjection,
    geometry_export_name,
)
from app.services.frontend_v2.decision_intelligence import (  # noqa: E402
    FrontendDecisionIntelligenceBundle,
    projection_export_name,
)

ROLES = ("DESIGN", "VALIDATION", "OOS")


def _load_shadow_attention_service() -> Any:
    """Load the isolated v0 package without importing app.evaluation.__init__."""

    package_name = "_money_heist_shadow_attention_v0"
    package_dir = PROJECT_ROOT / "app" / "evaluation" / "shadow_attention"
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_dir)]
    package.__package__ = package_name
    sys.modules[package_name] = package

    for module_name in ("models", "service"):
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

    return sys.modules[f"{package_name}.service"]


_SHADOW_SERVICE = _load_shadow_attention_service()
build_shadow_attention_report = _SHADOW_SERVICE.build_shadow_attention_report
shadow_attention_export_name = _SHADOW_SERVICE.shadow_attention_export_name


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


def backfill(campaign_id: str) -> None:
    campaign = _storage_root() / "campaigns" / campaign_id
    exports = campaign / "exports"
    if not campaign.is_dir():
        raise FileNotFoundError(f"campagne V2 persistée introuvable: {campaign}")

    print(f"Campagne : {campaign_id}")
    print("Shadow Attention v0 : backfill observation-only depuis artefacts 24C persistés.")
    for role in ROLES:
        bundle = FrontendDecisionIntelligenceBundle.model_validate_json(
            _read(exports / projection_export_name(role))
        )
        geometry = FrontendAnalyticsGeometryProjection.model_validate_json(
            _read(exports / geometry_export_name(role))
        )
        report = build_shadow_attention_report(
            period_role=role,
            scanner_projection=bundle.scanner,
            geometry=geometry,
        )
        target = exports / shadow_attention_export_name(role)
        _atomic_write(target, report.to_json())
        summary = report.summary
        print(
            f"{role}: evaluations={summary.scanner_evaluations} "
            f"scanner={summary.scanner_wakes} shadow={summary.shadow_wakes} "
            f"both={summary.both} scanner_only={summary.scanner_only} "
            f"shadow_only={summary.shadow_only} neither={summary.neither} "
            f"unavailable={summary.unavailable}"
        )
        print(
            "  raisons: "
            f"technical={summary.technical_event_wakes} "
            f"zigzag={summary.zigzag_confirmation_wakes} "
            f"pattern={summary.pattern_transition_wakes}"
        )
        print(f"  export: {target}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill Shadow Attention Gate v0 depuis les sidecars 24C persistés."
    )
    parser.add_argument("--campaign-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    backfill(args.campaign_id.strip())


if __name__ == "__main__":
    main()
