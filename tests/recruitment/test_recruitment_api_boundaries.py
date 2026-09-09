from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTE = ROOT / "app" / "api" / "routes" / "recruitment.py"
API = ROOT / "app" / "recruitment" / "api.py"
ROUTER = ROOT / "app" / "api" / "router.py"


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return tuple(names)


def test_recruitment_api_boundary_has_no_live_risk_or_registry_dependencies() -> None:
    imports = _imports(ROUTE) + _imports(API)
    forbidden = (
        "app.trading.live",
        "app.trading.risk",
        "app.trading.broker",
        "app.exchange",
        "app.agents.registry",
    )
    for name in imports:
        assert not any(name.startswith(prefix) for prefix in forbidden), name


def test_recruitment_route_declares_only_get_decorators() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    assert "@router.get(" in source
    for method in ("post", "put", "patch", "delete"):
        assert f"@router.{method}(" not in source


def test_main_api_router_registers_recruitment_once() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert source.count("from app.api.routes.recruitment import router as recruitment_router") == 1
    assert source.count("api_router.include_router(recruitment_router)") == 1
