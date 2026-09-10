from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.intelligence.ai_gateway.models import AIGatewayResult, AIUsageRecord
from app.portfolio.allocation import AllocationEnvelopeStatus, CrewAllocationEnvelope
from app.portfolio.allocation_advisory import MasterAllocationAdvisoryAction
from app.portfolio.allocation_evidence_analysis import build_master_allocation_evidence_analysis
from app.portfolio.allocation_master_professor_shadow import (
    MASTER_PROFESSOR_AGENT_ID,
    MasterProfessorAllocationCandidateSource,
    MasterProfessorShadowOutput,
    MasterProfessorShadowStatus,
    build_master_professor_allocation_candidate,
    build_master_professor_shadow_gateway_config,
    build_master_professor_shadow_gateway_request,
    run_master_professor_shadow_advisory,
    validate_master_professor_shadow_output,
)
from tests.portfolio.test_master_allocation_evidence_analysis import _evidence, _policy

USAGE_TIME = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)


def _candidate(
    *,
    candidate_id: str = "operator-balanced-v2",
    crew_a_capital: str = "55",
    crew_b_capital: str = "45",
):
    envelopes = (
        CrewAllocationEnvelope(
            system_id="crew-a",
            status=AllocationEnvelopeStatus.CONFIGURED,
            capital_ceiling_amount=Decimal(crew_a_capital),
            open_risk_ceiling_amount=Decimal("5.5"),
            gross_exposure_ceiling_amount=Decimal("44"),
        ),
        CrewAllocationEnvelope(
            system_id="crew-b",
            status=AllocationEnvelopeStatus.CONFIGURED,
            capital_ceiling_amount=Decimal(crew_b_capital),
            open_risk_ceiling_amount=Decimal("4.5"),
            gross_exposure_ceiling_amount=Decimal("36"),
        ),
    )
    return build_master_professor_allocation_candidate(
        candidate_id=candidate_id,
        proposed_envelopes=envelopes,
        source_ref=f"operator-scenario:{candidate_id}",
    )


def _context(*, candidates=None):
    policy = _policy()
    evidence = (
        _evidence(
            regime_label="TREND",
            regime_source_ref="operator-regime:v1",
        ),
    )
    analysis = build_master_allocation_evidence_analysis(
        current_allocation_policy=policy,
        evidence=evidence,
    )
    config = build_master_professor_shadow_gateway_config(
        prompt_version="batch21f.master-professor-shadow.v1",
        model_route="reasoning-medium",
        max_output_tokens=1400,
        source_ref="operator-ai-config:v1",
    )
    if candidates is None:
        candidates = (_candidate(),)
    return policy, evidence, analysis, tuple(candidates), config


def _output(
    analysis,
    policy,
    *,
    action: MasterAllocationAdvisoryAction = MasterAllocationAdvisoryAction.KEEP_CURRENT,
    selected_candidate_id: str | None = None,
    evidence_refs: tuple[str, ...] | None = None,
):
    if evidence_refs is None:
        evidence_refs = (analysis.fingerprint_sha256,)
    return MasterProfessorShadowOutput(
        analysis_id=analysis.analysis_id,
        analysis_fingerprint_sha256=analysis.fingerprint_sha256,
        current_policy_fingerprint_sha256=policy.fingerprint_sha256,
        action=action,
        selected_candidate_id=selected_candidate_id,
        rationale_codes=("SEALED_EVIDENCE_REVIEWED",),
        evidence_refs=evidence_refs,
        summary="SHADOW advisory only; operator review is required.",
        uncertainties=("AI_COST_IS_EXTERNAL_TO_HISTORICAL_TRADING_EVALUATION",),
    )


def _usage(request_id: UUID, *, attempt: int = 1, cost: str = "0.02") -> AIUsageRecord:
    return AIUsageRecord(
        usage_id=UUID(int=attempt),
        request_id=request_id,
        system_id="master-main",
        agent_id=MASTER_PROFESSOR_AGENT_ID,
        route_id="reasoning-medium-primary",
        model_id="model-test",
        input_tokens=100,
        cached_input_tokens=0,
        output_tokens=20,
        estimated_cost=Decimal(cost),
        latency_ms=50,
        attempt=attempt,
        created_at=USAGE_TIME,
    )


