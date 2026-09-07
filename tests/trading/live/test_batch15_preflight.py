from datetime import datetime, timezone

from app.domain.enums import SystemMode
from app.trading.live.activation import (
    LiveActivationController,
    LiveActivationError,
    LiveOperationalState,
)
from app.trading.live.preflight import (
    INITIAL_LIVE_SYMBOLS,
    LiveCheckState,
    LivePreflight,
    LivePreflightContext,
    LivePreflightReasonCode,
    LivePreflightStatus,
    MarketReadiness,
    REQUIRED_KRAKEN_PERMISSIONS,
)
from app.trading.live.store import InMemoryLiveAuditSink
from app.trading.risk.kill_switch import KillSwitch
from app.trading.risk.profiles import demo_profile, unresolved_profile

NOW = datetime(2026, 9, 7, 22, 0, tzinfo=timezone.utc)


def ready_market():
    return {
        symbol: MarketReadiness(
            symbol=symbol,
            source="kraken_spot",
            quote_asset="ZEUR",
            status="online",
            current_data_fresh=True,
            metadata_fresh=True,
            constraints_valid=True,
        )
        for symbol in INITIAL_LIVE_SYMBOLS
    }


def context(**changes):
    values = dict(
        system_id="balanced_v1",
        app_env="production",
        runtime_mode=SystemMode.LIVE,
        live_environment="kraken_spot_eur",
        explicitly_allowed_system_id="balanced_v1",
        target_system_mode=SystemMode.LIVE,
        risk_profile=demo_profile(risk_profile_id="balanced"),
        kill_switch=KillSwitch().snapshot(),
        persistence_ready=True,
        audit_ready=True,
        credentials_present=True,
        api_permissions=tuple(sorted(REQUIRED_KRAKEN_PERMISSIONS)),
        market_configuration_known=True,
        market=ready_market(),
        reconciliation_ready=True,
        unresolved_live_orders=0,
    )
    values.update(changes)
    return LivePreflightContext(**values)


def test_ready_requires_every_critical_check_to_pass():
    report = LivePreflight(now=lambda: NOW).evaluate(context())
    assert report.status is LivePreflightStatus.READY
    assert report.reason_codes == ()
    assert report.metadata["prototype_capital_eur"] == "100"
    assert report.metadata["capital_is_risk_input"] == "false"


def test_unknown_is_blocking():
    report = LivePreflight(now=lambda: NOW).evaluate(context(api_permissions=None))
    assert report.status is LivePreflightStatus.BLOCKED
    assert LivePreflightReasonCode.API_PERMISSIONS_UNKNOWN in report.reason_codes
    assert any(check.state is LiveCheckState.UNKNOWN for check in report.checks)


def test_incomplete_balanced_profile_is_explicit_blocker_without_inventing_values():
    report = LivePreflight(now=lambda: NOW).evaluate(
        context(risk_profile=unresolved_profile("balanced"))
    )
    assert report.status is LivePreflightStatus.BLOCKED
    assert LivePreflightReasonCode.RISK_PROFILE_INCOMPLETE in report.reason_codes


def test_withdrawal_and_any_extra_permission_block_exact_minimum_policy():
    permissions = tuple(sorted(REQUIRED_KRAKEN_PERMISSIONS | {"withdraw-funds"}))
    report = LivePreflight(now=lambda: NOW).evaluate(context(api_permissions=permissions))
    assert LivePreflightReasonCode.API_PERMISSION_WITHDRAWAL in report.reason_codes
    assert LivePreflightReasonCode.API_PERMISSIONS_EXCESS in report.reason_codes


def test_read_only_but_unneeded_permission_is_also_blocked():
    permissions = tuple(sorted(REQUIRED_KRAKEN_PERMISSIONS | {"query-ledger"}))
    report = LivePreflight(now=lambda: NOW).evaluate(context(api_permissions=permissions))
    assert LivePreflightReasonCode.API_PERMISSIONS_EXCESS in report.reason_codes


