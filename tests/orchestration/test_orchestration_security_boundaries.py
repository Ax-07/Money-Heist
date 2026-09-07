import ast
import inspect
from pathlib import Path

from app.agents.registry import CORE_AGENT_REGISTRY, SPECIALIST_AGENT_REGISTRY
from app.services.orchestration.pipeline import OrchestrationPipeline


def test_orchestration_has_no_broker_exchange_secret_or_risk_engine_dependency():
    source = Path("app/services/orchestration/pipeline.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    assert all(not module.startswith("app.trading") for module in imported_modules)
    assert all("exchange" not in module.lower() for module in imported_modules)
    assert all("secret" not in module.lower() for module in imported_modules)

    parameters = inspect.signature(OrchestrationPipeline.__init__).parameters
    forbidden_parameter_fragments = ("broker", "exchange", "secret", "risk")
    assert all(
        not any(fragment in name.lower() for fragment in forbidden_parameter_fragments)
        for name in parameters
    )


def test_all_agents_reachable_by_batch08_still_have_no_privileged_tools():
    for agent_id in ("professor", "palermo"):
        assert CORE_AGENT_REGISTRY.get(agent_id).allowed_tools == ()
    for entry in SPECIALIST_AGENT_REGISTRY.list():
        assert entry.allowed_tools == ()
