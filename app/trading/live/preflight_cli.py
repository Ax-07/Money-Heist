from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from app.config.settings import Settings
from app.market.exchange.kraken import (
    KRAKEN_INITIAL_SYMBOLS,
    KrakenAdapterConfig,
    KrakenPublicMarketDataProvider,
)
from app.market.exchange.transport import ResilientPublicHttpClient, StdlibJsonTransport
from app.market.quality import FreshnessPolicy
from app.storage.database import Database
from app.trading.live.activation import DenyAllLiveAuthorization
from app.trading.live.auth import EnvironmentKrakenCredentialProvider
from app.trading.live.broker import KrakenSpotLiveBroker
from app.trading.live.kraken_private import KrakenSpotPrivateRestClient
from app.trading.live.models import LiveAuditEvent
from app.trading.live.preflight import (
    INITIAL_LIVE_RISK_PROFILE_ID,
    INITIAL_LIVE_SYMBOLS,
    LivePreflight,
    LivePreflightContext,
    LivePreflightStatus,
    MarketReadiness,
)
from app.trading.live.readonly import ReadOnlyKrakenPrivateView
from app.trading.live.reconciliation import StartupReconciliationCoordinator
from app.trading.live.safety import SqlAlchemyLiveSafetyStore
from app.trading.live.store import SqlAlchemyLiveAuditSink, SqlAlchemyLiveOrderStore
from app.trading.risk.models import MarketConstraints, RiskProfile


def _decimal_or_none(value):
    return None if value is None else Decimal(str(value))


def load_explicit_risk_profile(path: str | None) -> RiskProfile | None:
    """Load operator-supplied risk values; Batch 15 never invents defaults."""

    if path is None:
        return None
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return RiskProfile(
        risk_profile_id=str(doc.get("risk_profile_id", INITIAL_LIVE_RISK_PROFILE_ID)),
        max_risk_per_trade_pct=_decimal_or_none(doc.get("max_risk_per_trade_pct")),
        max_daily_loss_pct=_decimal_or_none(doc.get("max_daily_loss_pct")),
        max_drawdown_pct=_decimal_or_none(doc.get("max_drawdown_pct")),
        max_portfolio_risk_pct=_decimal_or_none(doc.get("max_portfolio_risk_pct")),
        max_positions=(None if doc.get("max_positions") is None else int(doc["max_positions"])),
        max_leverage=_decimal_or_none(doc.get("max_leverage")),
        max_correlated_exposure_pct=_decimal_or_none(
            doc.get("max_correlated_exposure_pct")
        ),
        min_expected_rr=_decimal_or_none(doc.get("min_expected_rr")),
    )


def _constraints_valid(constraints: MarketConstraints | None) -> bool:
    if constraints is None:
        return False
    values = (constraints.qty_step, constraints.min_qty, constraints.min_notional)
    if any(not value.is_finite() or value <= 0 for value in values):
        return False
    if constraints.max_qty is not None and (
        not constraints.max_qty.is_finite() or constraints.max_qty <= 0
    ):
        return False
    # Spot Batch 15 never adds leverage. ``None`` is the Batch 13 projection.
    if constraints.max_leverage is not None and constraints.max_leverage > Decimal("1"):
        return False
    return True


async def _probe_market(settings: Settings) -> tuple[bool, dict[str, MarketReadiness]]:
    if (
        settings.live_market_max_age_seconds is None
        or settings.live_metadata_max_age_seconds is None
        or settings.live_timeframe_values is None
    ):
        return False, {}

    policy = FreshnessPolicy(max_age=timedelta(seconds=settings.live_market_max_age_seconds))
    provider = KrakenPublicMarketDataProvider(
        ResilientPublicHttpClient(StdlibJsonTransport()),
        config=KrakenAdapterConfig(
            freshness_policy=policy,
            snapshot_timeframes=settings.live_timeframe_values,
            metadata_max_age=timedelta(seconds=settings.live_metadata_max_age_seconds),
        ),
    )
    result: dict[str, MarketReadiness] = {}
    for symbol in INITIAL_LIVE_SYMBOLS:
        try:
            snapshot = await provider.get_snapshot(symbol)
            metadata = provider.get_cached_symbol_metadata(symbol)
            constraints = provider.get_market_constraints(symbol=symbol)
            if metadata is None:
                result[symbol] = MarketReadiness(
                    symbol=symbol,
                    source="unknown",
                    quote_asset="unknown",
                    status="unknown",
                    current_data_fresh=None,
                    metadata_fresh=False,
                    constraints_valid=False,
                )
                continue
            result[symbol] = MarketReadiness(
                symbol=symbol,
                source=metadata.source,
                quote_asset=metadata.quote_asset,
                status=metadata.status,
                current_data_fresh=snapshot.quality.is_valid and not snapshot.quality.is_stale,
                metadata_fresh=True,
                constraints_valid=_constraints_valid(constraints),
            )
        except Exception:
            # Fail closed without serializing remote payloads or traceback data.
            result[symbol] = MarketReadiness(
                symbol=symbol,
                source="unknown",
                quote_asset="unknown",
                status="unknown",
                current_data_fresh=None,
                metadata_fresh=None,
                constraints_valid=None,
            )
    return True, result


