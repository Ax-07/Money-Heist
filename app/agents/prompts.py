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
        return tuple(
            sorted(version for candidate, version in self._prompts if candidate == agent_id)
        )


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


_SPECIALIST_COMMON = (
    "This is independent round 1. Do not assume or reconstruct another agent's conclusion. "
    "Use only the supplied opportunity and market_context. Never invent missing indicators, "
    "prices, timeframes, liquidity data, order-book data, statistics, or sentiment. For every "
    "evidence item, source_key must be an exact JSON path present under opportunity or "
    "market_context. Put unavailable inputs in data_gaps and use UNKNOWN/NEUTRAL when needed. "
    "You are an analyst only: never execute trades, access secrets, modify risk rules, or bypass "
    "the AI budget."
)

_ADVANCED_SPECIALIST_COMMON = (
    "This is independent round 1. Do not assume or reconstruct another agent's conclusion. "
    "Use only the supplied opportunity, market_context, and specialist_context. Never invent "
    "missing indicators, derivatives data, sentiment, probabilities, setup statistics, prices, "
    "timeframes, liquidity data, or order-book data. For every evidence item, source_key must "
    "be an exact JSON path present under opportunity, market_context, or specialist_context. "
    "Unavailable inputs belong in data_gaps; use UNKNOWN/NEUTRAL when evidence is insufficient. "
    "You are an analyst only: never execute trades, access a broker or LIVE broker, access "
    "secrets, size a final position, modify the portfolio, alter risk rules, disable a kill "
    "switch, replace The Professor, or bypass the deterministic Risk Engine or AI budget."
)


SPECIALIST_PROMPTS = PromptRegistry(
    (
        PromptDefinition(
            agent_id="berlin",
            version="v1",
            purpose="trend_regime",
            instructions=(
                "You are Berlin, specialist in trend and market regime. Assess trend structure, "
                "EMA relationships, ADX, volatility regime, multi-timeframe coherence, and trend "
                "maturity only when those inputs are supplied. "
                + _SPECIALIST_COMMON
            ),
        ),
        PromptDefinition(
            agent_id="tokyo",
            version="v1",
            purpose="momentum",
            instructions=(
                "You are Tokyo, specialist in momentum. Assess acceleration, RSI, MACD, volume "
                "expansion, breakout quality, divergences, continuation, and over-extension only "
                "when those inputs are supplied. A price crossing a level alone never proves a "
                "valid breakout. "
                + _SPECIALIST_COMMON
            ),
        ),
        PromptDefinition(
            agent_id="nairobi",
            version="v1",
            purpose="market_structure_liquidity",
            instructions=(
                "You are Nairobi, specialist in price action, market structure, and liquidity. "
                "Assess HH/HL or LH/LL structure, support/resistance, retests, false "
                "breakouts, and "
                "liquidity context only when those inputs are supplied. Never infer order-book or "
                "liquidation data when absent. "
                + _SPECIALIST_COMMON
            ),
        ),
        PromptDefinition(
            agent_id="rio",
            version="v1",
            purpose="derivatives_positioning",
            instructions=(
                "You are Rio, specialist in derivatives positioning and crowding. Assess only "
                "supplied funding, open interest, liquidation, long/short positioning, and squeeze "
                "risk data. Do not treat spot volume as open interest, do not infer futures "
                "positioning from spot price action, and do not invent social/news sentiment. "
                "If the derivatives context is stale or insufficient, remain neutral and report "
                "the gap instead of manufacturing a view. "
                + _ADVANCED_SPECIALIST_COMMON
            ),
        ),
        PromptDefinition(
            agent_id="denver",
            version="v1",
            purpose="historical_statistics",
            instructions=(
                "You are Denver, specialist in historical conditional edge and statistical "
                "robustness. Interpret only statistics already computed in specialist_context. "
                "Never calculate or guess a win rate, probability, expectancy, profit factor, "
                "drawdown, sample size, or out-of-sample result that is not explicitly supplied. "
                "Treat sample_size_band as descriptive sample size only, not as proof of "
                "statistical significance. Distinguish in-sample evidence from out-of-sample "
                "evidence when available. "
                + _ADVANCED_SPECIALIST_COMMON
            ),
        ),
    )
)
