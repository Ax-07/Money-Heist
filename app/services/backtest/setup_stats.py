from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.market.features.models import FeatureSnapshot
from app.market.scanner.models import CandidateOpportunity

from .ids import canonical_json, stable_digest
from .splits import BacktestPeriodRole

SETUP_DEFINITION_VERSION = "scanner-regime-v1"
CATALOG_SCHEMA = "money-heist.denver-setup-stats.v1"
ZERO = Decimal("0")


class HistoricalSetupAttributionError(ValueError):
    """A closed trade cannot be mapped to exactly one historical setup."""


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class HistoricalSetupKey:
    system_id: str
    symbol: str
    timeframe: str
    scanner_version: str
    feature_version: str
    regime: str
    triggers: tuple[str, ...]
    definition_version: str = SETUP_DEFINITION_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "system_id",
            "symbol",
            "timeframe",
            "scanner_version",
            "feature_version",
            "regime",
            "definition_version",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be empty")
        if not self.triggers:
            raise ValueError("setup key requires at least one scanner trigger")
        normalized = tuple(
            sorted({str(item).strip() for item in self.triggers if str(item).strip()})
        )
        if not normalized:
            raise ValueError("setup key requires non-empty scanner triggers")
        object.__setattr__(self, "triggers", normalized)

    @property
    def setup_id(self) -> str:
        return "setup:" + stable_digest(self.canonical_payload())

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "definition_version": self.definition_version,
            "system_id": self.system_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "scanner_version": self.scanner_version,
            "feature_version": self.feature_version,
            "regime": self.regime,
            "triggers": self.triggers,
        }

    @classmethod
    def from_market(
        cls,
        opportunity: CandidateOpportunity,
        market_context: FeatureSnapshot,
    ) -> HistoricalSetupKey:
        if opportunity.symbol != market_context.symbol:
            raise ValueError("opportunity symbol does not match setup market context")
        if opportunity.timeframe != market_context.timeframe:
            raise ValueError("opportunity timeframe does not match setup market context")
        if opportunity.snapshot_id != market_context.snapshot_id:
            raise ValueError("opportunity snapshot does not match setup market context")
        return cls(
            system_id=opportunity.system_id,
            symbol=opportunity.symbol,
            timeframe=opportunity.timeframe,
            scanner_version=opportunity.scanner_version,
            feature_version=market_context.feature_version,
            regime=str(_value(market_context.regime)),
            triggers=tuple(str(_value(item)) for item in opportunity.triggers),
        )


@dataclass(frozen=True, slots=True)
class HistoricalSetupObservation:
    run_id: str
    dataset_id: str
    strategy_fingerprint: str
    period_role: BacktestPeriodRole
    opportunity_id: str
    trade_id: str
    setup: HistoricalSetupKey
    side: str
    opened_at: datetime
    closed_at: datetime
    net_pnl: Decimal

    def __post_init__(self) -> None:
        for field_name in (
            "run_id",
            "dataset_id",
            "strategy_fingerprint",
            "opportunity_id",
            "trade_id",
            "side",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be empty")
        opened = _as_utc(self.opened_at, field_name="opened_at")
        closed = _as_utc(self.closed_at, field_name="closed_at")
        if closed < opened:
            raise ValueError("closed_at cannot precede opened_at")
        pnl = Decimal(str(self.net_pnl))
        if not pnl.is_finite():
            raise ValueError("net_pnl must be finite")
        object.__setattr__(self, "opened_at", opened)
        object.__setattr__(self, "closed_at", closed)
        object.__setattr__(self, "net_pnl", pnl)

    @property
    def observation_id(self) -> str:
        return "setup-observation:" + stable_digest(self.canonical_payload())

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "dataset_id": self.dataset_id,
            "strategy_fingerprint": self.strategy_fingerprint,
            "period_role": self.period_role,
            "opportunity_id": self.opportunity_id,
            "trade_id": self.trade_id,
            "setup": self.setup.canonical_payload(),
            "side": self.side,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "net_pnl": self.net_pnl,
        }