async def run_preflight(settings: Settings) -> dict[str, object]:
    system_id = settings.live_system_id or settings.default_system_id
    risk_profile: RiskProfile | None
    try:
        risk_profile = load_explicit_risk_profile(settings.live_risk_profile_file)
    except Exception:
        risk_profile = None

    database = Database(settings.database_url)
    store = SqlAlchemyLiveOrderStore(database.session_factory)
    audit = SqlAlchemyLiveAuditSink(database.session_factory)
    safety = SqlAlchemyLiveSafetyStore(database.session_factory)

    try:
        persistence_ready: bool | None = store.healthcheck()
    except Exception:
        persistence_ready = False
    try:
        audit_ready: bool | None = audit.healthcheck()
    except Exception:
        audit_ready = False
    try:
        safety_ready: bool | None = safety.healthcheck()
    except Exception:
        safety_ready = False

    credentials_present = bool(
        os.getenv(EnvironmentKrakenCredentialProvider.API_KEY_ENV, "").strip()
        and os.getenv(EnvironmentKrakenCredentialProvider.API_SECRET_ENV, "").strip()
    )
    permissions: tuple[str, ...] | None = None
    reconciliation_ready: bool | None = None

    market_configuration_known, market = await _probe_market(settings)

    if persistence_ready:
        try:
            store.mark_reconciliation_required(
                system_id=system_id,
                reason="preflight_process_start",
            )
        except Exception:
            persistence_ready = False

    if credentials_present and persistence_ready and audit_ready:
        try:
            full_client = KrakenSpotPrivateRestClient(
                credentials=EnvironmentKrakenCredentialProvider()
            )
            readonly_api = ReadOnlyKrakenPrivateView(full_client)
            key_info = await readonly_api.get_api_key_info()
            raw_permissions = key_info.get("permissions")
            if isinstance(raw_permissions, (list, tuple)):
                permissions = tuple(str(item) for item in raw_permissions)

            # Deliberately construct the broker with the read-only capability
            # wrapper + deny-all authorization. Reconciliation works; order
            # submission cannot reach AddOrder from this process.
            broker = KrakenSpotLiveBroker(
                api=readonly_api,
                authorization=DenyAllLiveAuthorization(),
                store=store,
                audit=audit,
                allowed_system_ids=frozenset({system_id}),
                cancellation_enabled=False,
            )
            reconciliation = StartupReconciliationCoordinator(
                system_id=system_id,
                broker=broker,
                api=readonly_api,
                store=store,
                audit=audit,
            )
            result = await reconciliation.reconcile()
            reconciliation_ready = result.ready and not store.reconciliation_required(
                system_id=system_id
            )
        except Exception:
            # Invalid credentials, missing permission, transport error, DB error:
            # all become UNKNOWN/BLOCKED, never an optimistic pass.
            reconciliation_ready = False

    kill_switch = None
    if safety_ready:
        try:
            kill_switch = safety.snapshot(system_id=system_id)
        except Exception:
            kill_switch = None

    unresolved: int | None
    if persistence_ready:
        try:
            unresolved = len(store.unresolved_records(system_id=system_id))
        except Exception:
            unresolved = None
    else:
        unresolved = None

    report = LivePreflight().evaluate(
        LivePreflightContext(
            system_id=system_id,
            app_env=settings.app_env,
            runtime_mode=settings.runtime_mode,
            live_environment=settings.live_environment,
            explicitly_allowed_system_id=settings.live_system_id,
            target_system_mode=settings.runtime_mode,
            risk_profile=risk_profile,
            kill_switch=kill_switch,
            persistence_ready=persistence_ready,
            audit_ready=audit_ready,
            credentials_present=credentials_present,
            api_permissions=permissions,
            market_configuration_known=market_configuration_known,
            market=market,
            reconciliation_ready=reconciliation_ready,
            unresolved_live_orders=unresolved,
        )
    )

    if audit_ready:
        try:
            audit.record(
                LiveAuditEvent(
                    event_type="LIVE_PREFLIGHT_RESULT",
                    severity="INFO" if report.status is LivePreflightStatus.READY else "CRITICAL",
                    system_id=system_id,
                    client_order_id=None,
                    created_at=report.checked_at,
                    details={
                        "status": report.status.value,
                        "fingerprint": report.fingerprint,
                        "reason_codes": ",".join(code.value for code in report.reason_codes),
                    },
                )
            )
        except Exception:
            # Durable audit failure must never be represented as READY.
            data = report.as_dict()
            data["status"] = LivePreflightStatus.BLOCKED.value
            data["reason_codes"] = sorted(
                set(data["reason_codes"]) | {"AUDIT_UNAVAILABLE"}
            )
            data["audit_write_failed"] = True
            return data
    return report.as_dict()


def _settings_error(exc: ValidationError) -> dict[str, object]:
    return {
        "status": "BLOCKED",
        "reason_codes": ["SETTINGS_INVALID"],
        "checks": [
            {
                "name": "settings",
                "state": "BLOCKED",
                "reason_code": "SETTINGS_INVALID",
                "detail": "LIVE configuration is incomplete or invalid",
            }
        ],
        "validation_error_count": len(exc.errors()),
    }


def main() -> int:
    try:
        settings = Settings()
    except ValidationError as exc:
        output = _settings_error(exc)
        print(json.dumps(output, indent=2, sort_keys=True))
        return 2

    try:
        output = asyncio.run(run_preflight(settings))
    except Exception:
        output = {
            "status": "BLOCKED",
            "reason_codes": ["PREFLIGHT_INTERNAL_FAILURE"],
            "checks": [],
        }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output.get("status") == "READY" else 2


if __name__ == "__main__":
    sys.exit(main())
