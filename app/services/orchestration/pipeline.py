from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from app.agents.core import Palermo, StructuredGateway, TheProfessor
from app.agents.models import AgentState, EvidenceReference, ProfessorPlan
from app.agents.specialists import (
    Berlin,
    Nairobi,
    SpecialistAgent,
    Tokyo,
    UngroundedEvidenceError,
)
from app.intelligence.ai_gateway.budget import AIBudgetLedger
from app.intelligence.ai_gateway.errors import (
    AIProviderError,
    BudgetExceededError,
    StructuredOutputError,
)
from app.intelligence.ai_gateway.models import AIGatewayResult
from app.market.features.models import FeatureSnapshot
from app.market.scanner.models import CandidateOpportunity

from .compute_gate import ComputeGate
from .models import (
    AgentCallAudit,
    ComputeLevel,
    OrchestrationResult,
    PalermoRunRecord,
    PipelineAuditEvent,
    PipelineFailure,
    PipelineFailureCode,
    PipelineStatus,
    ProfessorFinalDecision,
    SpecialistRunRecord,
    TradeProposal,
)


class InvalidProfessorPlanError(ValueError):
    pass


class InvalidPipelineContextError(ValueError):
    pass


def _leaf_paths(value: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            paths.update(_leaf_paths(nested, child))
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            child = f"{prefix}.{index}" if prefix else str(index)
            paths.update(_leaf_paths(nested, child))
    elif prefix:
        paths.add(prefix)
    return paths


def _assert_grounded_final_evidence(
    evidence: list[EvidenceReference],
    *,
    opportunity: dict[str, Any],
    market_context: dict[str, Any],
    specialist_analyses: list[dict[str, Any]],
    palermo_review: dict[str, Any],
) -> None:
    available = _leaf_paths(
        {
            "opportunity": opportunity,
            "market_context": market_context,
            "specialist_analyses": specialist_analyses,
            "palermo_review": palermo_review,
        }
    )
    missing = sorted(item.source_key for item in evidence if item.source_key not in available)
    if missing:
        raise UngroundedEvidenceError(
            "Professor evidence references unavailable input fields: " + ", ".join(missing)
        )


class OrchestrationPipeline:
    """Batch 08 ends at TradeProposal; it owns no broker/exchange/risk capability."""

    def __init__(
        self,
        *,
        gateway: StructuredGateway,
        budget: AIBudgetLedger,
        compute_gate: ComputeGate | None = None,
        professor: TheProfessor | None = None,
        palermo: Palermo | None = None,
        specialists: Mapping[str, SpecialistAgent] | None = None,
    ) -> None:
        self._budget = budget
        self.compute_gate = compute_gate or ComputeGate(budget)
        self.professor = professor or TheProfessor(gateway)
        self.palermo = palermo or Palermo(gateway)
        self.specialists: dict[str, SpecialistAgent] = dict(
            specialists
            or {
                "berlin": Berlin(gateway),
                "tokyo": Tokyo(gateway),
                "nairobi": Nairobi(gateway),
            }
        )

    async def run(
        self,
        *,
        opportunity: CandidateOpportunity,
        market_context: FeatureSnapshot,
        now: datetime | None = None,
    ) -> OrchestrationResult:
        events: list[PipelineAuditEvent] = []
        calls: list[AgentCallAudit] = []
        specialist_runs: list[SpecialistRunRecord] = []
        gate_decision = None
        professor_plan = None
        palermo_run = None
        final_decision = None

        def event(stage: str, status: str, **details: Any) -> None:
            events.append(
                PipelineAuditEvent(
                    sequence=len(events) + 1,
                    stage=stage,
                    status=status,
                    details=details,
                )
            )

        try:
            opportunity_uuid = self._validate_context(opportunity, market_context)
        except (ValueError, InvalidPipelineContextError) as exc:
            event("context", "FAILED", reason=str(exc))
            return self._result(
                status=PipelineStatus.FAILED,
                opportunity=opportunity,
                gate_decision=None,
                professor_plan=None,
                specialist_runs=(),
                palermo_run=None,
                final_decision=None,
                trade_proposal=None,
                failure=PipelineFailure(
                    code=PipelineFailureCode.INVALID_CONTEXT,
                    stage="context",
                    message=str(exc),
                ),
                calls=calls,
                events=events,
            )

        opportunity_payload = opportunity.model_dump(mode="json")
        # Critical: absent optional market fields are omitted, so they cannot be cited as evidence.
        market_payload = market_context.model_dump(mode="json", exclude_none=True)
        event(
            "context",
            "COMPLETED",
            opportunity_id=opportunity.opportunity_id,
            snapshot_id=market_context.snapshot_id,
            feature_version=market_context.feature_version,
            scanner_version=opportunity.scanner_version,
        )

        gate_decision = self.compute_gate.evaluate(opportunity, now=now)
        event(
            "compute_gate",
            "COMPLETED" if gate_decision.allows_ai else "SKIPPED",
            level=gate_decision.level.value,
            reason=gate_decision.reason.value,
            remaining_budget_eur=str(gate_decision.remaining_budget_eur),
        )
        if not gate_decision.allows_ai:
            return self._result(
                status=PipelineStatus.NO_ANALYSIS,
                opportunity=opportunity,
                gate_decision=gate_decision,
                professor_plan=None,
                specialist_runs=(),
                palermo_run=None,
                final_decision=None,
                trade_proposal=None,
                failure=None,
                calls=calls,
                events=events,
            )

        available_agents = self._available_specialists()
        try:
            plan_result = await self.professor.plan(
                system_id=opportunity.system_id,
                opportunity=opportunity_payload,
                market_context=market_payload,
                available_agents=available_agents,
                remaining_budget_eur=float(self._budget.snapshot().remaining_eur),
                opportunity_id=opportunity_uuid,
            )
            professor_plan = plan_result.output
            calls.append(self._call_audit(plan_result, self.professor, "professor_plan"))
            self._validate_plan(professor_plan, gate_decision.level, available_agents)
            event(
                "professor_plan",
                "COMPLETED",
                decision=professor_plan.decision,
                selected_agents=list(professor_plan.selected_agents),
                request_id=str(plan_result.request_id),
            )
        except InvalidProfessorPlanError as exc:
            event("professor_plan", "FAILED", reason=str(exc))
            return self._failed(
                opportunity=opportunity,
                gate_decision=gate_decision,
                professor_plan=professor_plan,
                specialist_runs=specialist_runs,
                palermo_run=palermo_run,
                final_decision=final_decision,
                code=PipelineFailureCode.INVALID_PROFESSOR_PLAN,
                stage="professor_plan",
                message=str(exc),
                agent_id="professor",
                calls=calls,
                events=events,
            )
        except BudgetExceededError as exc:
            event("professor_plan", "FAILED", reason="budget")
            return self._failed_budget(
                opportunity,
                gate_decision,
                professor_plan,
                specialist_runs,
                palermo_run,
                final_decision,
                "professor_plan",
                "professor",
                exc,
                calls,
                events,
            )
        except StructuredOutputError as exc:
            event("professor_plan", "FAILED", reason="structured_output")
            return self._failed(
                opportunity=opportunity,
                gate_decision=gate_decision,
                professor_plan=professor_plan,
                specialist_runs=specialist_runs,
                palermo_run=palermo_run,
                final_decision=final_decision,
                code=PipelineFailureCode.INVALID_PROFESSOR_PLAN,
                stage="professor_plan",
                message=str(exc),
                agent_id="professor",
                calls=calls,
                events=events,
            )
        except AIProviderError as exc:
            return self._provider_failure(
                opportunity,
                gate_decision,
                professor_plan,
                specialist_runs,
                palermo_run,
                final_decision,
                "professor_plan",
                "professor",
                exc,
                calls,
                events,
            )

        if professor_plan.decision == "NO_ANALYSIS":
            event("specialists", "SKIPPED", reason="professor_no_analysis")
            return self._result(
                status=PipelineStatus.NO_ANALYSIS,
                opportunity=opportunity,
                gate_decision=gate_decision,
                professor_plan=professor_plan,
                specialist_runs=(),
                palermo_run=None,
                final_decision=None,
                trade_proposal=None,
                failure=None,
                calls=calls,
                events=events,
            )

        selected = list(professor_plan.selected_agents)
        event("specialists_independent_round_1", "STARTED", selected_agents=selected)
        specialist_outcomes = await asyncio.gather(
            *(
                self.specialists[agent_id].analyze(
                    system_id=opportunity.system_id,
                    opportunity=copy.deepcopy(opportunity_payload),
                    market_context=copy.deepcopy(market_payload),
                    opportunity_id=opportunity_uuid,
                )
                for agent_id in selected
            ),
            return_exceptions=True,
        )

        specialist_failure: tuple[str, BaseException] | None = None
        for agent_id, outcome in zip(selected, specialist_outcomes, strict=True):
            if isinstance(outcome, BaseException):
                if specialist_failure is None:
                    specialist_failure = (agent_id, outcome)
                continue
            agent = self.specialists[agent_id]
            calls.append(self._call_audit(outcome, agent, "specialist_independent_round_1"))
            specialist_runs.append(
                SpecialistRunRecord(
                    agent_id=agent_id,
                    request_id=outcome.request_id,
                    prompt_version=agent.prompt.version,
                    route_id=outcome.route_id,
                    model_id=outcome.model_id,
                    analysis=outcome.output,
                )
            )

        if specialist_failure is not None:
            agent_id, exc = specialist_failure
            event(
                "specialists_independent_round_1",
                "FAILED",
                agent_id=agent_id,
                successful_agents=[run.agent_id for run in specialist_runs],
            )
            if isinstance(exc, BudgetExceededError):
                return self._failed_budget(
                    opportunity,
                    gate_decision,
                    professor_plan,
                    specialist_runs,
                    palermo_run,
                    final_decision,
                    "specialists_independent_round_1",
                    agent_id,
                    exc,
                    calls,
                    events,
                )
            if isinstance(exc, AIProviderError):
                return self._provider_failure(
                    opportunity,
                    gate_decision,
                    professor_plan,
                    specialist_runs,
                    palermo_run,
                    final_decision,
                    "specialists_independent_round_1",
                    agent_id,
                    exc,
                    calls,
                    events,
                )
            if isinstance(exc, UngroundedEvidenceError):
                code = PipelineFailureCode.UNGROUNDED_EVIDENCE
            else:
                code = PipelineFailureCode.INVALID_SPECIALIST_OUTPUT
            return self._failed(
                opportunity=opportunity,
                gate_decision=gate_decision,
                professor_plan=professor_plan,
                specialist_runs=specialist_runs,
                palermo_run=palermo_run,
                final_decision=final_decision,
                code=code,
                stage="specialists_independent_round_1",
                message=str(exc),
                agent_id=agent_id,
                calls=calls,
                events=events,
            )

        event(
            "specialists_independent_round_1",
            "COMPLETED",
            completed_agents=[run.agent_id for run in specialist_runs],
        )
        specialist_payloads = [run.analysis.model_dump(mode="json") for run in specialist_runs]
        provisional_thesis = {
            "professor_plan": professor_plan.model_dump(mode="json"),
            "independent_stances": [
                {
                    "agent_id": run.agent_id,
                    "stance": run.analysis.stance.value,
                    "confidence": run.analysis.confidence,
                }
                for run in specialist_runs
            ],
            "aggregation_policy": "preserve_individual_conclusions_without_majority_vote",
        }

        try:
            palermo_result = await self.palermo.review(
                system_id=opportunity.system_id,
                market_context=market_payload,
                specialist_analyses=specialist_payloads,
                provisional_thesis=provisional_thesis,
                opportunity_id=opportunity_uuid,
            )
            calls.append(self._call_audit(palermo_result, self.palermo, "palermo_red_team"))
            palermo_run = PalermoRunRecord(
                request_id=palermo_result.request_id,
                prompt_version=self.palermo.prompt.version,
                route_id=palermo_result.route_id,
                model_id=palermo_result.model_id,
                review=palermo_result.output,
            )
            event(
                "palermo_red_team",
                "COMPLETED",
                request_id=str(palermo_result.request_id),
                verdict=palermo_result.output.verdict,
            )
        except BudgetExceededError as exc:
            return self._failed_budget(
                opportunity,
                gate_decision,
                professor_plan,
                specialist_runs,
                palermo_run,
                final_decision,
                "palermo_red_team",
                "palermo",
                exc,
                calls,
                events,
            )
        except StructuredOutputError as exc:
            event("palermo_red_team", "FAILED", reason="structured_output")
            return self._failed(
                opportunity=opportunity,
                gate_decision=gate_decision,
                professor_plan=professor_plan,
                specialist_runs=specialist_runs,
                palermo_run=palermo_run,
                final_decision=final_decision,
                code=PipelineFailureCode.INVALID_PALERMO_OUTPUT,
                stage="palermo_red_team",
                message=str(exc),
                agent_id="palermo",
                calls=calls,
                events=events,
            )
        except AIProviderError as exc:
            return self._provider_failure(
                opportunity,
                gate_decision,
                professor_plan,
                specialist_runs,
                palermo_run,
                final_decision,
                "palermo_red_team",
                "palermo",
                exc,
                calls,
                events,
            )

        try:
            final_result = await self.professor.finalize_with_schema(
                system_id=opportunity.system_id,
                opportunity=opportunity_payload,
                market_context=market_payload,
                specialist_analyses=specialist_payloads,
                palermo_review=palermo_run.review.model_dump(mode="json"),
                output_model=ProfessorFinalDecision,
                opportunity_id=opportunity_uuid,
            )
            final_decision = final_result.output
            _assert_grounded_final_evidence(
                final_decision.evidence,
                opportunity=opportunity_payload,
                market_context=market_payload,
                specialist_analyses=specialist_payloads,
                palermo_review=palermo_run.review.model_dump(mode="json"),
            )
            calls.append(self._call_audit(final_result, self.professor, "professor_finalize"))
            event(
                "professor_finalize",
                "COMPLETED",
                request_id=str(final_result.request_id),
                direction=final_decision.direction,
            )
        except BudgetExceededError as exc:
            return self._failed_budget(
                opportunity,
                gate_decision,
                professor_plan,
                specialist_runs,
                palermo_run,
                final_decision,
                "professor_finalize",
                "professor",
                exc,
                calls,
                events,
            )
        except StructuredOutputError as exc:
            event("professor_finalize", "FAILED", reason=type(exc).__name__)
            return self._failed(
                opportunity=opportunity,
                gate_decision=gate_decision,
                professor_plan=professor_plan,
                specialist_runs=specialist_runs,
                palermo_run=palermo_run,
                final_decision=final_decision,
                code=PipelineFailureCode.INVALID_PROFESSOR_OUTPUT,
                stage="professor_finalize",
                message=str(exc),
                agent_id="professor",
                calls=calls,
                events=events,
            )
        except UngroundedEvidenceError as exc:
            event("professor_finalize", "FAILED", reason=type(exc).__name__)
            return self._failed(
                opportunity=opportunity,
                gate_decision=gate_decision,
                professor_plan=professor_plan,
                specialist_runs=specialist_runs,
                palermo_run=palermo_run,
                final_decision=final_decision,
                code=PipelineFailureCode.UNGROUNDED_EVIDENCE,
                stage="professor_finalize",
                message=str(exc),
                agent_id="professor",
                calls=calls,
                events=events,
            )
        except AIProviderError as exc:
            return self._provider_failure(
                opportunity,
                gate_decision,
                professor_plan,
                specialist_runs,
                palermo_run,
                final_decision,
                "professor_finalize",
                "professor",
                exc,
                calls,
                events,
            )

        if final_decision.direction == "NO_TRADE":
            event("trade_proposal", "SKIPPED", reason="no_trade")
            return self._result(
                status=PipelineStatus.NO_TRADE,
                opportunity=opportunity,
                gate_decision=gate_decision,
                professor_plan=professor_plan,
                specialist_runs=specialist_runs,
                palermo_run=palermo_run,
                final_decision=final_decision,
                trade_proposal=None,
                failure=None,
                calls=calls,
                events=events,
            )

        assert final_decision.trade is not None  # Guaranteed by ProfessorFinalDecision validation.
        proposal_id = uuid5(
            NAMESPACE_URL,
            f"money-heist:proposal:{opportunity.opportunity_id}:{final_result.request_id}",
        )
        proposal = TradeProposal(
            proposal_id=proposal_id,
            opportunity_id=opportunity.opportunity_id,
            source_snapshot_id=market_context.snapshot_id,
            system_id=opportunity.system_id,
            symbol=opportunity.symbol,
            timeframe=opportunity.timeframe,
            side=final_decision.direction,
            confidence=final_decision.confidence,
            entry_price=final_decision.trade.entry_price,
            stop_price=final_decision.trade.stop_price,
            targets=final_decision.trade.targets,
            expected_rr=final_decision.trade.expected_rr,
            thesis=tuple(final_decision.thesis),
            counter_evidence=tuple(final_decision.counter_evidence),
            invalidation=tuple(final_decision.invalidation),
            evidence=tuple(final_decision.evidence),
            market_regime=market_context.regime.value,
            feature_version=market_context.feature_version,
            professor_prompt_version=self.professor.prompt.version,
            professor_request_id=final_result.request_id,
            specialist_request_ids=tuple(run.request_id for run in specialist_runs),
            palermo_request_id=palermo_run.request_id,
            created_at=final_result.usage.created_at,
            expires_at=opportunity.expires_at,
        )
        event("trade_proposal", "COMPLETED", proposal_id=str(proposal.proposal_id))
        return self._result(
            status=PipelineStatus.TRADE_PROPOSAL,
            opportunity=opportunity,
            gate_decision=gate_decision,
            professor_plan=professor_plan,
            specialist_runs=specialist_runs,
            palermo_run=palermo_run,
            final_decision=final_decision,
            trade_proposal=proposal,
            failure=None,
            calls=calls,
            events=events,
        )

    @staticmethod
    def _validate_context(
        opportunity: CandidateOpportunity,
        market_context: FeatureSnapshot,
    ) -> UUID:
        try:
            opportunity_uuid = UUID(opportunity.opportunity_id)
        except ValueError as exc:
            raise InvalidPipelineContextError("opportunity_id must be a UUID") from exc
        if opportunity.snapshot_id != market_context.snapshot_id:
            raise InvalidPipelineContextError("opportunity snapshot_id does not match market context")
        if opportunity.symbol != market_context.symbol:
            raise InvalidPipelineContextError("opportunity symbol does not match market context")
        if opportunity.timeframe != market_context.timeframe:
            raise InvalidPipelineContextError("opportunity timeframe does not match market context")
        if not market_context.quality.warmup_complete:
            raise InvalidPipelineContextError("feature warmup is incomplete")
        return opportunity_uuid

    def _available_specialists(self) -> list[str]:
        allowed_states = {AgentState.ACTIVE, AgentState.ON_DEMAND}
        return sorted(
            agent_id
            for agent_id, agent in self.specialists.items()
            if agent.entry.state in allowed_states
        )

    @staticmethod
    def _validate_plan(
        plan: ProfessorPlan,
        gate_level: ComputeLevel,
        available_agents: list[str],
    ) -> None:
        selected = plan.selected_agents
        if len(selected) != len(set(selected)):
            raise InvalidProfessorPlanError("selected_agents contains duplicates")
        unknown = [agent_id for agent_id in selected if agent_id not in available_agents]
        if unknown:
            raise InvalidProfessorPlanError(
                "Professor selected unavailable specialists: " + ", ".join(unknown)
            )
        if plan.decision == "NO_ANALYSIS":
            if selected:
                raise InvalidProfessorPlanError("NO_ANALYSIS cannot select specialists")
            return
        if not selected:
            raise InvalidProfessorPlanError(f"{plan.decision} must select at least one specialist")
        if plan.decision == "MINI_CREW" and len(selected) > 2:
            raise InvalidProfessorPlanError("MINI_CREW may select at most two specialists")
        if gate_level is ComputeLevel.LEVEL_2_MINI_CREW and plan.decision == "FULL_CREW":
            raise InvalidProfessorPlanError("Professor cannot exceed the Compute Gate level")

    @staticmethod
    def _call_audit(result: AIGatewayResult, agent: Any, phase: str) -> AgentCallAudit:
        return AgentCallAudit(
            request_id=result.request_id,
            agent_id=agent.agent_id,
            phase=phase,
            prompt_version=agent.prompt.version,
            route_id=result.route_id,
            model_id=result.model_id,
            estimated_cost_eur=result.usage.estimated_cost,
            attempts=result.attempts,
        )

    def _failed_budget(
        self,
        opportunity: CandidateOpportunity,
        gate_decision,
        professor_plan,
        specialist_runs,
        palermo_run,
        final_decision,
        stage: str,
        agent_id: str,
        exc: Exception,
        calls,
        events,
    ) -> OrchestrationResult:
        events.append(
            PipelineAuditEvent(
                sequence=len(events) + 1,
                stage=stage,
                status="FAILED",
                details={
                    "reason": "budget_exhausted",
                    "remaining_budget_eur": str(self._budget.snapshot().remaining_eur),
                },
            )
        )
        return self._failed(
            opportunity=opportunity,
            gate_decision=gate_decision,
            professor_plan=professor_plan,
            specialist_runs=specialist_runs,
            palermo_run=palermo_run,
            final_decision=final_decision,
            code=PipelineFailureCode.BUDGET_EXHAUSTED,
            stage=stage,
            message=str(exc),
            agent_id=agent_id,
            calls=calls,
            events=events,
        )

    def _provider_failure(
        self,
        opportunity,
        gate_decision,
        professor_plan,
        specialist_runs,
        palermo_run,
        final_decision,
        stage,
        agent_id,
        exc,
        calls,
        events,
    ) -> OrchestrationResult:
        events.append(
            PipelineAuditEvent(
                sequence=len(events) + 1,
                stage=stage,
                status="FAILED",
                details={"reason": "ai_provider_error"},
            )
        )
        return self._failed(
            opportunity=opportunity,
            gate_decision=gate_decision,
            professor_plan=professor_plan,
            specialist_runs=specialist_runs,
            palermo_run=palermo_run,
            final_decision=final_decision,
            code=PipelineFailureCode.AI_PROVIDER_ERROR,
            stage=stage,
            message=str(exc),
            agent_id=agent_id,
            calls=calls,
            events=events,
        )

    def _failed(
        self,
        *,
        opportunity,
        gate_decision,
        professor_plan,
        specialist_runs,
        palermo_run,
        final_decision,
        code,
        stage,
        message,
        agent_id,
        calls,
        events,
    ) -> OrchestrationResult:
        return self._result(
            status=PipelineStatus.FAILED,
            opportunity=opportunity,
            gate_decision=gate_decision,
            professor_plan=professor_plan,
            specialist_runs=specialist_runs,
            palermo_run=palermo_run,
            final_decision=final_decision,
            trade_proposal=None,
            failure=PipelineFailure(
                code=code,
                stage=stage,
                message=message or type(message).__name__,
                agent_id=agent_id,
            ),
            calls=calls,
            events=events,
        )

    @staticmethod
    def _result(
        *,
        status,
        opportunity,
        gate_decision,
        professor_plan,
        specialist_runs,
        palermo_run,
        final_decision,
        trade_proposal,
        failure,
        calls,
        events,
    ) -> OrchestrationResult:
        return OrchestrationResult(
            status=status,
            opportunity_id=opportunity.opportunity_id,
            source_snapshot_id=opportunity.snapshot_id,
            system_id=opportunity.system_id,
            symbol=opportunity.symbol,
            compute_gate=gate_decision,
            professor_plan=professor_plan,
            specialist_runs=tuple(specialist_runs),
            palermo_run=palermo_run,
            professor_decision=final_decision,
            trade_proposal=trade_proposal,
            failure=failure,
            agent_calls=tuple(calls),
            audit_events=tuple(events),
        )
