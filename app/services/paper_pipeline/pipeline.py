from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable

from app.market.features.models import FeatureSnapshot
from app.market.scanner.models import CandidateOpportunity
from app.services.orchestration.models import PipelineStatus
from app.trading.paper.broker import PaperBroker, PaperBrokerError
from app.trading.paper.models import Fill, OrderStatus, Position
from app.trading.risk.engine import RiskEngine
from app.trading.risk.models import RiskDecisionStatus

from .adapters import (
    authorized_order_intent,
    intent_to_paper_request,
    risk_decision_record,
    trade_proposal_to_risk_input,
)
from .models import (
    PaperPipelineEvent,
    PaperPipelineFailure,
    PaperPipelineFailureCode,
    PaperPipelineResult,
    PaperPipelineStatus,
)
from .ports import (
    KillSwitchStateProvider,
    MarketConstraintsProvider,
    OrchestrationPort,
    PaperPipelineJournal,
    PortfolioRiskStateProvider,
    RiskProfileProvider,
)


class PaperTradingPipeline:
    """Deterministic Batch 09 boundary: Opportunity -> AI -> Risk -> Paper Broker.

    Agents remain isolated behind ``OrchestrationPort``. Only this service owns
    access to RiskEngine and PaperBroker, and it has no LIVE execution path.
    """

    def __init__(
        self,
        *,
        orchestration: OrchestrationPort,
        risk_engine: RiskEngine,
        paper_broker: PaperBroker,
        portfolio_provider: PortfolioRiskStateProvider,
        risk_profile_provider: RiskProfileProvider,
        market_constraints_provider: MarketConstraintsProvider,
        kill_switch_provider: KillSwitchStateProvider,
        journal: PaperPipelineJournal,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.orchestration = orchestration
        self.risk_engine = risk_engine
        self.paper_broker = paper_broker
        self.portfolio_provider = portfolio_provider
        self.risk_profile_provider = risk_profile_provider
        self.market_constraints_provider = market_constraints_provider
        self.kill_switch_provider = kill_switch_provider
        self.journal = journal
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def run(
        self,
        *,
        opportunity: CandidateOpportunity,
        market_context: FeatureSnapshot,
        now: datetime | None = None,
    ) -> PaperPipelineResult:
        events: list[PaperPipelineEvent] = []
        orchestration_result = None
        risk_input = None
        portfolio = None
        profile = None
        market = None
        kill_switch = None
        risk_record = None
        order_intent = None
        order = None
        fill = None
        position_before = None
        position_after = None

        effective_now = now or self._clock()
        if effective_now.tzinfo is None:
            effective_now = effective_now.replace(tzinfo=timezone.utc)
        else:
            effective_now = effective_now.astimezone(timezone.utc)

        def result(
            status: PaperPipelineStatus,
            *,
            failure: PaperPipelineFailure | None = None,
        ) -> PaperPipelineResult:
            return PaperPipelineResult(
                status=status,
                opportunity_id=opportunity.opportunity_id,
                source_snapshot_id=market_context.snapshot_id,
                orchestration_result=orchestration_result,
                risk_input=risk_input,
                portfolio_state=portfolio,
                risk_profile=profile,
                market_constraints=market,
                kill_switch_state=kill_switch,
                risk_record=risk_record,
                order_intent=order_intent,
                order=order,
                fill=fill,
                position_before=position_before,
                position_after=position_after,
                failure=failure,
                audit_events=tuple(events),
            )

        def fail(code: PaperPipelineFailureCode, stage: str, message: str) -> PaperPipelineResult:
            return result(
                PaperPipelineStatus.FAILED,
                failure=PaperPipelineFailure(code=code, stage=stage, message=message),
            )

        def emit(
            stage: str,
            status: str,
            *,
            proposal_id: str | None = None,
            **details: str,
        ) -> None:
            event = PaperPipelineEvent(
                sequence=len(events) + 1,
                stage=stage,
                status=status,
                opportunity_id=opportunity.opportunity_id,
                proposal_id=proposal_id,
                source_snapshot_id=market_context.snapshot_id,
                created_at=self._clock(),
                details=details,
            )
            self.journal.append(event)
            events.append(event)

        try:
            self.journal.preflight()
        except Exception as exc:
            return fail(PaperPipelineFailureCode.AUDIT_UNAVAILABLE, "audit_preflight", str(exc))

        try:
            orchestration_result = await self.orchestration.run(
                opportunity=opportunity,
                market_context=market_context,
                now=effective_now,
            )
        except Exception as exc:
            try:
                emit("orchestration", "FAILED", error=type(exc).__name__)
            except Exception:
                pass
            return fail(
                PaperPipelineFailureCode.ORCHESTRATION_UNAVAILABLE,
                "orchestration",
                str(exc),
            )

        try:
            emit(
                "orchestration",
                "COMPLETED",
                orchestration_status=orchestration_result.status.value,
                professor_direction=(
                    orchestration_result.professor_decision.direction
                    if orchestration_result.professor_decision is not None
                    else ""
                ),
                agent_call_count=str(len(orchestration_result.agent_calls)),
                agent_request_ids=",".join(
                    str(call.request_id) for call in orchestration_result.agent_calls
                ),
            )
        except Exception as exc:
            return fail(PaperPipelineFailureCode.AUDIT_UNAVAILABLE, "orchestration_audit", str(exc))

        if orchestration_result.status is PipelineStatus.NO_ANALYSIS:
            return result(PaperPipelineStatus.NO_ANALYSIS)

        if orchestration_result.status is PipelineStatus.NO_TRADE:
            return result(PaperPipelineStatus.NO_TRADE)

        if orchestration_result.status is PipelineStatus.FAILED:
            message = (
                orchestration_result.failure.message
                if orchestration_result.failure is not None
                else "upstream orchestration failed"
            )
            return fail(
                PaperPipelineFailureCode.ORCHESTRATION_FAILED,
                "orchestration",
                message,
            )

        proposal = orchestration_result.trade_proposal
        if orchestration_result.status is not PipelineStatus.TRADE_PROPOSAL or proposal is None:
            return fail(
                PaperPipelineFailureCode.INCOHERENT_ORCHESTRATION_RESULT,
                "proposal_validation",
                "orchestration did not provide a coherent TRADE_PROPOSAL result",
            )

        incoherence = self._proposal_incoherence(opportunity, market_context, proposal)
        if incoherence is not None:
            return fail(
                PaperPipelineFailureCode.INCOHERENT_ORCHESTRATION_RESULT,
                "proposal_validation",
                incoherence,
            )

        proposal_id = str(proposal.proposal_id)
        try:
            emit(
                "trade_proposal",
                "COMPLETED",
                proposal_id=proposal_id,
                side=proposal.side,
                professor_request_id=str(proposal.professor_request_id),
                specialist_request_ids=",".join(
                    str(request_id) for request_id in proposal.specialist_request_ids
                ),
                palermo_request_id=str(proposal.palermo_request_id),
                entry_price=str(proposal.entry_price),
                stop_price=str(proposal.stop_price),
                targets=",".join(str(target) for target in proposal.targets),
                expected_rr=str(proposal.expected_rr),
                professor_prompt_version=proposal.professor_prompt_version,
                feature_version=proposal.feature_version,
            )
        except Exception as exc:
            return fail(
                PaperPipelineFailureCode.AUDIT_UNAVAILABLE,
                "proposal_audit",
                str(exc),
            )

        try:
            risk_input = trade_proposal_to_risk_input(proposal)
        except (ValueError, TypeError) as exc:
            return fail(
                PaperPipelineFailureCode.PROPOSAL_ADAPTATION_FAILED,
                "risk_adapter",
                str(exc),
            )

        try:
            portfolio = self.portfolio_provider.get_portfolio_state(system_id=proposal.system_id)
        except Exception as exc:
            return fail(
                PaperPipelineFailureCode.PORTFOLIO_STATE_UNAVAILABLE,
                "risk_context",
                str(exc),
            )
        if portfolio is None:
            return fail(
                PaperPipelineFailureCode.PORTFOLIO_STATE_UNAVAILABLE,
                "risk_context",
                "portfolio risk state is missing",
            )

        try:
            profile = self.risk_profile_provider.get_risk_profile(system_id=proposal.system_id)
        except Exception as exc:
            return fail(PaperPipelineFailureCode.RISK_PROFILE_UNAVAILABLE, "risk_context", str(exc))
        if profile is None:
            return fail(
                PaperPipelineFailureCode.RISK_PROFILE_UNAVAILABLE,
                "risk_context",
                "risk profile is missing",
            )

        try:
            market = self.market_constraints_provider.get_market_constraints(symbol=proposal.symbol)
        except Exception as exc:
            return fail(
                PaperPipelineFailureCode.MARKET_CONSTRAINTS_UNAVAILABLE,
                "risk_context",
                str(exc),
            )
        if market is None:
            return fail(
                PaperPipelineFailureCode.MARKET_CONSTRAINTS_UNAVAILABLE,
                "risk_context",
                "market constraints are missing",
            )

        try:
            kill_switch = self.kill_switch_provider.get_kill_switch_state(
                system_id=proposal.system_id
            )
        except Exception as exc:
            return fail(PaperPipelineFailureCode.KILL_SWITCH_UNAVAILABLE, "risk_context", str(exc))
        if kill_switch is None:
            return fail(
                PaperPipelineFailureCode.KILL_SWITCH_UNAVAILABLE,
                "risk_context",
                "kill switch state is missing",
            )

        decision = self.risk_engine.evaluate(
            proposal=risk_input,
            portfolio=portfolio,
            profile=profile,
            market=market,
            kill_switch=kill_switch,
            now=effective_now,
        )
        risk_record = risk_decision_record(proposal_id, decision)

        try:
            emit(
                "risk_engine",
                "COMPLETED",
                proposal_id=proposal_id,
                risk_decision_id=str(risk_record.risk_decision_id),
                risk_status=decision.status.value,
                reason_codes=",".join(code.value for code in decision.reason_codes),
                approved_quantity=str(decision.approved_quantity),
            )
        except Exception as exc:
            return fail(PaperPipelineFailureCode.AUDIT_UNAVAILABLE, "risk_audit", str(exc))

        if decision.status is RiskDecisionStatus.REJECTED:
            return result(PaperPipelineStatus.RISK_REJECTED)

        try:
            order_intent = authorized_order_intent(proposal, risk_record)
        except ValueError as exc:
            return fail(
                PaperPipelineFailureCode.INCOHERENT_ORCHESTRATION_RESULT,
                "order_intent",
                str(exc),
            )

        execution_mark = self._execution_mark(market_context)
        if execution_mark is None:
            return fail(
                PaperPipelineFailureCode.INVALID_EXECUTION_MARK,
                "execution_preflight",
                "market_context.close is not a positive finite execution mark",
            )

        if self.paper_broker.config.system_id != proposal.system_id:
            return fail(
                PaperPipelineFailureCode.BROKER_EXECUTION_FAILED,
                "execution_preflight",
                "paper broker system_id does not match proposal system_id",
            )

        try:
            self.journal.preflight()
            claimed = self.journal.claim_execution(
                opportunity_id=proposal.opportunity_id,
                proposal_id=proposal_id,
                source_snapshot_id=proposal.source_snapshot_id,
            )
        except Exception as exc:
            return fail(PaperPipelineFailureCode.AUDIT_UNAVAILABLE, "execution_claim", str(exc))

        if not claimed:
            try:
                emit(
                    "execution_claim",
                    "SKIPPED",
                    proposal_id=proposal_id,
                    reason="duplicate_opportunity_or_proposal",
                )
            except Exception:
                pass
            return result(
                PaperPipelineStatus.DUPLICATE_BLOCKED,
                failure=PaperPipelineFailure(
                    code=PaperPipelineFailureCode.DUPLICATE_EXECUTION,
                    stage="execution_claim",
                    message="opportunity/proposal was already claimed for PAPER execution",
                ),
            )

        try:
            emit(
                "order_intent",
                "COMPLETED",
                proposal_id=proposal_id,
                risk_decision_id=str(order_intent.risk_decision_id),
                mode=order_intent.mode,
                side=order_intent.side.value,
                quantity=str(order_intent.quantity),
                client_order_id=order_intent.client_order_id,
            )
        except Exception as exc:
            return fail(PaperPipelineFailureCode.AUDIT_RECORDING_FAILED, "order_intent", str(exc))

        try:
            before_positions = await self.paper_broker.get_positions()
            position_before = self._find_position(before_positions, proposal.symbol)

            # The exact Batch 08 feature snapshot supplies the deterministic PAPER mark.
            await self.paper_broker.process_price(
                proposal.symbol,
                execution_mark,
                observed_at=market_context.observed_at,
            )
            order = await self.paper_broker.submit_order(intent_to_paper_request(order_intent))

            if order.status is not OrderStatus.FILLED:
                return fail(
                    PaperPipelineFailureCode.INCOMPLETE_BROKER_EXECUTION,
                    "paper_broker",
                    f"PAPER market order ended with status {order.status.value}",
                )

            fills = await self.paper_broker.get_fills()
            fill = self._find_fill(fills, order.broker_order_id)
            if fill is None:
                return fail(
                    PaperPipelineFailureCode.INCOMPLETE_BROKER_EXECUTION,
                    "paper_broker",
                    "filled PAPER order has no matching fill",
                )

            after_positions = await self.paper_broker.get_positions()
            position_after = self._find_position(after_positions, proposal.symbol)
        except PaperBrokerError as exc:
            return fail(
                PaperPipelineFailureCode.BROKER_EXECUTION_FAILED,
                "paper_broker",
                str(exc),
            )

        try:
            emit(
                "paper_execution",
                "COMPLETED",
                proposal_id=proposal_id,
                risk_decision_id=str(risk_record.risk_decision_id),
                broker_order_id=order.broker_order_id,
                fill_id=fill.fill_id,
                filled_quantity=str(fill.quantity),
                fill_price=str(fill.price),
                position_side=(
                    position_after.side.value
                    if position_after and position_after.side
                    else "FLAT"
                ),
                position_quantity=(str(position_after.quantity) if position_after else "0"),
            )
        except Exception as exc:
            # A compliant journal must surface inability to guarantee this write in preflight.
            return fail(
                PaperPipelineFailureCode.AUDIT_RECORDING_FAILED,
                "paper_execution_audit",
                str(exc),
            )

        return result(PaperPipelineStatus.EXECUTED)

    @staticmethod
    def _proposal_incoherence(opportunity, market_context, proposal) -> str | None:
        checks = (
            (proposal.opportunity_id == opportunity.opportunity_id, "opportunity_id mismatch"),
            (proposal.source_snapshot_id == market_context.snapshot_id, "snapshot_id mismatch"),
            (
                proposal.source_snapshot_id == opportunity.snapshot_id,
                "opportunity snapshot mismatch",
            ),
            (proposal.system_id == opportunity.system_id, "system_id mismatch"),
            (proposal.symbol == opportunity.symbol, "symbol mismatch"),
            (proposal.timeframe == opportunity.timeframe, "timeframe mismatch"),
        )
        for valid, message in checks:
            if not valid:
                return message
        return None

    @staticmethod
    def _execution_mark(market_context: FeatureSnapshot) -> Decimal | None:
        try:
            value = Decimal(str(market_context.close))
            if not value.is_finite() or value <= 0:
                return None
            return value
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _find_fill(fills: tuple[Fill, ...], broker_order_id: str) -> Fill | None:
        matches = [fill for fill in fills if fill.broker_order_id == broker_order_id]
        return matches[-1] if matches else None

    @staticmethod
    def _find_position(positions: tuple[Position, ...], symbol: str) -> Position | None:
        return next((position for position in positions if position.symbol == symbol), None)