class _Gateway:
    def __init__(self, output, *, usage_records=None, request_id_override=None):
        self.output = output
        self.usage_records = usage_records
        self.request_id_override = request_id_override
        self.calls = 0
        self.request = None

    async def generate_structured(self, request, output_model):
        self.calls += 1
        self.request = request
        assert output_model is MasterProfessorShadowOutput
        records = self.usage_records or (_usage(request.request_id),)
        request_id = self.request_id_override or request.request_id
        return AIGatewayResult[MasterProfessorShadowOutput](
            request_id=request_id,
            route_id="reasoning-medium-primary",
            model_id="model-test",
            output=self.output,
            usage=records[-1],
            usage_records=records,
            attempts=max(item.attempt for item in records),
            provider_request_id="provider-request-1",
        )


def test_candidate_is_operator_owned_and_has_no_authority() -> None:
    candidate = _candidate()
    assert candidate.source is MasterProfessorAllocationCandidateSource.OPERATOR_SCENARIO
    assert candidate.operator_owned_values is True
    assert candidate.advisory_only is True
    assert candidate.auto_apply is False
    assert candidate.policy_mutation is False
    assert candidate.risk_authority is False
    assert candidate.live_authority is False


def test_candidate_builder_canonicalizes_envelope_order() -> None:
    candidate = _candidate()
    rebuilt = build_master_professor_allocation_candidate(
        candidate_id="x",
        proposed_envelopes=tuple(reversed(candidate.proposed_envelopes)),
        source_ref="operator:x",
    )
    assert tuple(item.system_id for item in rebuilt.proposed_envelopes) == ("crew-a", "crew-b")


def test_candidate_rejects_not_configured_envelope() -> None:
    with pytest.raises(ValueError, match="CONFIGURED"):
        build_master_professor_allocation_candidate(
            candidate_id="bad",
            proposed_envelopes=(
                CrewAllocationEnvelope(
                    system_id="crew-a",
                    status=AllocationEnvelopeStatus.NOT_CONFIGURED,
                    reason_code="MISSING",
                ),
            ),
            source_ref="operator:bad",
        )


def test_gateway_config_is_explicit_and_gateway_only() -> None:
    *_, config = _context()
    assert config.agent_id == MASTER_PROFESSOR_AGENT_ID
    assert config.mode == "SHADOW"
    assert config.gateway_required is True
    assert config.provider_direct_access is False
    assert config.live_authority is False


def test_gateway_config_rejects_zero_output_tokens() -> None:
    with pytest.raises(ValueError, match="max_output_tokens"):
        build_master_professor_shadow_gateway_config(
            prompt_version="v1",
            model_route="route",
            max_output_tokens=0,
            source_ref="operator",
        )


def test_output_schema_forbids_unknown_fields() -> None:
    policy, _, analysis, _, _ = _context()
    payload = _output(analysis, policy).model_dump(mode="json")
    payload["proposed_capital_ceiling"] = "999"
    with pytest.raises(ValidationError):
        MasterProfessorShadowOutput.model_validate(payload)


def test_output_cannot_claim_numeric_generation_or_live_authority() -> None:
    policy, _, analysis, _, _ = _context()
    payload = _output(analysis, policy).model_dump(mode="json")
    payload["numeric_allocation_generation"] = True
    with pytest.raises(ValidationError):
        MasterProfessorShadowOutput.model_validate(payload)
    payload = _output(analysis, policy).model_dump(mode="json")
    payload["live_authority"] = True
    with pytest.raises(ValidationError):
        MasterProfessorShadowOutput.model_validate(payload)


def test_propose_change_requires_candidate_id() -> None:
    policy, _, analysis, _, _ = _context()
    with pytest.raises(ValidationError, match="selected_candidate_id"):
        _output(
            analysis,
            policy,
            action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE,
        )


def test_keep_current_cannot_select_candidate() -> None:
    policy, _, analysis, _, _ = _context()
    with pytest.raises(ValidationError, match="selected_candidate_id"):
        _output(analysis, policy, selected_candidate_id="operator-balanced-v2")


