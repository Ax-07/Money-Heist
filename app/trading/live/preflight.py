from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Mapping

from app.domain.enums import SystemMode
from app.trading.risk.models import KillSwitchState, RiskDecision, RiskProfile


INITIAL_LIVE_SYSTEM_ID = "balanced_v1"
INITIAL_LIVE_RISK_PROFILE_ID = "balanced"
INITIAL_LIVE_ENVIRONMENT = "kraken_spot_eur"
INITIAL_LIVE_SYMBOLS = ("BTC/EUR", "ETH/EUR", "SOL/EUR")
INITIAL_LIVE_CAPITAL_EUR = Decimal("100")  # documentation metadata only; never a risk input

# Machine values currently returned by Kraken GetApiKeyInfo for the private
# surfaces used by Batch 14. Exact-minimum policy: an extra permission blocks.
REQUIRED_KRAKEN_PERMISSIONS = frozenset(
    {
        "query-funds",
        "query-open-trades",
        "query-closed-trades",
        "modify-trades",
        "close-trades",
    }
)
PROHIBITED_KRAKEN_PERMISSIONS = frozenset(
    {
        "add-funds",
        "withdraw-funds",
        "earn-funds",
        "query-ledger",
        "export-data",
        "create-ws-token",
        "add-withdraw-address",
        "update-withdraw-address",
    }
)


class LivePreflightStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class LiveCheckState(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class LivePreflightReasonCode(StrEnum):
    APP_ENV_NOT_PRODUCTION = "APP_ENV_NOT_PRODUCTION"
    RUNTIME_MODE_NOT_LIVE = "RUNTIME_MODE_NOT_LIVE"
    LIVE_ENVIRONMENT_NOT_EXPLICIT = "LIVE_ENVIRONMENT_NOT_EXPLICIT"
    LIVE_SYSTEM_NOT_EXPLICIT = "LIVE_SYSTEM_NOT_EXPLICIT"
    LIVE_SYSTEM_NOT_BALANCED = "LIVE_SYSTEM_NOT_BALANCED"
    TARGET_SYSTEM_IS_SHADOW = "TARGET_SYSTEM_IS_SHADOW"
    RISK_PROFILE_UNKNOWN = "RISK_PROFILE_UNKNOWN"
    RISK_PROFILE_NOT_BALANCED = "RISK_PROFILE_NOT_BALANCED"
    RISK_PROFILE_INCOMPLETE = "RISK_PROFILE_INCOMPLETE"
    KILL_SWITCH_UNKNOWN = "KILL_SWITCH_UNKNOWN"
    KILL_SWITCH_BLOCKS_NEW_TRADES = "KILL_SWITCH_BLOCKS_NEW_TRADES"
    PERSISTENCE_UNKNOWN = "PERSISTENCE_UNKNOWN"
    PERSISTENCE_UNAVAILABLE = "PERSISTENCE_UNAVAILABLE"
    AUDIT_UNKNOWN = "AUDIT_UNKNOWN"
    AUDIT_UNAVAILABLE = "AUDIT_UNAVAILABLE"
    CREDENTIALS_UNKNOWN = "CREDENTIALS_UNKNOWN"
    CREDENTIALS_MISSING = "CREDENTIALS_MISSING"
    API_PERMISSIONS_UNKNOWN = "API_PERMISSIONS_UNKNOWN"
    API_PERMISSIONS_MISSING = "API_PERMISSIONS_MISSING"
    API_PERMISSION_WITHDRAWAL = "API_PERMISSION_WITHDRAWAL"
    API_PERMISSIONS_EXCESS = "API_PERMISSIONS_EXCESS"
    MARKET_CONFIGURATION_UNKNOWN = "MARKET_CONFIGURATION_UNKNOWN"
    MARKET_SYMBOL_MISSING = "MARKET_SYMBOL_MISSING"
    MARKET_DATA_UNKNOWN = "MARKET_DATA_UNKNOWN"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    MARKET_METADATA_STALE = "MARKET_METADATA_STALE"
    MARKET_STATUS_INVALID = "MARKET_STATUS_INVALID"
    MARKET_SOURCE_INVALID = "MARKET_SOURCE_INVALID"
    MARKET_NOT_SPOT_EUR = "MARKET_NOT_SPOT_EUR"
    MARKET_CONSTRAINTS_INVALID = "MARKET_CONSTRAINTS_INVALID"
    RECONCILIATION_UNKNOWN = "RECONCILIATION_UNKNOWN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    UNRESOLVED_LIVE_ORDERS = "UNRESOLVED_LIVE_ORDERS"
    RISK_DECISION_NOT_AUTHORIZED = "RISK_DECISION_NOT_AUTHORIZED"
    RISK_DECISION_MISMATCH = "RISK_DECISION_MISMATCH"
    ORDER_STALE = "ORDER_STALE"
    ORDER_SHORT_NOT_SUPPORTED = "ORDER_SHORT_NOT_SUPPORTED"
    ORDER_SYSTEM_MISMATCH = "ORDER_SYSTEM_MISMATCH"
    ORDER_SYMBOL_NOT_ALLOWLISTED = "ORDER_SYMBOL_NOT_ALLOWLISTED"
    OPERATOR_ARM_REQUIRED = "OPERATOR_ARM_REQUIRED"


@dataclass(frozen=True, slots=True)
class LivePreflightCheck:
    name: str
    state: LiveCheckState
    reason_code: LivePreflightReasonCode | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MarketReadiness:
    symbol: str
    source: str
    quote_asset: str
    status: str
    current_data_fresh: bool | None
    metadata_fresh: bool | None
    constraints_valid: bool | None


@dataclass(frozen=True, slots=True)
class LivePreflightContext:
    system_id: str
    app_env: str
    runtime_mode: SystemMode
    live_environment: str
    explicitly_allowed_system_id: str | None
    target_system_mode: SystemMode
    risk_profile: RiskProfile | None
    kill_switch: KillSwitchState | None
    persistence_ready: bool | None
    audit_ready: bool | None
    credentials_present: bool | None
    api_permissions: tuple[str, ...] | None
    market_configuration_known: bool
    market: Mapping[str, MarketReadiness]
    reconciliation_ready: bool | None
    unresolved_live_orders: int | None


@dataclass(frozen=True, slots=True)
class LivePreflightReport:
    system_id: str
    status: LivePreflightStatus
    checks: tuple[LivePreflightCheck, ...]
    checked_at: datetime
    metadata: Mapping[str, str] = field(default_factory=dict)

    @property
    def reason_codes(self) -> tuple[LivePreflightReasonCode, ...]:
        return tuple(
            check.reason_code
            for check in self.checks
            if check.reason_code is not None and check.state is not LiveCheckState.PASS
        )

    @property
    def fingerprint(self) -> str:
        payload = {
            "system_id": self.system_id,
            "status": self.status.value,
            "checked_at": self.checked_at.isoformat(),
            "checks": [
                {
                    "name": item.name,
                    "state": item.state.value,
                    "reason": item.reason_code.value if item.reason_code else None,
                    "detail": item.detail,
                }
                for item in self.checks
            ],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "system_id": self.system_id,
            "status": self.status.value,
            "checked_at": self.checked_at.isoformat(),
            "fingerprint": self.fingerprint,
            "metadata": dict(self.metadata),
            "reason_codes": [code.value for code in self.reason_codes],
            "checks": [
                {
                    "name": check.name,
                    "state": check.state.value,
                    "reason_code": check.reason_code.value if check.reason_code else None,
                    "detail": check.detail,
                }
                for check in self.checks
            ],
        }


class LivePreflight:
    """Pure deterministic Batch 15 preflight evaluator.

    I/O belongs to probes/coordinators. Every UNKNOWN check is blocking.
    """

    def __init__(self, *, now=lambda: datetime.now(timezone.utc)) -> None:
        self._now = now

    def evaluate(self, context: LivePreflightContext) -> LivePreflightReport:
        checks: list[LivePreflightCheck] = []
        add = checks.append

        add(self._bool_check(
            "production_environment",
            context.app_env == "production",
            LivePreflightReasonCode.APP_ENV_NOT_PRODUCTION,
            f"app_env={context.app_env}",
        ))
        add(self._bool_check(
            "runtime_mode_live",
            context.runtime_mode is SystemMode.LIVE,
            LivePreflightReasonCode.RUNTIME_MODE_NOT_LIVE,
            f"runtime_mode={context.runtime_mode.value}",
        ))
        add(self._bool_check(
            "explicit_live_environment",
            context.live_environment == INITIAL_LIVE_ENVIRONMENT,
            LivePreflightReasonCode.LIVE_ENVIRONMENT_NOT_EXPLICIT,
            f"live_environment={context.live_environment}",
        ))
        add(self._bool_check(
            "explicit_live_system",
            context.explicitly_allowed_system_id == context.system_id,
            LivePreflightReasonCode.LIVE_SYSTEM_NOT_EXPLICIT,
            "target system must be explicitly allowlisted by configuration",
        ))
        add(self._bool_check(
            "balanced_system_only",
            context.system_id == INITIAL_LIVE_SYSTEM_ID,
            LivePreflightReasonCode.LIVE_SYSTEM_NOT_BALANCED,
            f"system_id={context.system_id}",
        ))
        add(self._bool_check(
            "target_not_shadow",
            context.target_system_mode is SystemMode.LIVE,
            LivePreflightReasonCode.TARGET_SYSTEM_IS_SHADOW,
            f"target_mode={context.target_system_mode.value}",
        ))

        if context.risk_profile is None:
            add(self._unknown("risk_profile", LivePreflightReasonCode.RISK_PROFILE_UNKNOWN))
        else:
            add(self._bool_check(
                "balanced_risk_profile_only",
                context.risk_profile.risk_profile_id == INITIAL_LIVE_RISK_PROFILE_ID,
                LivePreflightReasonCode.RISK_PROFILE_NOT_BALANCED,
                f"risk_profile_id={context.risk_profile.risk_profile_id}",
            ))
            missing = context.risk_profile.missing_required_limits()
            add(self._bool_check(
                "risk_profile_complete",
                not missing,
                LivePreflightReasonCode.RISK_PROFILE_INCOMPLETE,
                "missing=" + ",".join(missing) if missing else "all constitutional limits explicit",
            ))

        if context.kill_switch is None:
            add(self._unknown("kill_switch", LivePreflightReasonCode.KILL_SWITCH_UNKNOWN))
        else:
            add(self._bool_check(
                "kill_switch_allows_new_entries",
                not context.kill_switch.blocks_new_trades,
                LivePreflightReasonCode.KILL_SWITCH_BLOCKS_NEW_TRADES,
                context.kill_switch.reason or "kill switch clear",
            ))

        add(self._tri_check(
            "durable_persistence",
            context.persistence_ready,
            LivePreflightReasonCode.PERSISTENCE_UNKNOWN,
            LivePreflightReasonCode.PERSISTENCE_UNAVAILABLE,
        ))
        add(self._tri_check(
            "durable_audit",
            context.audit_ready,
            LivePreflightReasonCode.AUDIT_UNKNOWN,
            LivePreflightReasonCode.AUDIT_UNAVAILABLE,
        ))
        add(self._tri_check(
            "credentials_present_at_kraken_boundary",
            context.credentials_present,
            LivePreflightReasonCode.CREDENTIALS_UNKNOWN,
            LivePreflightReasonCode.CREDENTIALS_MISSING,
        ))

        self._permission_checks(context.api_permissions, checks)
        self._market_checks(context, checks)

        add(self._tri_check(
            "exchange_reconciled_this_session",
            context.reconciliation_ready,
            LivePreflightReasonCode.RECONCILIATION_UNKNOWN,
            LivePreflightReasonCode.RECONCILIATION_REQUIRED,
        ))
        if context.unresolved_live_orders is None:
            add(self._unknown(
                "no_unresolved_live_orders",
                LivePreflightReasonCode.RECONCILIATION_UNKNOWN,
            ))
        else:
            add(self._bool_check(
                "no_unresolved_live_orders",
                context.unresolved_live_orders == 0,
                LivePreflightReasonCode.UNRESOLVED_LIVE_ORDERS,
                f"unresolved={context.unresolved_live_orders}",
            ))

        status = (
            LivePreflightStatus.READY
            if all(check.state is LiveCheckState.PASS for check in checks)
            else LivePreflightStatus.BLOCKED
        )
        return LivePreflightReport(
            system_id=context.system_id,
            status=status,
            checks=tuple(checks),
            checked_at=self._utc_now(),
            metadata={
                "exchange": "kraken_spot",
                "quote": "EUR",
                "prototype_capital_eur": format(INITIAL_LIVE_CAPITAL_EUR, "f"),
                "capital_is_risk_input": "false",
            },
        )

    def _permission_checks(
        self,
        permissions: tuple[str, ...] | None,
        checks: list[LivePreflightCheck],
    ) -> None:
        if permissions is None:
            checks.append(self._unknown(
                "kraken_api_permissions",
                LivePreflightReasonCode.API_PERMISSIONS_UNKNOWN,
            ))
            return
        actual = frozenset(str(item).strip() for item in permissions if str(item).strip())
        missing = REQUIRED_KRAKEN_PERMISSIONS - actual
        withdrawal = actual & {
            "withdraw-funds",
            "add-withdraw-address",
            "update-withdraw-address",
        }
        extra = actual - REQUIRED_KRAKEN_PERMISSIONS
        checks.append(self._bool_check(
            "kraken_required_permissions",
            not missing,
            LivePreflightReasonCode.API_PERMISSIONS_MISSING,
            "missing=" + ",".join(sorted(missing)) if missing else "required permissions present",
        ))
        checks.append(self._bool_check(
            "kraken_no_withdrawal_permissions",
            not withdrawal,
            LivePreflightReasonCode.API_PERMISSION_WITHDRAWAL,
            "withdrawal_permissions=" + ",".join(sorted(withdrawal)) if withdrawal else "none",
        ))
        checks.append(self._bool_check(
            "kraken_no_unnecessary_permissions",
            not extra,
            LivePreflightReasonCode.API_PERMISSIONS_EXCESS,
            "extra=" + ",".join(sorted(extra)) if extra else "exact minimum permission set",
        ))

    def _market_checks(
        self,
        context: LivePreflightContext,
        checks: list[LivePreflightCheck],
    ) -> None:
        if not context.market_configuration_known:
            checks.append(self._unknown(
                "market_configuration",
                LivePreflightReasonCode.MARKET_CONFIGURATION_UNKNOWN,
            ))
        for symbol in INITIAL_LIVE_SYMBOLS:
            readiness = context.market.get(symbol)
            if readiness is None:
                checks.append(LivePreflightCheck(
                    name=f"market:{symbol}",
                    state=LiveCheckState.UNKNOWN,
                    reason_code=LivePreflightReasonCode.MARKET_SYMBOL_MISSING,
                    detail="allowlisted symbol has no verified metadata",
                ))
                continue
            checks.append(self._bool_check(
                f"market:{symbol}:source",
                readiness.source == "kraken_spot",
                LivePreflightReasonCode.MARKET_SOURCE_INVALID,
                f"source={readiness.source}",
            ))
            checks.append(self._bool_check(
                f"market:{symbol}:spot_eur",
                readiness.quote_asset.upper() in {"EUR", "ZEUR"} and symbol.endswith("/EUR"),
                LivePreflightReasonCode.MARKET_NOT_SPOT_EUR,
                f"quote={readiness.quote_asset}",
            ))
            checks.append(self._bool_check(
                f"market:{symbol}:online",
                readiness.status.lower() == "online",
                LivePreflightReasonCode.MARKET_STATUS_INVALID,
                f"status={readiness.status}",
            ))
            checks.append(self._tri_check(
                f"market:{symbol}:current_fresh",
                readiness.current_data_fresh,
                LivePreflightReasonCode.MARKET_DATA_UNKNOWN,
                LivePreflightReasonCode.MARKET_DATA_STALE,
            ))
            checks.append(self._tri_check(
                f"market:{symbol}:metadata_fresh",
                readiness.metadata_fresh,
                LivePreflightReasonCode.MARKET_DATA_UNKNOWN,
                LivePreflightReasonCode.MARKET_METADATA_STALE,
            ))
            checks.append(self._tri_check(
                f"market:{symbol}:constraints",
                readiness.constraints_valid,
                LivePreflightReasonCode.MARKET_DATA_UNKNOWN,
                LivePreflightReasonCode.MARKET_CONSTRAINTS_INVALID,
            ))

    @staticmethod
    def _bool_check(
        name: str,
        passed: bool,
        reason: LivePreflightReasonCode,
        detail: str,
    ) -> LivePreflightCheck:
        return LivePreflightCheck(
            name=name,
            state=LiveCheckState.PASS if passed else LiveCheckState.BLOCKED,
            reason_code=None if passed else reason,
            detail=detail,
        )

    @staticmethod
    def _tri_check(
        name: str,
        value: bool | None,
        unknown_reason: LivePreflightReasonCode,
        blocked_reason: LivePreflightReasonCode,
    ) -> LivePreflightCheck:
        if value is None:
            return LivePreflightCheck(name, LiveCheckState.UNKNOWN, unknown_reason, "not verified")
        if not value:
            return LivePreflightCheck(name, LiveCheckState.BLOCKED, blocked_reason, "check failed")
        return LivePreflightCheck(name, LiveCheckState.PASS, None, "verified")

    @staticmethod
    def _unknown(name: str, reason: LivePreflightReasonCode) -> LivePreflightCheck:
        return LivePreflightCheck(name, LiveCheckState.UNKNOWN, reason, "not verified")

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("preflight clock must be timezone-aware")
        return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class LiveOrderPreflightContext:
    system_id: str
    proposal_id: str
    proposal_side: str
    proposal_expires_at: datetime
    risk_decision: RiskDecision
    risk_profile: RiskProfile
    kill_switch: KillSwitchState | None
    symbol: str
    market: MarketReadiness
    reconciliation_ready: bool | None
    armed: bool


class LiveOrderPreflight:
    """Last deterministic gate before an OrderIntent is created/submitted."""

    def __init__(self, *, now=lambda: datetime.now(timezone.utc)) -> None:
        self._now = now

    def evaluate(self, context: LiveOrderPreflightContext) -> tuple[LivePreflightCheck, ...]:
        now = self._utc_now()
        checks = [
            LivePreflight._bool_check(
                "operator_arm_active",
                context.armed,
                LivePreflightReasonCode.OPERATOR_ARM_REQUIRED,
                "ephemeral operator arm required",
            ),
            LivePreflight._bool_check(
                "risk_decision_authorized",
                context.risk_decision.is_authorized,
                LivePreflightReasonCode.RISK_DECISION_NOT_AUTHORIZED,
                f"status={context.risk_decision.status.value}",
            ),
            LivePreflight._bool_check(
                "risk_decision_matches_proposal",
                context.risk_decision.proposal_id == context.proposal_id,
                LivePreflightReasonCode.RISK_DECISION_MISMATCH,
                "risk decision must belong to proposal",
            ),
            LivePreflight._bool_check(
                "order_not_stale",
                context.proposal_expires_at.tzinfo is not None
                and context.proposal_expires_at.utcoffset() is not None
                and context.proposal_expires_at > now,
                LivePreflightReasonCode.ORDER_STALE,
                f"expires_at={context.proposal_expires_at.isoformat()}",
            ),
            LivePreflight._bool_check(
                "long_only_spot_entry",
                context.proposal_side == "LONG",
                LivePreflightReasonCode.ORDER_SHORT_NOT_SUPPORTED,
                f"side={context.proposal_side}",
            ),
            LivePreflight._bool_check(
                "balanced_system",
                context.system_id == INITIAL_LIVE_SYSTEM_ID,
                LivePreflightReasonCode.ORDER_SYSTEM_MISMATCH,
                f"system_id={context.system_id}",
            ),
            LivePreflight._bool_check(
                "allowlisted_symbol",
                context.symbol in INITIAL_LIVE_SYMBOLS,
                LivePreflightReasonCode.ORDER_SYMBOL_NOT_ALLOWLISTED,
                f"symbol={context.symbol}",
            ),
            LivePreflight._bool_check(
                "market_symbol_matches_order",
                context.market.symbol == context.symbol,
                LivePreflightReasonCode.MARKET_SYMBOL_MISSING,
                f"market_symbol={context.market.symbol}",
            ),
            LivePreflight._bool_check(
                "market_source_spot",
                context.market.source == "kraken_spot",
                LivePreflightReasonCode.MARKET_SOURCE_INVALID,
                f"source={context.market.source}",
            ),
            LivePreflight._bool_check(
                "market_quote_eur",
                context.market.quote_asset.upper() in {"EUR", "ZEUR"}
                and context.symbol.endswith("/EUR"),
                LivePreflightReasonCode.MARKET_NOT_SPOT_EUR,
                f"quote={context.market.quote_asset}",
            ),
            LivePreflight._bool_check(
                "market_online",
                context.market.status.lower() == "online",
                LivePreflightReasonCode.MARKET_STATUS_INVALID,
                f"status={context.market.status}",
            ),
            LivePreflight._bool_check(
                "balanced_profile",
                context.risk_profile.risk_profile_id == INITIAL_LIVE_RISK_PROFILE_ID
                and context.risk_profile.is_complete,
                LivePreflightReasonCode.RISK_PROFILE_INCOMPLETE,
                f"risk_profile_id={context.risk_profile.risk_profile_id}",
            ),
            (
                LivePreflight._unknown(
                    "kill_switch_clear",
                    LivePreflightReasonCode.KILL_SWITCH_UNKNOWN,
                )
                if context.kill_switch is None
                else LivePreflight._bool_check(
                    "kill_switch_clear",
                    not context.kill_switch.blocks_new_trades,
                    LivePreflightReasonCode.KILL_SWITCH_BLOCKS_NEW_TRADES,
                    context.kill_switch.reason or "clear",
                )
            ),
            LivePreflight._tri_check(
                "reconciliation_current",
                context.reconciliation_ready,
                LivePreflightReasonCode.RECONCILIATION_UNKNOWN,
                LivePreflightReasonCode.RECONCILIATION_REQUIRED,
            ),
            LivePreflight._bool_check(
                "market_current_fresh",
                context.market.current_data_fresh is True,
                LivePreflightReasonCode.MARKET_DATA_STALE,
                "current price must be fresh",
            ),
            LivePreflight._bool_check(
                "market_metadata_fresh",
                context.market.metadata_fresh is True,
                LivePreflightReasonCode.MARKET_METADATA_STALE,
                "symbol metadata must be fresh",
            ),
            LivePreflight._bool_check(
                "market_constraints_valid",
                context.market.constraints_valid is True,
                LivePreflightReasonCode.MARKET_CONSTRAINTS_INVALID,
                "market constraints must be verified",
            ),
        ]
        return tuple(checks)

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("order preflight clock must be timezone-aware")
        return value.astimezone(timezone.utc)
