from __future__ import annotations

from app.agents.prompts import CORE_PROMPTS, SPECIALIST_PROMPTS
from app.agents.registry import CORE_AGENT_REGISTRY, SPECIALIST_AGENT_REGISTRY
from app.intelligence.ai_gateway import PROMPT_TRANSPORT_VERSION
from app.portfolio.allocation_master_professor_shadow import (
    MASTER_PROFESSOR_SHADOW_INSTRUCTIONS_FR_V1,
)
from app.task_force.execution import TASK_FORCE_MEMBER_INSTRUCTIONS_FR_V1


def test_active_core_prompt_versions_are_native_french() -> None:
    expected = {"professor": "v8", "palermo": "v4", "lisbon": "v2"}
    actual = {entry.agent_id: entry.prompt_version for entry in CORE_AGENT_REGISTRY.list()}
    assert actual == expected
    for agent_id, version in expected.items():
        assert "Tu es" in CORE_PROMPTS.get(agent_id, version).instructions


def test_active_specialist_prompt_versions_are_native_french() -> None:
    expected = {
        "berlin": "v6",
        "tokyo": "v6",
        "nairobi": "v6",
        "rio": "v6",
        "denver": "v6",
    }
    actual = {
        entry.agent_id: entry.prompt_version
        for entry in SPECIALIST_AGENT_REGISTRY.list()
    }
    assert actual == expected
    for agent_id, version in expected.items():
        assert "Tu es" in SPECIALIST_PROMPTS.get(agent_id, version).instructions


def test_historical_english_prompts_remain_addressable() -> None:
    assert CORE_PROMPTS.get("professor", "v6").instructions.startswith("You are The Professor.")
    assert CORE_PROMPTS.get("palermo", "v3").instructions.startswith("You are Palermo")
    assert CORE_PROMPTS.get("lisbon", "v1").instructions.startswith("You are Lisbon")
    assert SPECIALIST_PROMPTS.get("berlin", "v5").instructions.startswith("You are Berlin")


def test_machine_contract_tokens_remain_canonical() -> None:
    professor = CORE_PROMPTS.get("professor", "v8").instructions
    berlin = SPECIALIST_PROMPTS.get("berlin", "v6").instructions
    for token in (
        "LONG",
        "SHORT",
        "NO_TRADE",
        "NO_ANALYSIS",
        "source_index",
        "source_key",
        "evidence_source_catalog",
        "execution_constraints",
        "allowed_trade_directions",
    ):
        assert token in professor
    for token in ("UNKNOWN", "NEUTRAL", "source_index", "source_key", "data_gaps"):
        assert token in berlin


def test_dynamic_agent_instructions_are_native_french() -> None:
    assert "Retourne uniquement" in TASK_FORCE_MEMBER_INSTRUCTIONS_FR_V1
    assert "Ne crée" in TASK_FORCE_MEMBER_INSTRUCTIONS_FR_V1
    assert "Tu es le Master Professor" in MASTER_PROFESSOR_SHADOW_INSTRUCTIONS_FR_V1
    assert "candidate_id" in MASTER_PROFESSOR_SHADOW_INSTRUCTIONS_FR_V1
    assert "evidence_refs" in MASTER_PROFESSOR_SHADOW_INSTRUCTIONS_FR_V1


def test_prompt_transport_version_changes_for_native_french_prompts() -> None:
    assert PROMPT_TRANSPORT_VERSION == "money-heist.prompt-transport.v4"
