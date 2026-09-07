from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptDefinition:
    agent_id: str
    version: str
    purpose: str
    instructions: str


class PromptRegistry:
    def __init__(
        self,
        prompts: list[PromptDefinition] | tuple[PromptDefinition, ...] = (),
    ) -> None:
        self._prompts: dict[tuple[str, str], PromptDefinition] = {}
        for prompt in prompts:
            self.register(prompt)

    def register(self, prompt: PromptDefinition) -> None:
        key = (prompt.agent_id, prompt.version)
        if key in self._prompts:
            raise ValueError(f"prompt already registered: {key}")
        self._prompts[key] = prompt

    def get(self, agent_id: str, version: str) -> PromptDefinition:
        try:
            return self._prompts[(agent_id, version)]
        except KeyError as exc:
            raise KeyError(f"unknown prompt version: {agent_id}@{version}") from exc

    def versions(self, agent_id: str) -> tuple[str, ...]:
        return tuple(sorted(version for candidate, version in self._prompts if candidate == agent_id))


CORE_PROMPTS = PromptRegistry(
    (
        PromptDefinition(
            agent_id="professor",
            version="v1",
            purpose="orchestration",
            instructions=(
                "You are The Professor. Orchestrate analysis only. Never execute trades, access "
                "secrets, alter risk limits, bypass the Risk Engine, or bypass the AI budget. "
                "NO_TRADE and NO_ANALYSIS are first-class outcomes."
            ),
        ),
        PromptDefinition(
            agent_id="palermo",
            version="v1",
            purpose="contradiction",
            instructions=(
                "You are Palermo, the red team. Attack the provisional thesis, identify missing "
                "checks and reasons to reject. You are an analyst only and have no broker, secret, "
                "risk, or budget override authority."
            ),
        ),
        PromptDefinition(
            agent_id="lisbon",
            version="v1",
            purpose="ai_economics",
            instructions=(
                "You are Lisbon, CFO for AI compute. Evaluate AI cost efficiency and recommend "
                "agent states. Never change trading risk limits, secrets, broker state, or hard AI "
                "budget caps."
            ),
        ),
    )
)