def test_shadow_target_can_never_be_ready():
    report = LivePreflight(now=lambda: NOW).evaluate(
        context(target_system_mode=SystemMode.SHADOW)
    )
    assert LivePreflightReasonCode.TARGET_SYSTEM_IS_SHADOW in report.reason_codes


def test_missing_kill_switch_state_is_unknown_and_blocking():
    report = LivePreflight(now=lambda: NOW).evaluate(context(kill_switch=None))
    assert report.status is LivePreflightStatus.BLOCKED
    assert LivePreflightReasonCode.KILL_SWITCH_UNKNOWN in report.reason_codes


def test_reconciliation_unknown_is_blocking():
    report = LivePreflight(now=lambda: NOW).evaluate(context(reconciliation_ready=None))
    assert report.status is LivePreflightStatus.BLOCKED
    assert LivePreflightReasonCode.RECONCILIATION_UNKNOWN in report.reason_codes


def test_kill_switch_blocks_new_live_entries():
    switch = KillSwitch()
    switch.stop_new_trades(reason="operator stop")
    report = LivePreflight(now=lambda: NOW).evaluate(context(kill_switch=switch.snapshot()))
    assert LivePreflightReasonCode.KILL_SWITCH_BLOCKS_NEW_TRADES in report.reason_codes


def test_any_market_staleness_blocks():
    market = ready_market()
    market["BTC/EUR"] = MarketReadiness(
        symbol="BTC/EUR",
        source="kraken_spot",
        quote_asset="ZEUR",
        status="online",
        current_data_fresh=False,
        metadata_fresh=True,
        constraints_valid=True,
    )
    report = LivePreflight(now=lambda: NOW).evaluate(context(market=market))
    assert LivePreflightReasonCode.MARKET_DATA_STALE in report.reason_codes


def test_reconciliation_required_blocks():
    report = LivePreflight(now=lambda: NOW).evaluate(
        context(reconciliation_ready=False, unresolved_live_orders=1)
    )
    assert LivePreflightReasonCode.RECONCILIATION_REQUIRED in report.reason_codes
    assert LivePreflightReasonCode.UNRESOLVED_LIVE_ORDERS in report.reason_codes


def test_activation_is_never_armed_at_construction_or_restart():
    audit = InMemoryLiveAuditSink()
    report = LivePreflight(now=lambda: NOW).evaluate(context())
    first = LiveActivationController(system_id="balanced_v1", audit=audit, now=lambda: NOW)
    assert first.state is LiveOperationalState.LIVE_DISABLED
    assert not first.get_authorization(system_id="balanced_v1").authorized

    first.begin_preflight()
    first.arm(report=report, operator_confirmation="ARM LIVE balanced_v1")
    assert first.state is LiveOperationalState.LIVE_ARMED
    assert first.get_authorization(system_id="balanced_v1").authorized

    restarted = LiveActivationController(system_id="balanced_v1", audit=audit, now=lambda: NOW)
    assert restarted.state is LiveOperationalState.LIVE_DISABLED
    assert not restarted.get_authorization(system_id="balanced_v1").authorized


def test_blocked_report_or_wrong_operator_phrase_cannot_arm():
    audit = InMemoryLiveAuditSink()
    controller = LiveActivationController(system_id="balanced_v1", audit=audit, now=lambda: NOW)
    controller.begin_preflight()
    blocked = LivePreflight(now=lambda: NOW).evaluate(context(reconciliation_ready=False))
    try:
        controller.arm(report=blocked, operator_confirmation="ARM LIVE balanced_v1")
    except LiveActivationError:
        pass
    else:
        raise AssertionError("BLOCKED report armed LIVE")

    ready = LivePreflight(now=lambda: NOW).evaluate(context())
    try:
        controller.arm(report=ready, operator_confirmation="yes")
    except LiveActivationError:
        pass
    else:
        raise AssertionError("wrong confirmation armed LIVE")