def test_gateway_request_is_deterministic_and_uses_master_identity() -> None:
    policy, evidence, analysis, candidates, config = _context()
    first = build_master_professor_shadow_gateway_request(
        current_allocation_policy=policy,
        evidence=evidence,
        analysis=analysis,
        candidates=candidates,
        config=config,
    )
    second = build_master_professor_shadow_gateway_request(
        current_allocation_policy=policy,
        evidence=evidence,
        analysis=analysis,
        candidates=candidates,
        config=config,
    )
    assert first.request_id == second.request_id
    assert first.system_id == policy.master_portfolio_id
    assert first.agent_id == MASTER_PROFESSOR_AGENT_ID
    assert first.prompt_version == config.prompt_version
    assert first.model_route == config.model_route


def test_gateway_request_contains_only_operator_candidate_amounts() -> None:
    policy, evidence, analysis, candidates, config = _context()
    request = build_master_professor_shadow_gateway_request(
        current_allocation_policy=policy,
        evidence=evidence,
        analysis=analysis,
        candidates=candidates,
        config=config,
    )
    payload = json.loads(request.input_text)
    assert payload["operator_candidate_options"][0]["candidate_id"] == candidates[0].candidate_id
    assert "55" in request.input_text
    assert "candidate_id" in request.instructions
    assert "never invent" in request.instructions


def test_gateway_request_rejects_unconfigured_current_policy() -> None:
    policy, evidence, analysis, candidates, config = _context()
    unconfigured = _policy(configured=False)
    with pytest.raises(ValueError, match="CONFIGURED"):
        build_master_professor_shadow_gateway_request(
            current_allocation_policy=unconfigured,
            evidence=evidence,
            analysis=analysis,
            candidates=candidates,
            config=config,
        )


def test_gateway_request_rejects_candidate_membership_change() -> None:
    policy, evidence, analysis, _, config = _context()
    bad = build_master_professor_allocation_candidate(
        candidate_id="bad-membership",
        proposed_envelopes=(
            CrewAllocationEnvelope(
                system_id="crew-a",
                status=AllocationEnvelopeStatus.CONFIGURED,
                capital_ceiling_amount=Decimal("100"),
                open_risk_ceiling_amount=Decimal("5"),
                gross_exposure_ceiling_amount=Decimal("50"),
            ),
        ),
        source_ref="operator:bad-membership",
    )
    with pytest.raises(ValueError, match="membership"):
        build_master_professor_shadow_gateway_request(
            current_allocation_policy=policy,
            evidence=evidence,
            analysis=analysis,
            candidates=(bad,),
            config=config,
        )


def test_gateway_request_rejects_candidate_equal_to_current_policy() -> None:
    policy, evidence, analysis, _, config = _context()
    same = build_master_professor_allocation_candidate(
        candidate_id="same",
        proposed_envelopes=policy.envelopes,
        source_ref="operator:same",
    )
    with pytest.raises(ValueError, match="differ"):
        build_master_professor_shadow_gateway_request(
            current_allocation_policy=policy,
            evidence=evidence,
            analysis=analysis,
            candidates=(same,),
            config=config,
        )


def test_validate_output_rejects_unknown_evidence_reference() -> None:
    policy, _, analysis, candidates, _ = _context()
    output = _output(analysis, policy, evidence_refs=("f" * 64,))
    with pytest.raises(ValueError, match="outside"):
        validate_master_professor_shadow_output(
            output=output,
            current_allocation_policy=policy,
            analysis=analysis,
            candidates=candidates,
        )


def test_validate_output_rejects_unknown_candidate() -> None:
    policy, _, analysis, candidates, _ = _context()
    output = _output(
        analysis,
        policy,
        action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE,
        selected_candidate_id="does-not-exist",
    )
    with pytest.raises(ValueError, match="unknown"):
        validate_master_professor_shadow_output(
            output=output,
            current_allocation_policy=policy,
            analysis=analysis,
            candidates=candidates,
        )


def test_runtime_keep_current_builds_step1_advisory_report() -> None:
    policy, evidence, analysis, candidates, config = _context()
    gateway = _Gateway(_output(analysis, policy))
    result = asyncio.run(
        run_master_professor_shadow_advisory(
            gateway=gateway,
            current_allocation_policy=policy,
            evidence=evidence,
            analysis=analysis,
            candidates=candidates,
            config=config,
        )
    )
    assert gateway.calls == 1
    assert result.status is MasterProfessorShadowStatus.COMPLETED
    assert (
        result.advisory_report.recommendation.action
        is MasterAllocationAdvisoryAction.KEEP_CURRENT
    )
    assert result.advisory_report.recommendation.proposed_envelopes == policy.envelopes


