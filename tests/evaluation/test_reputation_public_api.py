from __future__ import annotations

import ast
from pathlib import Path


def test_batch18_public_api_exports_are_declared() -> None:
    init_path = Path("app/evaluation/__init__.py")
    tree = ast.parse(init_path.read_text(encoding="utf-8"))
    exports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            assert isinstance(node.value, ast.List)
            exports = {
                item.value
                for item in node.value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }

    required = {
        "AblationComparison",
        "AgentReputationProfile",
        "ReputationPolicyThresholds",
        "AgentStateEvidence",
        "AgentStateRecommendation",
        "DeterministicAgentStateAdvisor",
        "AgentReputationAdvisoryReport",
        "ReputationAdvisoryService",
        "build_agent_state_evidence",
        "reputation_advisory_to_dict",
        "reputation_advisory_to_json",
    }
    assert required <= exports
