from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Protocol

from app.intelligence.ai_gateway.models import ProviderRequest, ProviderResponse


class MockProviderPort(Protocol):
    async def complete(self, request: ProviderRequest) -> ProviderResponse: ...


def adapt_mock_specialist_evidence_v3(
    request: ProviderRequest,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Adapt deterministic MOCK specialist evidence to the strict v3 provider schema.

    LIVE_EVAL is unaffected: this helper is used only by deterministic MOCK
    providers. Canonical source_key strings are accepted only when they are
    exact members of the request's deterministic allowed path catalogue.
    """

    if request.metadata.get("prompt_version") != "v3":
        return payload

    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return payload

    try:
        request_payload = json.loads(request.input_text)
    except json.JSONDecodeError as exc:
        raise ValueError("v3 MOCK specialist request input must be valid JSON") from exc
    if not isinstance(request_payload, dict):
        raise ValueError("v3 MOCK specialist request input must be a JSON object")

    raw_allowed = request_payload.get("allowed_evidence_source_keys")
    if not isinstance(raw_allowed, list) or not all(
        isinstance(item, str) for item in raw_allowed
    ):
        raise ValueError("v3 MOCK specialist request has no valid allowed path catalogue")

    index_by_key = {key: index for index, key in enumerate(raw_allowed)}
    converted: list[dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("v3 MOCK specialist evidence item must be an object")
        if "source_index" in item:
            converted.append(dict(item))
            continue

        source_key = item.get("source_key")
        if not isinstance(source_key, str) or source_key not in index_by_key:
            raise ValueError(
                "v3 MOCK specialist evidence references a non-allowed source_key"
            )
        converted_item = {
            key: value for key, value in item.items() if key != "source_key"
        }
        converted_item["source_index"] = index_by_key[source_key]
        converted.append(converted_item)

    adapted = dict(payload)
    adapted["evidence"] = converted
    return adapted


class DeterministicAdvancedSpecialistMockProvider:
    """Add Rio/Denver MOCK support without changing legacy deterministic responses.

    All legacy schemas are delegated byte-for-byte to ``fallback``. ProfessorPlan is
    delegated too unless a context-gated advanced specialist is actually available.
    This keeps historical MOCK behavior unchanged when Rio/Denver are not selectable.
    """

    provider_name = "mock"

    def __init__(self, fallback: MockProviderPort) -> None:
        self.fallback = fallback

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        if request.schema_name == "DenverAnalysis":
            return self._response(request, self._denver(self._context(request)))
        if request.schema_name == "RioAnalysis":
            return self._response(request, self._rio(self._context(request)))
        if request.schema_name == "ProfessorPlan":
            return await self._professor_plan(request)
        return await self.fallback.complete(request)

    async def _professor_plan(self, request: ProviderRequest) -> ProviderResponse:
        context = self._context(request)
        available = context.get("available_agents")
        available_agents = {
            str(agent_id) for agent_id in available if isinstance(agent_id, str)
        } if isinstance(available, list) else set()
        advanced = [
            agent_id for agent_id in ("denver", "rio") if agent_id in available_agents
        ]
        legacy = await self.fallback.complete(request)
        if not advanced:
            return legacy

        payload = json.loads(legacy.output_text)
        if payload.get("decision") == "NO_ANALYSIS":
            return legacy
        selected = [str(item) for item in payload.get("selected_agents", [])]
        limit = 2 if payload.get("decision") == "MINI_CREW" else len(available_agents)
        for agent_id in advanced:
            if agent_id not in selected and len(selected) < limit:
                selected.append(agent_id)
        if selected == payload.get("selected_agents", []):
            return legacy
        payload["selected_agents"] = selected
        rationale = [str(item) for item in payload.get("rationale", [])]
        rationale.append("advanced specialist context available")
        payload["rationale"] = rationale
        return self._response_from_legacy(legacy, payload)

    @staticmethod
    def _context(request: ProviderRequest) -> dict[str, Any]:
        try:
            payload = json.loads(request.input_text)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _specialist_context(payload: dict[str, Any]) -> dict[str, Any]:
        context = payload.get("specialist_context")
        return context if isinstance(context, dict) else {}

    @classmethod
    def _denver(cls, payload: dict[str, Any]) -> dict[str, Any]:
        context = cls._specialist_context(payload)
        stats_id = str(context.get("stats_id") or "").strip()
        sample_size_band = str(context.get("sample_size_band") or "").strip()
        if not stats_id or sample_size_band not in {"NONE", "SMALL", "MEDIUM", "LARGE"}:
            raise ValueError("Denver MOCK requires grounded stats_id and sample_size_band")
        sample_count = int(context.get("sample_count") or 0)
        expectancy_raw = context.get("expectancy")
        expectancy = None if expectancy_raw is None else Decimal(str(expectancy_raw))
        if expectancy is None:
            historical_edge = "UNKNOWN"
        elif expectancy > 0:
            historical_edge = "POSITIVE"
        elif expectancy < 0:
            historical_edge = "NEGATIVE"
        else:
            historical_edge = "INCONCLUSIVE"

        if sample_size_band == "SMALL":
            confidence = 0.35
            robustness = "FRAGILE"
        elif sample_size_band in {"MEDIUM", "LARGE"}:
            confidence = 0.55 if sample_size_band == "MEDIUM" else 0.65
            robustness = "MIXED"
        else:
            confidence = 0.2
            robustness = "UNKNOWN"

        evidence = []
        if expectancy is not None:
            evidence.append(
                {
                    "source_key": "specialist_context.expectancy",
                    "observation": "deterministic historical expectancy supplied by Batch 16 stats",
                }
            )
        if sample_count > 0:
            evidence.append(
                {
                    "source_key": "specialist_context.sample_count",
                    "observation": (
                        "deterministic historical sample count supplied by Batch 16 stats"
                    ),
                }
            )

        return {
            "agent": "denver",
            "stance": "NEUTRAL",
            "confidence": confidence,
            "evidence": evidence,
            "risks": ["historical association does not prove future performance"],
            "invalidation": ["setup definition or source strategy version changes"],
            "data_gaps": ["directional edge is not inferred from setup-level statistics"],
            "source_stats_id": stats_id,
            "historical_edge": historical_edge,
            "sample_size_band": sample_size_band,
            "robustness": robustness,
            "oos_consistency": "UNAVAILABLE",
        }

    @classmethod
    def _rio(cls, payload: dict[str, Any]) -> dict[str, Any]:
        context = cls._specialist_context(payload)
        data_quality = str(context.get("data_quality") or "").strip()
        if data_quality not in {"RELIABLE", "DEGRADED", "INSUFFICIENT"}:
            raise ValueError("Rio MOCK requires grounded data_quality")
        funding = context.get("funding_rate")
        oi_change = context.get("open_interest_change_pct")
        long_liq = context.get("long_liquidations_notional")
        short_liq = context.get("short_liquidations_notional")

        if funding is None:
            funding_state = "UNKNOWN"
        elif Decimal(str(funding)) > 0:
            funding_state = "POSITIVE"
        elif Decimal(str(funding)) < 0:
            funding_state = "NEGATIVE"
        else:
            funding_state = "NEUTRAL"

        if oi_change is None:
            open_interest_state = "UNKNOWN"
        elif Decimal(str(oi_change)) > 0:
            open_interest_state = "RISING"
        elif Decimal(str(oi_change)) < 0:
            open_interest_state = "FALLING"
        else:
            open_interest_state = "STABLE"

        if long_liq is None or short_liq is None:
            liquidation_state = "UNKNOWN"
        else:
            long_value = Decimal(str(long_liq))
            short_value = Decimal(str(short_liq))
            if long_value == 0 and short_value == 0:
                liquidation_state = "QUIET"
            elif long_value > short_value:
                liquidation_state = "LONG_DOMINATED"
            elif short_value > long_value:
                liquidation_state = "SHORT_DOMINATED"
            else:
                liquidation_state = "BALANCED"

        evidence = []
        for key in (
            "funding_rate",
            "open_interest_change_pct",
            "long_liquidations_notional",
            "short_liquidations_notional",
        ):
            if context.get(key) is not None:
                evidence.append(
                    {
                        "source_key": f"specialist_context.{key}",
                        "observation": "deterministic derivatives input supplied to MOCK Rio",
                    }
                )
                break

        return {
            "agent": "rio",
            "stance": "NEUTRAL",
            "confidence": 0.45,
            "evidence": evidence,
            "risks": ["derivatives context alone does not authorize a directional trade"],
            "invalidation": ["derivatives context becomes stale or unavailable"],
            "data_gaps": ["MOCK does not infer external sentiment"],
            "positioning_regime": "UNKNOWN",
            "funding_state": funding_state,
            "open_interest_state": open_interest_state,
            "liquidation_state": liquidation_state,
            "squeeze_risk": "UNKNOWN",
            "data_quality": data_quality,
        }

    @staticmethod
    def _response(
        request: ProviderRequest,
        payload: dict[str, Any],
    ) -> ProviderResponse:
        from app.intelligence.ai_gateway.models import TokenUsage

        payload = adapt_mock_specialist_evidence_v3(request, payload)
        return ProviderResponse(
            provider_request_id=f"mock-advanced-{request.request_id}",
            model_id=request.model_id,
            output_text=json.dumps(payload, separators=(",", ":"), sort_keys=True),
            usage=TokenUsage(input_tokens=0, cached_input_tokens=0, output_tokens=0),
            latency_ms=0,
        )

    @staticmethod
    def _response_from_legacy(
        legacy: ProviderResponse,
        payload: dict[str, Any],
    ) -> ProviderResponse:
        return ProviderResponse(
            provider_request_id=legacy.provider_request_id,
            model_id=legacy.model_id,
            output_text=json.dumps(payload, separators=(",", ":"), sort_keys=True),
            usage=legacy.usage,
            latency_ms=legacy.latency_ms,
        )


__all__ = [
    "DeterministicAdvancedSpecialistMockProvider",
    "MockProviderPort",
    "adapt_mock_specialist_evidence_v3",
]