@dataclass(frozen=True, slots=True)
class HistoricalSetupStats:
    stats_id: str
    setup: HistoricalSetupKey
    as_of: datetime
    source_run_ids: tuple[str, ...]
    source_dataset_ids: tuple[str, ...]
    sample_count: int
    oos_sample_count: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: Decimal
    expectancy: Decimal
    profit_factor: Decimal | None
    profit_factor_status: str

    def __post_init__(self) -> None:
        as_of = _as_utc(self.as_of, field_name="as_of")
        if self.sample_count <= 0:
            raise ValueError("historical setup stats require at least one sample")
        if self.oos_sample_count < 0 or self.oos_sample_count > self.sample_count:
            raise ValueError("invalid oos_sample_count")
        if self.winning_trades + self.losing_trades + self.breakeven_trades != self.sample_count:
            raise ValueError("trade outcome counts do not sum to sample_count")
        object.__setattr__(self, "as_of", as_of)

    def to_denver_context_payload(self) -> dict[str, Any]:
        notes = (
            "expectancy_basis=NET_PNL_QUOTE_CURRENCY",
            f"profit_factor_status={self.profit_factor_status}",
            f"setup_id={self.setup.setup_id}",
        )
        return {
            "stats_id": self.stats_id,
            "setup_definition_version": self.setup.definition_version,
            "as_of": self.as_of,
            "source_run_ids": self.source_run_ids,
            "source_dataset_ids": self.source_dataset_ids,
            "sample_count": self.sample_count,
            "oos_sample_count": self.oos_sample_count,
            "win_rate": float(self.win_rate),
            "expectancy": float(self.expectancy),
            "profit_factor": (
                float(self.profit_factor) if self.profit_factor is not None else None
            ),
            "max_drawdown_pct": None,
            "regime": self.setup.regime,
            "notes": notes,
        }


@dataclass(frozen=True, slots=True)
class _ExecutedEntry:
    system_id: str
    symbol: str
    opportunity_id: str
    setup: HistoricalSetupKey
    side: str
    price: Decimal
    quantity: Decimal
    filled_at: datetime


