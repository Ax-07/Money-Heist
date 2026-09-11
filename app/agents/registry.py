from __future__ import annotations

from .models import AgentRegistryEntry, AgentRole, AgentState


class AgentRegistry:
    def __init__(
        self,
        entries: list[AgentRegistryEntry] | tuple[AgentRegistryEntry, ...] = (),
    ) -> None:
        self._entries = {entry.agent_id: entry for entry in entries}
        if len(self._entries) != len(entries):
            raise ValueError("duplicate agent_id")

    def get(self, agent_id: str) -> AgentRegistryEntry:
        try:
            return self._entries[agent_id]
        except KeyError as exc:
            raise KeyError(f"unknown agent: {agent_id}") from exc

    def list(self) -> tuple[AgentRegistryEntry, ...]:
        return tuple(self._entries[agent_id] for agent_id in sorted(self._entries))

    def available(self) -> tuple[AgentRegistryEntry, ...]:
        return tuple(entry for entry in self.list() if entry.state is not AgentState.DISABLED)


CORE_AGENT_REGISTRY = AgentRegistry(
    (
        AgentRegistryEntry(
            agent_id="professor",
            role=AgentRole.ORCHESTRATION,
            state=AgentState.ACTIVE,
            prompt_version="v2",
            model_route="core_reasoning",
            allowed_tools=(),
        ),
        AgentRegistryEntry(
            agent_id="palermo",
            role=AgentRole.RED_TEAM,
            state=AgentState.ACTIVE,
            prompt_version="v2",
            model_route="core_reasoning",
            allowed_tools=(),
        ),
        AgentRegistryEntry(
            agent_id="lisbon",
            role=AgentRole.AI_ECONOMICS,
            state=AgentState.ON_DEMAND,
            prompt_version="v1",
            model_route="economy",
            allowed_tools=(),
        ),
    )
)


SPECIALIST_AGENT_REGISTRY = AgentRegistry(
    (
        AgentRegistryEntry(
            agent_id="berlin",
            role=AgentRole.TREND_REGIME,
            state=AgentState.ACTIVE,
            prompt_version="v1",
            model_route="core_reasoning",
            allowed_tools=(),
            core=False,
        ),
        AgentRegistryEntry(
            agent_id="tokyo",
            role=AgentRole.MOMENTUM,
            state=AgentState.ACTIVE,
            prompt_version="v1",
            model_route="core_reasoning",
            allowed_tools=(),
            core=False,
        ),
        AgentRegistryEntry(
            agent_id="nairobi",
            role=AgentRole.MARKET_STRUCTURE,
            state=AgentState.ACTIVE,
            prompt_version="v1",
            model_route="core_reasoning",
            allowed_tools=(),
            core=False,
        ),
        AgentRegistryEntry(
            agent_id="rio",
            role=AgentRole.DERIVATIVES_POSITIONING,
            state=AgentState.ON_DEMAND,
            prompt_version="v1",
            model_route="core_reasoning",
            allowed_tools=(),
            core=False,
        ),
        AgentRegistryEntry(
            agent_id="denver",
            role=AgentRole.HISTORICAL_STATISTICS,
            state=AgentState.ON_DEMAND,
            prompt_version="v1",
            model_route="core_reasoning",
            allowed_tools=(),
            core=False,
        ),
    )
)


V1_AGENT_REGISTRY = AgentRegistry(
    (*CORE_AGENT_REGISTRY.list(), *SPECIALIST_AGENT_REGISTRY.list())
)
