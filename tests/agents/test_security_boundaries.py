import pytest
from pydantic import ValidationError

from app.agents.models import AgentRegistryEntry, AgentRole, AgentState


def test_registry_entry_rejects_privileged_tool_names():
    for tool in (
        "broker.submit_order",
        "exchange_request",
        "get_secret",
        "risk_engine.override",
        "withdraw",
    ):
        with pytest.raises(ValidationError):
            AgentRegistryEntry(
                agent_id="x",
                role=AgentRole.RED_TEAM,
                state=AgentState.SHADOW,
                prompt_version="v1",
                model_route="x",
                allowed_tools=(tool,),
            )