class HistoricalSetupStatsCatalog:
    """Frozen deterministic setup database consumed by Denver as a read-only context provider."""

    def __init__(self, observations: tuple[HistoricalSetupObservation, ...]) -> None:
        unique: dict[str, HistoricalSetupObservation] = {}
        for observation in observations:
            key = observation.observation_id
            if key in unique:
                raise ValueError(f"duplicate historical setup observation: {key}")
            unique[key] = observation
        self._observations = tuple(
            sorted(unique.values(), key=lambda item: (item.closed_at, item.observation_id))
        )
        economic_keys: set[tuple[str, str, str]] = set()
        for item in self._observations:
            key = (item.setup.setup_id, item.opportunity_id, item.side)
            if key in economic_keys:
                raise ValueError(
                    "Denver setup-stats catalog cannot double-count one market opportunity"
                )
            economic_keys.add(key)
        fingerprints = {item.strategy_fingerprint for item in self._observations}
        if len(fingerprints) > 1:
            raise ValueError(
                "Denver setup-stats catalog cannot mix different strategy fingerprints"
            )

    @property
    def observations(self) -> tuple[HistoricalSetupObservation, ...]:
        return self._observations

    @property
    def strategy_fingerprint(self) -> str | None:
        if not self._observations:
            return None
        return self._observations[0].strategy_fingerprint

    @property
    def catalog_id(self) -> str:
        payload = {
            "schema": CATALOG_SCHEMA,
            "setup_definition_version": SETUP_DEFINITION_VERSION,
            "observations": tuple(item.canonical_payload() for item in self._observations),
        }
        return "denver-catalog:" + stable_digest(payload)

    @property
    def reproducibility_assumptions(self) -> dict[str, str]:
        assumptions = {
            "denver_setup_stats_catalog_id": self.catalog_id,
            "denver_setup_definition_version": SETUP_DEFINITION_VERSION,
        }
        if self.strategy_fingerprint is not None:
            assumptions["denver_source_strategy_fingerprint"] = self.strategy_fingerprint
        return assumptions

    def query(
        self,
        *,
        opportunity: CandidateOpportunity,
        market_context: FeatureSnapshot,
        as_of: datetime,
    ) -> HistoricalSetupStats | None:
        setup = HistoricalSetupKey.from_market(opportunity, market_context)
        cutoff = _as_utc(as_of, field_name="as_of")
        eligible = tuple(
            item
            for item in self._observations
            if item.setup == setup and item.closed_at <= cutoff
        )
        if not eligible:
            return None

        wins = tuple(item for item in eligible if item.net_pnl > ZERO)
        losses = tuple(item for item in eligible if item.net_pnl < ZERO)
        breakeven = tuple(item for item in eligible if item.net_pnl == ZERO)
        count = len(eligible)
        gross_profit = sum((item.net_pnl for item in wins), ZERO)
        gross_loss = abs(sum((item.net_pnl for item in losses), ZERO))
        if gross_loss > ZERO:
            profit_factor = gross_profit / gross_loss
            profit_factor_status = "AVAILABLE"
        elif gross_profit > ZERO:
            profit_factor = None
            profit_factor_status = "UNBOUNDED_NO_LOSSES"
        else:
            profit_factor = None
            profit_factor_status = "UNAVAILABLE_NO_PROFIT_OR_LOSS"

        observation_ids = tuple(item.observation_id for item in eligible)
        stats_id = "denver-stats:" + stable_digest(
            {
                "setup": setup.canonical_payload(),
                "observation_ids": observation_ids,
            }
        )
        return HistoricalSetupStats(
            stats_id=stats_id,
            setup=setup,
            as_of=cutoff,
            source_run_ids=tuple(sorted({item.run_id for item in eligible})),
            source_dataset_ids=tuple(sorted({item.dataset_id for item in eligible})),
            sample_count=count,
            oos_sample_count=sum(
                1 for item in eligible if item.period_role is BacktestPeriodRole.OOS
            ),
            winning_trades=len(wins),
            losing_trades=len(losses),
            breakeven_trades=len(breakeven),
            win_rate=Decimal(len(wins)) / Decimal(count),
            expectancy=sum((item.net_pnl for item in eligible), ZERO) / Decimal(count),
            profit_factor=profit_factor,
            profit_factor_status=profit_factor_status,
        )

    def to_json(self) -> str:
        payload = {
            "schema": CATALOG_SCHEMA,
            "catalog_id": self.catalog_id,
            "setup_definition_version": SETUP_DEFINITION_VERSION,
            "observations": tuple(item.canonical_payload() for item in self._observations),
        }
        return canonical_json(payload)

    @classmethod
    def from_json(cls, payload: str) -> HistoricalSetupStatsCatalog:
        raw = json.loads(payload)
        if raw.get("schema") != CATALOG_SCHEMA:
            raise ValueError("unsupported Denver setup-stats catalog schema")
        if raw.get("setup_definition_version") != SETUP_DEFINITION_VERSION:
            raise ValueError("unsupported Denver setup definition version")
        observations = []
        for item in raw.get("observations", []):
            setup_raw = item["setup"]
            setup = HistoricalSetupKey(
                system_id=setup_raw["system_id"],
                symbol=setup_raw["symbol"],
                timeframe=setup_raw["timeframe"],
                scanner_version=setup_raw["scanner_version"],
                feature_version=setup_raw["feature_version"],
                regime=setup_raw["regime"],
                triggers=tuple(setup_raw["triggers"]),
                definition_version=setup_raw["definition_version"],
            )
            observations.append(
                HistoricalSetupObservation(
                    run_id=item["run_id"],
                    dataset_id=item["dataset_id"],
                    strategy_fingerprint=item["strategy_fingerprint"],
                    period_role=BacktestPeriodRole(item["period_role"]),
                    opportunity_id=item["opportunity_id"],
                    trade_id=item["trade_id"],
                    setup=setup,
                    side=item["side"],
                    opened_at=datetime.fromisoformat(item["opened_at"].replace("Z", "+00:00")),
                    closed_at=datetime.fromisoformat(item["closed_at"].replace("Z", "+00:00")),
                    net_pnl=Decimal(item["net_pnl"]),
                )
            )
        catalog = cls(tuple(observations))
        expected_id = raw.get("catalog_id")
        if expected_id != catalog.catalog_id:
            raise ValueError("Denver setup-stats catalog_id does not match content")
        return catalog



class DenverSetupStatsContextProvider:
    """Adapter from a frozen setup-stats catalog to orchestration specialist contexts."""

    def __init__(self, catalog: HistoricalSetupStatsCatalog) -> None:
        self.catalog = catalog

    @classmethod
    def for_backtest(
        cls,
        catalog: HistoricalSetupStatsCatalog,
        *,
        config: Any,
    ) -> DenverSetupStatsContextProvider:
        actual = dict(getattr(config, "execution_assumptions", {}) or {})
        expected = catalog.reproducibility_assumptions
        missing = sorted(key for key in expected if key not in actual)
        mismatched = sorted(
            key for key, value in expected.items() if key in actual and actual[key] != value
        )
        if missing or mismatched:
            details = []
            if missing:
                details.append("missing=" + ",".join(missing))
            if mismatched:
                details.append("mismatched=" + ",".join(mismatched))
            raise ValueError(
                "BacktestConfig.execution_assumptions does not bind Denver catalog: "
                + "; ".join(details)
            )
        return cls(catalog)

    @property
    def reproducibility_assumptions(self) -> dict[str, str]:
        return self.catalog.reproducibility_assumptions

    def contexts_for(
        self,
        *,
        opportunity: CandidateOpportunity,
        market_context: FeatureSnapshot,
    ) -> dict[str, Any]:
        stats = self.catalog.query(
            opportunity=opportunity,
            market_context=market_context,
            as_of=market_context.observed_at,
        )
        if stats is None:
            return {}
        return {"denver": stats.to_denver_context_payload()}