def test_runtime_propose_change_maps_only_selected_operator_candidate() -> None:
    first = _candidate(candidate_id="candidate-a", crew_a_capital="55", crew_b_capital="45")
    second = _candidate(candidate_id="candidate-b", crew_a_capital="60", crew_b_capital="40")
    policy, evidence, analysis, candidates, config = _context(candidates=(first, second))
    gateway = _Gateway(
        _output(
            analysis,
            policy,
            action=MasterAllocationAdvisoryAction.PROPOSE_CHANGE,
            selected_candidate_id="candidate-b",
        )
    )
    result = asyncio.run(
        run_master_professor_shadow_advisory(
            gateway=gateway,
            current_allocation_policy=policy,
            evidence=evidence,
            analysis=analysis,
            candidates=candidates,
            config=config,
        )
    )
    assert (
        result.advisory_report.recommendation.action
        is MasterAllocationAdvisoryAction.PROPOSE_CHANGE
    )
    assert result.advisory_report.recommendation.proposed_envelopes == second.proposed_envelopes
    assert result.advisory_report.auto_apply is False
    assert result.advisory_report.policy_mutation is False


def test_runtime_abstain_has_no_proposed_envelopes() -> None:
    policy, evidence, analysis, candidates, config = _context()
    gateway = _Gateway(_output(analysis, policy, action=MasterAllocationAdvisoryAction.ABSTAIN))
    result = asyncio.run(
        run_master_professor_shadow_advisory(
            gateway=gateway,
            current_allocation_policy=policy,
            evidence=evidence,
            analysis=analysis,
            candidates=candidates,
            config=config,
        )
    )
    assert result.advisory_report.recommendation.action is MasterAllocationAdvisoryAction.ABSTAIN
    assert result.advisory_report.recommendation.proposed_envelopes == ()


def test_runtime_preserves_ai_usage_and_total_cost() -> None:
    policy, evidence, analysis, candidates, config = _context()
    request = build_master_professor_shadow_gateway_request(
        current_allocation_policy=policy,
        evidence=evidence,
        analysis=analysis,
        candidates=candidates,
        config=config,
    )
    records = (
        _usage(request.request_id, attempt=1, cost="0.02"),
        _usage(request.request_id, attempt=2, cost="0.03"),
    )
    gateway = _Gateway(_output(analysis, policy), usage_records=records)
    result = asyncio.run(
        run_master_professor_shadow_advisory(
            gateway=gateway,
            current_allocation_policy=policy,
            evidence=evidence,
            analysis=analysis,
            candidates=candidates,
            config=config,
        )
    )
    assert result.attempts == 2
    assert len(result.usage_records) == 2
    assert result.total_ai_cost_eur == Decimal("0.05")


def test_runtime_rejects_gateway_request_id_mismatch() -> None:
    policy, evidence, analysis, candidates, config = _context()
    gateway = _Gateway(
        _output(analysis, policy),
        request_id_override=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
    )
    with pytest.raises(ValueError, match="request_id"):
        asyncio.run(
            run_master_professor_shadow_advisory(
                gateway=gateway,
                current_allocation_policy=policy,
                evidence=evidence,
                analysis=analysis,
                candidates=candidates,
                config=config,
            )
        )


def test_runtime_result_exposes_no_trading_or_live_authority() -> None:
    policy, evidence, analysis, candidates, config = _context()
    result = asyncio.run(
        run_master_professor_shadow_advisory(
            gateway=_Gateway(_output(analysis, policy)),
            current_allocation_policy=policy,
            evidence=evidence,
            analysis=analysis,
            candidates=candidates,
            config=config,
        )
    )
    assert result.mode == "SHADOW"
    assert result.advisory_only is True
    assert result.operator_review_required is True
    assert result.auto_apply is False
    assert result.numeric_allocation_generation is False
    assert result.policy_mutation is False
    assert result.reservation_authority is False
    assert result.risk_authority is False
    assert result.admission_authority is False
    assert result.local_risk_override is False
    assert result.resize_authority is False
    assert result.registry_mutation is False
    assert result.broker_authority is False
    assert result.live_authority is False
    assert result.auto_execute is False