def test_order_preflight_requires_operator_arm_and_authorized_risk_decision():
    from datetime import timedelta
    from decimal import Decimal

    from app.trading.live.preflight import LiveOrderPreflight, LiveOrderPreflightContext
    from app.trading.risk.models import RiskDecision, RiskDecisionStatus

    decision = RiskDecision(
        proposal_id="proposal-15",
        status=RiskDecisionStatus.REJECTED,
        reason_codes=(),
        approved_quantity=Decimal("0"),
    )
    checks = LiveOrderPreflight(now=lambda: NOW).evaluate(
        LiveOrderPreflightContext(
            system_id="balanced_v1",
            proposal_id="proposal-15",
            proposal_side="LONG",
            proposal_expires_at=NOW + timedelta(minutes=1),
            risk_decision=decision,
            risk_profile=demo_profile(risk_profile_id="balanced"),
            kill_switch=KillSwitch().snapshot(),
            symbol="BTC/EUR",
            market=ready_market()["BTC/EUR"],
            reconciliation_ready=True,
            armed=False,
        )
    )
    reasons = {check.reason_code for check in checks if check.reason_code}
    assert LivePreflightReasonCode.OPERATOR_ARM_REQUIRED in reasons
    assert LivePreflightReasonCode.RISK_DECISION_NOT_AUTHORIZED in reasons


def test_order_preflight_blocks_short_even_when_risk_decision_is_authorized():
    from datetime import timedelta
    from decimal import Decimal

    from app.trading.live.preflight import LiveOrderPreflight, LiveOrderPreflightContext
    from app.trading.risk.models import RiskDecision, RiskDecisionStatus

    decision = RiskDecision(
        proposal_id="proposal-15",
        status=RiskDecisionStatus.APPROVED,
        reason_codes=(),
        approved_quantity=Decimal("0.001"),
    )
    checks = LiveOrderPreflight(now=lambda: NOW).evaluate(
        LiveOrderPreflightContext(
            system_id="balanced_v1",
            proposal_id="proposal-15",
            proposal_side="SHORT",
            proposal_expires_at=NOW + timedelta(minutes=1),
            risk_decision=decision,
            risk_profile=demo_profile(risk_profile_id="balanced"),
            kill_switch=KillSwitch().snapshot(),
            symbol="BTC/EUR",
            market=ready_market()["BTC/EUR"],
            reconciliation_ready=True,
            armed=True,
        )
    )
    assert LivePreflightReasonCode.ORDER_SHORT_NOT_SUPPORTED in {
        check.reason_code for check in checks if check.reason_code
    }


def test_order_preflight_rechecks_spot_eur_market_boundary():
    from datetime import timedelta
    from decimal import Decimal

    from app.trading.live.preflight import LiveOrderPreflight, LiveOrderPreflightContext
    from app.trading.risk.models import RiskDecision, RiskDecisionStatus

    decision = RiskDecision(
        proposal_id="proposal-15",
        status=RiskDecisionStatus.APPROVED,
        reason_codes=(),
        approved_quantity=Decimal("0.001"),
    )
    wrong_market = MarketReadiness(
        symbol="BTC/EUR",
        source="other",
        quote_asset="USD",
        status="online",
        current_data_fresh=True,
        metadata_fresh=True,
        constraints_valid=True,
    )
    checks = LiveOrderPreflight(now=lambda: NOW).evaluate(
        LiveOrderPreflightContext(
            system_id="balanced_v1",
            proposal_id="proposal-15",
            proposal_side="LONG",
            proposal_expires_at=NOW + timedelta(minutes=1),
            risk_decision=decision,
            risk_profile=demo_profile(risk_profile_id="balanced"),
            kill_switch=KillSwitch().snapshot(),
            symbol="BTC/EUR",
            market=wrong_market,
            reconciliation_ready=True,
            armed=True,
        )
    )
    reasons = {check.reason_code for check in checks if check.reason_code}
    assert LivePreflightReasonCode.MARKET_SOURCE_INVALID in reasons
    assert LivePreflightReasonCode.MARKET_NOT_SPOT_EUR in reasons