def observations_from_historical_replay(
    replay_result: Any,
    evaluation_bundle: Any,
    *,
    period_role: BacktestPeriodRole,
) -> tuple[HistoricalSetupObservation, ...]:
    """Join real Batch 16 executed opportunities to Batch 10 closed-trade outcomes.

    Attribution is intentionally strict. A closed trade must map to exactly one entry fill with
    the same system, symbol, side, open timestamp, entry price and quantity. Ambiguous scaled or
    reversal positions fail closed instead of being silently assigned to a setup.
    """

    run = replay_result.backtest_result.run
    config_payload = run.config.canonical_payload()
    strategy_fingerprint = "strategy:" + stable_digest(config_payload)
    entries: list[_ExecutedEntry] = []
    for point in replay_result.points:
        result = getattr(point, "pipeline_result", None)
        opportunity = getattr(point, "opportunity", None)
        feature = getattr(point, "feature_snapshot", None)
        fill = getattr(result, "fill", None) if result is not None else None
        order = getattr(result, "order", None) if result is not None else None
        orchestration = (
            getattr(result, "orchestration_result", None) if result is not None else None
        )
        proposal = (
            getattr(orchestration, "trade_proposal", None)
            if orchestration is not None
            else None
        )
        required = (opportunity, feature, fill, order, proposal)
        if any(item is None for item in required):
            continue
        proposal_side = str(_value(proposal.side))
        expected_order_side = "BUY" if proposal_side == "LONG" else "SELL"
        actual_order_side = str(_value(order.side))
        if actual_order_side != expected_order_side:
            raise ValueError("executed order side does not match trade proposal side")
        entries.append(
            _ExecutedEntry(
                system_id=opportunity.system_id,
                symbol=opportunity.symbol,
                opportunity_id=opportunity.opportunity_id,
                setup=HistoricalSetupKey.from_market(opportunity, feature),
                side=proposal_side,
                price=Decimal(str(fill.price)),
                quantity=Decimal(str(fill.quantity)),
                filled_at=_as_utc(fill.filled_at, field_name="fill.filled_at"),
            )
        )

    observations = []
    for trade in evaluation_bundle.report.trading.closed_trades:
        opened_at = _as_utc(trade.opened_at, field_name="trade.opened_at")
        candidates = [
            entry
            for entry in entries
            if entry.system_id == trade.system_id
            and entry.symbol == trade.symbol
            and entry.side == trade.side
            and entry.filled_at == opened_at
            and entry.price == Decimal(str(trade.entry_price))
            and entry.quantity == Decimal(str(trade.quantity))
        ]
        if len(candidates) != 1:
            raise HistoricalSetupAttributionError(
                f"closed trade {trade.trade_id} cannot be attributed to exactly one setup entry"
            )
        entry = candidates[0]
        observations.append(
            HistoricalSetupObservation(
                run_id=run.run_id,
                dataset_id=run.dataset.dataset_id,
                strategy_fingerprint=strategy_fingerprint,
                period_role=period_role,
                opportunity_id=entry.opportunity_id,
                trade_id=trade.trade_id,
                setup=entry.setup,
                side=trade.side,
                opened_at=trade.opened_at,
                closed_at=trade.closed_at,
                net_pnl=Decimal(str(trade.net_pnl)),
            )
        )
    return tuple(observations)


def catalog_from_historical_runs(
    sources: tuple[tuple[Any, Any, BacktestPeriodRole], ...],
) -> HistoricalSetupStatsCatalog:
    observations = []
    for replay_result, evaluation_bundle, period_role in sources:
        observations.extend(
            observations_from_historical_replay(
                replay_result,
                evaluation_bundle,
                period_role=period_role,
            )
        )
    return HistoricalSetupStatsCatalog(tuple(observations))


__all__ = [
    "HistoricalSetupAttributionError",
    "CATALOG_SCHEMA",
    "SETUP_DEFINITION_VERSION",
    "HistoricalSetupKey",
    "HistoricalSetupObservation",
    "HistoricalSetupStats",
    "DenverSetupStatsContextProvider",
    "HistoricalSetupStatsCatalog",
    "catalog_from_historical_runs",
    "observations_from_historical_replay",
]