def test_runtime_does_not_mutate_policy_or_candidate_objects() -> None:
    policy, evidence, analysis, candidates, config = _context()
    policy_fp = policy.fingerprint_sha256
    candidate_fp = candidates[0].fingerprint_sha256
    asyncio.run(
        run_master_professor_shadow_advisory(
            gateway=_Gateway(_output(analysis, policy)),
            current_allocation_policy=policy,
            evidence=evidence,
            analysis=analysis,
            candidates=candidates,
            config=config,
        )
    )
    assert policy.fingerprint_sha256 == policy_fp
    assert candidates[0].fingerprint_sha256 == candidate_fp


def test_candidate_input_order_does_not_change_gateway_request_id() -> None:
    first = _candidate(candidate_id="candidate-a", crew_a_capital="55", crew_b_capital="45")
    second = _candidate(candidate_id="candidate-b", crew_a_capital="60", crew_b_capital="40")
    policy, evidence, analysis, _, config = _context(candidates=(first, second))
    forward = build_master_professor_shadow_gateway_request(
        current_allocation_policy=policy,
        evidence=evidence,
        analysis=analysis,
        candidates=(first, second),
        config=config,
    )
    reverse = build_master_professor_shadow_gateway_request(
        current_allocation_policy=policy,
        evidence=evidence,
        analysis=analysis,
        candidates=(second, first),
        config=config,
    )
    assert forward.request_id == reverse.request_id
    assert forward.input_text == reverse.input_text


def test_output_canonicalizes_rationale_and_evidence_references() -> None:
    policy, _, analysis, _, _ = _context()
    refs = (analysis.crew_analyses[0].fingerprint_sha256, analysis.fingerprint_sha256)
    output = MasterProfessorShadowOutput(
        analysis_id=analysis.analysis_id,
        analysis_fingerprint_sha256=analysis.fingerprint_sha256,
        current_policy_fingerprint_sha256=policy.fingerprint_sha256,
        action=MasterAllocationAdvisoryAction.KEEP_CURRENT,
        rationale_codes=("Z_REASON", "A_REASON"),
        evidence_refs=refs,
        summary="Review only.",
    )
    assert output.rationale_codes == ("A_REASON", "Z_REASON")
    assert output.evidence_refs == tuple(sorted(refs))


def test_runtime_invalid_context_does_not_call_gateway() -> None:
    policy, evidence, analysis, candidates, config = _context()
    gateway = _Gateway(_output(analysis, policy))
    unconfigured = _policy(configured=False)
    with pytest.raises(ValueError, match="CONFIGURED"):
        asyncio.run(
            run_master_professor_shadow_advisory(
                gateway=gateway,
                current_allocation_policy=unconfigured,
                evidence=evidence,
                analysis=analysis,
                candidates=candidates,
                config=config,
            )
        )
    assert gateway.calls == 0


def test_runtime_rejects_usage_route_mismatch() -> None:
    policy, evidence, analysis, candidates, config = _context()
    request = build_master_professor_shadow_gateway_request(
        current_allocation_policy=policy,
        evidence=evidence,
        analysis=analysis,
        candidates=candidates,
        config=config,
    )
    bad_usage = AIUsageRecord(
        usage_id=UUID(int=3),
        request_id=request.request_id,
        system_id="master-main",
        agent_id=MASTER_PROFESSOR_AGENT_ID,
        route_id="wrong-route",
        model_id="model-test",
        input_tokens=100,
        cached_input_tokens=0,
        output_tokens=20,
        estimated_cost=Decimal("0.02"),
        latency_ms=50,
        attempt=1,
        created_at=USAGE_TIME,
    )
    gateway = _Gateway(_output(analysis, policy), usage_records=(bad_usage,))
    with pytest.raises(ValueError, match="route_id"):
        asyncio.run(
            run_master_professor_shadow_advisory(
                gateway=gateway,
                current_allocation_policy=policy,
                evidence=evidence,
                analysis=analysis,
                candidates=candidates,
                config=config,
            )
        )
